"""Worker Celery real, broker filesystem e checkpoint PostgreSQL real.

Cenario: o worker 1 morre a meio (depois da triagem, ao entrar em knowledge_retrieval).
O worker 2 arranca e a tarefa conclui-se a partir do checkpoint, sem repetir a triagem.

Executar com: pytest -m postgres tests/test_celery_worker.py
"""

import os
import subprocess
import sys
import time

import pgserver
import psycopg
import pytest
from sqlalchemy import create_engine

from backend.app.auth.security import Principal
from backend.app.service import create_task
from backend.app.store.db import make_session_factory
from backend.app.store.models import Task, TaskEvent
from tests.conftest import ROOT

pytestmark = pytest.mark.postgres

PRINCIPAL = Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo")
REQUEST = "classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta"


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata-celery"), cleanup_mode="stop")
    base = server.get_uri()
    host_port = base.split("@", 1)[1].split("/", 1)[0]
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("CREATE DATABASE agentstation_celery")
    yield {
        "plain": f"postgresql://postgres@{host_port}/agentstation_celery",
        "sqlalchemy": f"postgresql+psycopg://postgres@{host_port}/agentstation_celery",
    }
    server.cleanup()


def _env(pg, tmp_path, **extra):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "DATABASE_URL": pg["sqlalchemy"],
        "CHECKPOINT_URL": pg["plain"],
        "CELERY_BROKER_URL": "filesystem://",
        "CELERY_FS_DIR": str(tmp_path / "broker"),
        "CELERY_EAGER": "false",
        "CHROMA_PATH": str(tmp_path / "chroma"),
        "DEMO_MODE": "true",
        "LLM_PROVIDER": "fake",
    }
    env.update(extra)
    return env


def _wait_for(predicate, timeout_s: float, step: float = 1.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def test_real_worker_killed_mid_task_resumes_on_restart(pg, tmp_path):
    env = _env(pg, tmp_path)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    seed = subprocess.run(
        [sys.executable, "-m", "backend.app.seed"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert seed.returncode == 0, seed.stderr

    factory = make_session_factory(create_engine(pg["sqlalchemy"]))
    with factory() as s:
        task_id = create_task(s, PRINCIPAL, REQUEST).id

    # 1. enfileirar pelo caminho real (producer -> broker filesystem)
    enqueue = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from backend.app.workers.tasks import run_task; run_task.delay('{task_id}')",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert enqueue.returncode == 0, enqueue.stderr[-2000:]

    worker_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "backend.app.workers.celery_app",
        "worker",
        "--pool=solo",
        "--loglevel=info",
        "--without-gossip",
        "--without-mingle",
    ]

    # 2. worker 1: morre ao entrar em knowledge_retrieval (apos o checkpoint da triagem)
    log1 = open(tmp_path / "worker1.log", "w", encoding="utf-8")
    w1 = subprocess.Popen(
        worker_cmd,
        cwd=ROOT,
        stdout=log1,
        stderr=subprocess.STDOUT,
        env=_env(pg, tmp_path, CRASH_AT_NODE="knowledge_retrieval", ALLOW_TEST_HOOKS="true"),
    )
    try:
        assert _wait_for(lambda: w1.poll() is not None, timeout_s=300), "worker 1 nao morreu"
    finally:
        log1.close()
    assert w1.returncode == 137, (tmp_path / "worker1.log").read_text(encoding="utf-8")[-3000:]

    with factory() as s:
        assert s.get(Task, task_id).status == "running"
        triage_calls = (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="node_started", node="triage")
            .count()
        )
    assert triage_calls == 1

    # 3. worker 2 sem crash: deve retomar a partir do checkpoint PostgreSQL
    log2 = open(tmp_path / "worker2.log", "w", encoding="utf-8")
    w2 = subprocess.Popen(
        worker_cmd, cwd=ROOT, stdout=log2, stderr=subprocess.STDOUT, env=_env(pg, tmp_path)
    )

    def completed() -> bool:
        with factory() as s:
            return s.get(Task, task_id).status == "completed"

    try:
        done = _wait_for(completed, timeout_s=300, step=2)
    finally:
        w2.terminate()
        try:
            w2.wait(timeout=30)
        except subprocess.TimeoutExpired:
            w2.kill()
        log2.close()
    worker2_log = (tmp_path / "worker2.log").read_text(encoding="utf-8")
    assert done, worker2_log[-3000:]
    assert "resumed_from_checkpoint" in worker2_log, worker2_log[-3000:]

    with factory() as s:
        assert (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="node_started", node="triage")
            .count()
            == 1
        )
        assert (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="tool_call", tool="get_ticket")
            .count()
            == 1
        )

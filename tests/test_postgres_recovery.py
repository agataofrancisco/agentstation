"""Recuperacao real com PostgreSQL (pgserver, sem Docker): crash a meio e retoma do checkpoint.

Executar com: pytest -m postgres
"""

import json
import os
import subprocess
import sys

import pgserver
import psycopg
import pytest
from sqlalchemy import create_engine

from backend.app.auth.security import Principal
from backend.app.graph.checkpointer import open_checkpointer
from backend.app.service import create_task
from backend.app.store.db import make_session_factory
from backend.app.store.models import Task, TaskEvent
from tests.conftest import ROOT

pytestmark = pytest.mark.postgres

PRINCIPAL = Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo")
REQUEST = "classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta"


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    datadir = tmp_path_factory.mktemp("pgdata")
    server = pgserver.get_server(datadir, cleanup_mode="stop")
    base = server.get_uri()  # postgresql://postgres:@127.0.0.1:PORT/postgres
    host_port = base.split("@", 1)[1].split("/", 1)[0]
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("CREATE DATABASE agentstation_test")
    yield {
        "plain": f"postgresql://postgres@{host_port}/agentstation_test",
        "sqlalchemy": f"postgresql+psycopg://postgres@{host_port}/agentstation_test",
    }
    server.cleanup()


def _env(pg, tmp_path, **extra):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "DATABASE_URL": pg["sqlalchemy"],
        "CHECKPOINT_URL": pg["plain"],
        "CELERY_EAGER": "true",
        "CHROMA_PATH": str(tmp_path / "chroma"),
        "DEMO_MODE": "true",
        "LLM_PROVIDER": "fake",
    }
    env.update(extra)
    return env


def _run(args, env):
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=240
    )


def test_worker_crash_then_resume_does_not_repeat_triage(pg, tmp_path):
    env = _env(pg, tmp_path)
    # 1. esquema + seed (migracoes reais no PostgreSQL)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    seed = _run(["-m", "backend.app.seed"], env)
    assert seed.returncode == 0, seed.stderr

    engine = create_engine(pg["sqlalchemy"])
    factory = make_session_factory(engine)
    with factory() as s:
        task_id = create_task(s, PRINCIPAL, REQUEST).id

    # 2. arranque do worker que morre ao entrar em knowledge_retrieval (apos o checkpoint do triage)
    crash_env = _env(pg, tmp_path, CRASH_AT_NODE="knowledge_retrieval")
    crashed = subprocess.run(
        [sys.executable, "tests/pg_child.py", "start", task_id],
        cwd=ROOT,
        env=crash_env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert crashed.returncode == 137, crashed.stderr[-2000:]

    # 3. inspecao do checkpoint a meio, feita por outro processo
    saver = open_checkpointer(pg["plain"])
    from backend.app.agents.fake import FakeProvider
    from backend.app.config import Settings
    from backend.app.graph.build import build_graph
    from backend.app.graph.runtime import GraphDeps

    cfg = Settings(database_url=pg["sqlalchemy"], checkpoint_url=pg["plain"], demo_mode=True)
    deps = GraphDeps(settings=cfg, session_factory=factory, llm=FakeProvider())
    graph = build_graph(deps, saver)
    snapshot = graph.get_state({"configurable": {"thread_id": task_id}})
    assert snapshot.next == ("knowledge_retrieval",)
    triage_before = snapshot.values["results"]["triage"]
    assert triage_before["ticket_id"] == "T-101"

    with factory() as s:
        assert s.get(Task, task_id).status == "running"
        gets_before = (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="tool_call", tool="get_ticket")
            .count()
        )
    assert gets_before == 1

    # 4. retoma num processo novo, sem crash
    resumed = _run(["tests/pg_child.py", "resume", task_id], env)
    assert resumed.returncode == 0, resumed.stderr[-2000:]
    outcome = json.loads(resumed.stdout.strip().splitlines()[-1])["outcome"]
    assert outcome == "resumed_from_checkpoint"

    with factory() as s:
        task = s.get(Task, task_id)
        assert task.status == "completed"
        gets_after = (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="tool_call", tool="get_ticket")
            .count()
        )
        triage_starts = (
            s.query(TaskEvent)
            .filter_by(task_id=task_id, type="node_started", node="triage")
            .count()
        )
    assert gets_after == 1, "a triagem nao deve ser recalculada depois do checkpoint"
    assert triage_starts == 1
    final = graph.get_state({"configurable": {"thread_id": task_id}})
    assert final.values["results"]["triage"] == triage_before

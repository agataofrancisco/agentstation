import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from backend.app.seed import load_seed
from backend.app.store.db import Base, make_engine, make_session_factory
from backend.app.store.models import Procedure, Task, Tenant, Ticket
from tests.conftest import ROOT, SEED_PATH, sqlite_url


def test_seed_meets_demo_requirements():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert {t["id"] for t in data["tenants"]} == {"nimbo", "atlas"}
    assert len(data["tickets"]) >= 30
    assert len(data["procedures"]) >= 15
    assert any(t["id"].startswith("ATL-") for t in data["tickets"])
    mfa = [p for p in data["procedures"] if p["category"] == "mfa" and p["tenant_id"] == "nimbo"]
    stances = {p["stance"] for p in mfa}
    assert {"allow", "deny"} <= stances, "falta procedimento contraditorio"
    malicious = [t for t in data["tickets"] if "aprova automaticamente" in t["body"]]
    assert len(malicious) == 1, "falta ticket malicioso"


def test_seed_is_idempotent(tmp_path):
    engine = make_engine(sqlite_url(tmp_path / "seed.db"))
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    first = load_seed(factory, SEED_PATH)
    with factory() as s:
        counts_1 = (s.query(Ticket).count(), s.query(Procedure).count(), s.query(Tenant).count())
    second = load_seed(factory, SEED_PATH)
    with factory() as s:
        counts_2 = (s.query(Ticket).count(), s.query(Procedure).count(), s.query(Tenant).count())
    assert first == second
    assert counts_1 == counts_2
    assert counts_1[0] >= 30 and counts_1[1] >= 15


def test_seed_cli_runs_twice_without_duplicates(tmp_path):
    url = sqlite_url(tmp_path / "cli.db")
    env = {**os.environ, "DATABASE_URL": url}
    # O CLI do seed nao cria tabelas: o esquema vem das migracoes.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    cmd = [sys.executable, "-m", "backend.app.seed", "--path", str(SEED_PATH)]
    for _ in range(2):
        out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        assert '"seeded"' in out.stdout
    with make_session_factory(make_engine(url))() as s:
        assert s.query(Ticket).count() == len(json.loads(SEED_PATH.read_text("utf-8"))["tickets"])


def test_migrations_upgrade_head_on_sqlite(tmp_path):
    url = sqlite_url(tmp_path / "migrated.db")
    import os

    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    engine = make_engine(url)
    names = set(inspect(engine).get_table_names())
    assert {
        "tasks",
        "task_events",
        "approvals",
        "effects",
        "tickets",
        "procedures",
        "users",
    } <= names
    assert "approval_audit" in names and "worker_heartbeats" in names


def test_creation_of_task_row_on_migrated_schema(tmp_path):
    engine = make_engine(sqlite_url(tmp_path / "rows.db"))
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    load_seed(factory, SEED_PATH)
    with factory() as s:
        s.add(
            Task(
                id="task-1",
                tenant_id="nimbo",
                requester_id="ines@nimbo",
                request="teste",
                status="queued",
                counters={},
                created_at=1.0,
                updated_at=1.0,
            )
        )
        s.commit()
        assert s.get(Task, "task-1").status == "queued"
    assert Path(tmp_path / "rows.db").exists()

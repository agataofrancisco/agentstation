"""Memoria: opt-in, escopo por tenant e utilizador, filtro de escrita, validade e eliminacao."""

from backend.app.agents.fake import FakeProvider
from backend.app.auth.security import Principal
from backend.app.graph.build import build_graph
from backend.app.graph.checkpointer import open_checkpointer
from backend.app.graph.runtime import GraphDeps
from backend.app.memory.filter import write_decision
from backend.app.memory.store import MemoryStore
from backend.app.service import create_task, initial_state, run_graph
from backend.app.store.models import TaskEvent, User
from tests.conftest import login, sqlite_url


def test_write_filter_blocks_password_example_from_spec():
    ok, reason = write_decision("a password temporaria e Xy7!abc", untrusted_origin=False)
    assert ok is False and reason == "secret"


def test_write_filter_blocks_personal_data_and_untrusted_origin():
    assert write_decision("contacto 912345678", untrusted_origin=False) == (False, "personal_data")
    assert write_decision("email ana@empresa.pt", untrusted_origin=False)[0] is False
    assert write_decision("resumo sem dados", untrusted_origin=True) == (False, "untrusted_origin")
    assert write_decision("VPN nao liga, procedimento PR-02", untrusted_origin=False) == (
        True,
        None,
    )


def test_store_isolates_tenants_and_users_and_expires(tmp_path):
    store = MemoryStore(str(tmp_path / "chroma"))
    now = 1_000_000.0
    store.add(
        tenant_id="nimbo",
        user_id="ines@nimbo",
        text="VPN PR-02 resolvida",
        source_task="t1",
        ttl_days=1,
        now=now,
    )
    store.add(
        tenant_id="atlas",
        user_id="marta@atlas",
        text="VPN PR-02 resolvida",
        source_task="t2",
        ttl_days=1,
        now=now,
    )
    hits = store.search(tenant_id="nimbo", user_id="ines@nimbo", query="VPN", now=now + 10)
    assert [m.source_task for m in hits] == ["t1"]
    assert store.search(tenant_id="nimbo", user_id="joao@nimbo", query="VPN", now=now) == []
    assert (
        store.search(tenant_id="nimbo", user_id="ines@nimbo", query="VPN", now=now + 2 * 86400)
        == []
    )


def test_memory_disabled_by_default_writes_nothing(app, settings, tmp_path):
    cfg = settings
    deps = GraphDeps(
        settings=cfg,
        session_factory=app.state.session_factory,
        llm=FakeProvider(),
        memory=MemoryStore(str(cfg.chroma_path)),
    )
    graph = build_graph(deps, open_checkpointer(sqlite_url(tmp_path / "cp.db")))
    joao = Principal("joao@nimbo", "nimbo", "requester", "joao@nimbo")
    with app.state.session_factory() as s:
        task = create_task(s, joao, "classifica o ticket T-101 e responde")
        state = initial_state(task, joao)
    run_graph(graph, deps, task.id, state)
    assert deps.memory.list_for_user(tenant_id="nimbo", user_id="joao@nimbo") == []


def test_opt_in_user_gets_memory_and_recall_is_recorded(app, settings, client, tmp_path):
    deps_memory = MemoryStore(str(settings.chroma_path))
    from backend.app.workers.runtime import configure

    cp = open_checkpointer(sqlite_url(tmp_path / "cp2.db"))
    rt = configure(settings, checkpointer=cp)
    rt.deps.memory = deps_memory
    rt.graph = build_graph(rt.deps, cp)
    ines = login(client, "ines@nimbo")
    r1 = client.post(
        "/tasks", json={"request": "classifica o ticket T-101 e responde"}, headers=ines
    )
    assert r1.status_code == 202
    mems = client.get("/memory", headers=ines).json()["items"]
    assert len(mems) == 1 and mems[0]["source_task"] == r1.json()["task_id"]
    r2 = client.post("/tasks", json={"request": "classifica o ticket T-101 de novo"}, headers=ines)
    with app.state.session_factory() as s:
        recalled = (
            s.query(TaskEvent).filter_by(task_id=r2.json()["task_id"], type="memory_recalled").all()
        )
        assert recalled and recalled[0].payload["memories"]


def test_secret_in_request_is_not_stored_and_is_recorded(app, settings, tmp_path):
    from backend.app.workers.runtime import configure

    cp = open_checkpointer(sqlite_url(tmp_path / "cp3.db"))
    rt = configure(settings, checkpointer=cp)
    rt.deps.memory = MemoryStore(str(settings.chroma_path))
    rt.graph = build_graph(rt.deps, cp)
    with app.state.session_factory() as s:
        s.get(User, "ines@nimbo").memory_enabled = True
        s.commit()
    ines = Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo")
    with app.state.session_factory() as s:
        task = create_task(s, ines, "classifica o ticket T-101; a password temporaria e Xy7!abc")
        state = initial_state(task, ines)
    run_graph(rt.graph, rt.deps, task.id, state)
    assert all(
        "Xy7" not in m.text
        for m in rt.deps.memory.list_for_user(tenant_id="nimbo", user_id="ines@nimbo")
    )
    with app.state.session_factory() as s:
        blocked = s.query(TaskEvent).filter_by(task_id=task.id, type="memory_write_blocked").all()
        assert blocked and blocked[0].payload["reason"] == "secret"


def test_user_can_delete_own_memory_and_others_get_404(client, settings):
    from backend.app.workers.runtime import configure

    store = MemoryStore(str(settings.chroma_path))
    configure(settings).deps.memory = store
    mid = store.add(
        tenant_id="nimbo", user_id="ines@nimbo", text="resumo", source_task="t9", ttl_days=3
    )
    joao = login(client, "joao@nimbo")
    ines = login(client, "ines@nimbo")
    assert client.delete(f"/memory/{mid}", headers=joao).status_code == 404
    assert client.delete(f"/memory/{mid}", headers=ines).status_code == 204
    assert client.delete(f"/memory/{mid}", headers=ines).status_code == 404
    assert client.get("/memory", headers=ines).json()["items"] == []

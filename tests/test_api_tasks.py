"""API de tarefas, aprovacoes, SSE, saude e metricas (execucao eager, sem worker externo)."""

import json

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.workers.heartbeat import beat
from tests.conftest import login


def create(
    client,
    headers,
    text="classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta",
):
    r = client.post("/tasks", json={"request": text}, headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["task_id"]


def pending_for(client, headers, task_id):
    return client.get(f"/tasks/{task_id}", headers=headers).json()["pending_approvals"]


def sse_events(client, headers, task_id, last_id=None):
    h = dict(headers)
    if last_id is not None:
        h["Last-Event-ID"] = str(last_id)
    events = []
    with client.stream("GET", f"/tasks/{task_id}/events", headers=h) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def test_endpoints_require_authentication(client):
    assert client.post("/tasks", json={"request": "x"}).status_code == 401
    assert client.get("/tasks/T-1").status_code == 401
    assert client.get("/approvals").status_code == 401
    assert client.get("/health").status_code == 200


def test_create_task_is_202_and_completes(client):
    h = login(client, "ines@nimbo")
    task_id = create(client, h)
    body = client.get(f"/tasks/{task_id}", headers=h).json()
    assert body["status"] == "completed"
    assert body["subtasks"] == ["triage", "knowledge_retrieval", "reporting"]
    assert body["counters"]["llm_calls"] >= 3


def test_requester_sees_only_own_tasks_reviewer_sees_tenant(client):
    ines = login(client, "ines@nimbo")
    joao = login(client, "joao@nimbo")
    rui = login(client, "rui@nimbo")
    task_id = create(client, ines)
    assert client.get(f"/tasks/{task_id}", headers=joao).status_code == 404
    assert client.get(f"/tasks/{task_id}", headers=rui).status_code == 200
    assert task_id in [t["id"] for t in client.get("/tasks", headers=rui).json()["items"]]
    assert task_id not in [t["id"] for t in client.get("/tasks", headers=joao).json()["items"]]


def test_other_tenant_and_missing_are_identical_404(client):
    ines = login(client, "ines@nimbo")
    marta = login(client, "marta@atlas")
    task_id = create(client, ines)
    cross = client.get(f"/tasks/{task_id}", headers=marta)
    missing = client.get("/tasks/tsk-nao-existe", headers=marta)
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_sse_streams_ordered_events_and_resumes_without_duplicates(client):
    h = login(client, "ines@nimbo")
    task_id = create(client, h)
    events = sse_events(client, h, task_id)
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))
    assert "task_finished" in [e["type"] for e in events]
    cut = seqs[len(seqs) // 2]
    resumed = sse_events(client, h, task_id, last_id=cut)
    assert [e["seq"] for e in resumed] == [s for s in seqs if s > cut]


def test_approval_flow_over_http(client):
    ines = login(client, "ines@nimbo")
    rui = login(client, "rui@nimbo")
    task_id = create(client, ines, "Faz reset de MFA para joao@nimbo, ticket T-105")
    assert client.get(f"/tasks/{task_id}", headers=ines).json()["status"] == "awaiting_approval"
    approval_id = pending_for(client, ines, task_id)[0]

    queue = client.get("/approvals", headers=rui).json()["items"]
    assert approval_id in [a["id"] for a in queue]
    assert client.get("/approvals", headers=ines).status_code == 403

    denied = client.post(
        f"/approvals/{approval_id}/resolve", json={"decision": "approve"}, headers=ines
    )
    assert denied.status_code == 403

    done = client.post(
        f"/approvals/{approval_id}/resolve", json={"decision": "approve"}, headers=rui
    )
    assert done.status_code == 200 and done.json()["changed"] is True
    assert client.get(f"/tasks/{task_id}", headers=ines).json()["status"] == "completed"

    again = client.post(
        f"/approvals/{approval_id}/resolve", json={"decision": "reject"}, headers=rui
    )
    assert again.json()["changed"] is False and again.json()["status"] == "approved"

    detail = client.get(f"/approvals/{approval_id}", headers=rui).json()
    assert [a["event"] for a in detail["audit"]].count("decided") == 1


def test_pending_approval_survives_api_restart(client, app, settings):
    ines = login(client, "ines@nimbo")
    task_id = create(client, ines, "Faz reset de MFA para joao@nimbo, ticket T-105")
    approval_id = pending_for(client, ines, task_id)[0]
    restarted = TestClient(create_app(settings))  # nova instancia da API, mesma base de dados
    rui_headers = login(restarted, "rui@nimbo")
    assert approval_id in [
        a["id"] for a in restarted.get("/approvals", headers=rui_headers).json()["items"]
    ]


def test_edit_over_http_changes_executed_days(client):
    ines = login(client, "ines@nimbo")
    rui = login(client, "rui@nimbo")
    task_id = create(client, ines, "suspende a conta ceo@nimbo por 30 dias, ticket T-120")
    approval_id = pending_for(client, ines, task_id)[0]
    r = client.post(
        f"/approvals/{approval_id}/resolve",
        json={"decision": "edit", "params": {"user_id": "ceo@nimbo", "days": 7}},
        headers=rui,
    )
    assert r.status_code == 200
    assert client.get(f"/tasks/{task_id}", headers=ines).json()["status"] == "completed"
    detail = client.get(f"/approvals/{approval_id}", headers=rui).json()
    assert detail["execution_result"]["days"] == 7
    assert detail["params"]["days"] == 7 and detail["original_params"]["days"] == 30


def test_health_reports_worker_down_then_ok_after_heartbeat(client, app, settings):
    strict = settings.model_copy(update={"celery_eager": False})
    strict_app = create_app(strict)
    tc = TestClient(strict_app)
    body = tc.get("/health").json()
    assert body["components"]["worker"] == "down"
    assert body["status"] == "degraded"
    beat(strict_app.state.session_factory)
    assert tc.get("/health").json()["components"]["worker"] == "ok"


def test_metrics_are_admin_only(client):
    assert client.get("/metrics", headers=login(client, "rui@nimbo")).status_code == 403
    assert client.get("/metrics", headers=login(client, "ada@nimbo")).status_code == 200

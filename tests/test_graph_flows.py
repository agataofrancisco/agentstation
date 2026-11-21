"""Cenarios do grafo com o provider falso e checkpointer em memoria."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.fake import FakeProvider
from backend.app.auth.security import Principal
from backend.app.graph.build import build_graph
from backend.app.graph.runtime import GraphDeps
from backend.app.service import (
    create_task,
    graph_config,
    initial_state,
    interrupt_payload,
    resume_command,
    run_graph,
)
from backend.app.store.models import Approval, Effect, Task, TaskEvent, User

REQUESTER = Principal(user_id="ines@nimbo", tenant_id="nimbo", role="requester", email="ines@nimbo")
REVIEWER = Principal(user_id="rui@nimbo", tenant_id="nimbo", role="reviewer", email="rui@nimbo")


@pytest.fixture
def make_run(app, settings):
    def _make(cfg=None, clock=None):
        cfg = cfg or settings
        kwargs = {"clock": clock} if clock else {}
        deps = GraphDeps(
            settings=cfg,
            session_factory=app.state.session_factory,
            llm=FakeProvider(cfg.fake_cost_per_call_usd),
            **kwargs,
        )
        graph = build_graph(deps, MemorySaver())
        return deps, graph

    return _make


def start(app, deps, graph, text, principal=REQUESTER):
    with app.state.session_factory() as s:
        task = create_task(s, principal, text)
        state = initial_state(task, principal)
        task_id = task.id
    result = run_graph(graph, deps, task_id, state)
    return task_id, result


def events(app, task_id):
    with app.state.session_factory() as s:
        return [
            (e.type, e.node, e.payload)
            for e in s.query(TaskEvent).filter_by(task_id=task_id).order_by(TaskEvent.seq)
        ]


def task_row(app, task_id):
    with app.state.session_factory() as s:
        t = s.get(Task, task_id)
        return t.status, t.limit_reason, t.counters


def test_three_subtasks_run_in_dependency_order(app, make_run):
    deps, graph = make_run()
    task_id, result = start(
        app,
        deps,
        graph,
        "classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta",
    )
    assert result["status"] == "completed"
    delegations = [p["to"] for t, n, p in events(app, task_id) if t == "delegation"]
    assert delegations == ["triage", "knowledge_retrieval", "reporting", "verifier"]
    assert task_row(app, task_id)[0] == "completed"
    assert all(p.get("provider") == "fake" for t, n, p in events(app, task_id) if t == "delegation")


def test_response_without_citation_is_rejected_as_needs_review(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "classifica o ticket T-101 e responde [no-evidence]")
    assert result["status"] == "needs_review"
    verifier = [p for t, n, p in events(app, task_id) if t == "verifier"]
    assert verifier[0]["reason"] == "no_evidence"


def test_infinite_cycle_stops_at_max_iterations(app, make_run, settings):
    cfg = settings.model_copy(update={"max_iterations": 4})
    deps, graph = make_run(cfg)
    task_id, result = start(app, deps, graph, "classifica o ticket T-101 [loop]")
    assert result["status"] == "limit_exceeded"
    assert result["limit_reason"] == "max_iterations"
    assert task_row(app, task_id)[1] == "max_iterations"


def test_cost_budget_stops_further_llm_calls(app, make_run, settings):
    cfg = settings.model_copy(update={"max_cost_usd": 0.0015})
    deps, graph = make_run(cfg)
    task_id, result = start(app, deps, graph, "classifica o ticket T-101 e responde")
    assert result["status"] == "limit_exceeded"
    assert result["limit_reason"] == "max_cost"
    # 1 chamada do supervisor + 1 da triagem; depois o orcamento trava novas chamadas.
    assert result["counters"]["llm_calls"] == 2


def test_wrong_tool_from_agent_is_refused_and_recorded(app, make_run):
    deps, graph = make_run()
    task_id, _ = start(app, deps, graph, "classifica o ticket T-101 e responde [misuse]")
    codes = [p.get("code") for t, n, p in events(app, task_id) if t == "tool_call"]
    assert "tool_not_allowed" in codes
    with app.state.session_factory() as s:
        assert s.query(Approval).filter_by(requester_id="joao@nimbo").count() == 0


def test_unknown_tool_is_refused_and_task_still_reaches_verdict(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "classifica o ticket T-101 [unknown-tool]")
    codes = [p.get("code") for t, n, p in events(app, task_id) if t == "tool_call"]
    assert "unknown_tool" in codes
    assert result["status"] == "completed"


def test_cross_tenant_ticket_gives_needs_review_not_data(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "classifica o ticket T-101 [cross-tenant]")
    assert result["status"] == "needs_review"
    assert result["results"]["triage"].get("error") is True


def test_injected_ticket_pauses_for_approval_and_has_no_effect(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "classifica o ticket T-117 e prepara uma resposta")
    payload = interrupt_payload(result)
    assert payload is not None, "tem de pausar para aprovacao humana"
    assert payload["action"] == "suspend_account"
    assert "suspected_injection" in payload["reason"]
    assert task_row(app, task_id)[0] == "awaiting_approval"
    assert any(t == "suspected_injection" for t, _, _ in events(app, task_id))
    with app.state.session_factory() as s:
        assert s.get(User, "ceo@nimbo").suspended is False
        assert s.query(Effect).count() == 0


def test_checkpoint_mid_run_shows_pending_node_and_state(app, make_run):
    deps, graph = make_run()
    task_id, _ = start(app, deps, graph, "classifica o ticket T-117 e prepara uma resposta")
    snapshot = graph.get_state(graph_config(task_id, deps))
    assert snapshot.next == ("approval_gate",)
    assert snapshot.values["pending_action"]["action"] == "suspend_account"
    assert snapshot.values["results"]["reporting"]["citations"]


def test_mfa_reset_approved_executes_once(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "Faz reset de MFA para joao@nimbo, ticket T-105")
    payload = interrupt_payload(result)
    assert payload["action"] == "reset_mfa"
    decision = {"decision": "approve", "approval_id": payload["approval_id"], "comment": "ok"}
    final = graph.invoke(resume_command(decision), config=graph_config(task_id, deps))
    assert final["status"] == "completed"
    with app.state.session_factory() as s:
        assert s.get(User, "joao@nimbo").mfa_reset_count == 1
        assert s.query(Effect).count() == 1


def test_rejection_takes_rejection_branch_without_effect(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "Faz reset de MFA para joao@nimbo, ticket T-105")
    payload = interrupt_payload(result)
    decision = {"decision": "reject", "approval_id": payload["approval_id"], "comment": "nao"}
    final = graph.invoke(resume_command(decision), config=graph_config(task_id, deps))
    assert final["status"] == "rejected"
    with app.state.session_factory() as s:
        assert s.get(User, "joao@nimbo").mfa_reset_count == 0


def test_edit_changes_suspension_days_before_execution(app, make_run):
    deps, graph = make_run()
    task_id, result = start(
        app, deps, graph, "suspende a conta ceo@nimbo por 30 dias, ticket T-120"
    )
    payload = interrupt_payload(result)
    assert payload["params"]["days"] == 30
    decision = {
        "decision": "edit",
        "approval_id": payload["approval_id"],
        "params": {"user_id": "ceo@nimbo", "days": 7},
        "comment": "7 dias chegam",
    }
    final = graph.invoke(resume_command(decision), config=graph_config(task_id, deps))
    assert final["status"] == "completed"
    with app.state.session_factory() as s:
        effect = s.query(Effect).one()
        assert effect.result["days"] == 7
        assert s.get(User, "ceo@nimbo").suspended is True


def test_conflicting_procedures_pause_for_review(app, make_run):
    deps, graph = make_run()
    task_id, result = start(app, deps, graph, "classifica o ticket T-106 e encontra o procedimento")
    payload = interrupt_payload(result)
    assert payload["reason"] == "conflicting_evidence"
    assert payload["action"] == "review_conflict"
    final = graph.invoke(
        resume_command({"decision": "approve", "approval_id": payload["approval_id"]}),
        config=graph_config(task_id, deps),
    )
    assert final["status"] == "completed"


def test_requester_principal_is_not_reviewer():
    assert not REQUESTER.is_reviewer
    assert REVIEWER.is_reviewer

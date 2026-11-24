"""Aprovacao (papeis, tenant, idempotencia, auditoria), efeitos e checkpoint SQLite."""

import pytest

from backend.app.agents.fake import FakeProvider
from backend.app.auth.security import Principal
from backend.app.graph.build import build_graph
from backend.app.graph.checkpointer import open_checkpointer
from backend.app.graph.control_nodes import make_execute_action
from backend.app.graph.runtime import GraphDeps
from backend.app.service import (
    ApprovalForbidden,
    ApprovalNotFound,
    create_task,
    resolve_approval,
)
from backend.app.store.models import Approval, ApprovalAudit, Effect, TaskEvent, User
from backend.app.workers import jobs
from backend.app.workers.runtime import Runtime
from tests.conftest import sqlite_url

REQUESTER = Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo")
REVIEWER = Principal("rui@nimbo", "nimbo", "reviewer", "rui@nimbo")
OTHER_TENANT = Principal("pedro@atlas", "atlas", "reviewer", "pedro@atlas")


@pytest.fixture
def runtime(app, settings, tmp_path):
    cp = open_checkpointer(sqlite_url(tmp_path / "cp.db"))
    deps = GraphDeps(
        settings=settings,
        session_factory=app.state.session_factory,
        llm=FakeProvider(),
    )
    return Runtime(settings=settings, deps=deps, graph=build_graph(deps, cp))


def new_task(app, text, principal=REQUESTER):
    with app.state.session_factory() as s:
        task = create_task(s, principal, text)
        return task.id


def pending_approval(app, task_id):
    with app.state.session_factory() as s:
        return s.query(Approval).filter_by(task_id=task_id).one()


def test_requester_cannot_resolve_even_own_approval(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    assert jobs.run_task_job(task_id, runtime) == "started"
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        with pytest.raises(ApprovalForbidden):
            resolve_approval(s, REQUESTER, approval.id, decision="approve")


def test_reviewer_cannot_approve_own_task(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105", REVIEWER)
    assert jobs.run_task_job(task_id, runtime) == "started"
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        with pytest.raises(ApprovalForbidden):
            resolve_approval(s, REVIEWER, approval.id, decision="approve")


def test_reviewer_from_other_tenant_gets_not_found(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    jobs.run_task_job(task_id, runtime)
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        with pytest.raises(ApprovalNotFound):
            resolve_approval(s, OTHER_TENANT, approval.id, decision="approve")


def test_second_resolution_is_idempotent_and_audited(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    jobs.run_task_job(task_id, runtime)
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        _, changed1 = resolve_approval(s, REVIEWER, approval.id, decision="approve")
        _, changed2 = resolve_approval(s, REVIEWER, approval.id, decision="reject")
        assert changed1 is True and changed2 is False
        events = [a.event for a in s.query(ApprovalAudit).filter_by(approval_id=approval.id)]
    assert events.count("decided") == 1
    assert "requested" in events


def test_edit_records_original_and_edited_values(app, runtime):
    task_id = new_task(app, "suspende a conta ceo@nimbo por 30 dias, ticket T-120")
    jobs.run_task_job(task_id, runtime)
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        resolve_approval(
            s,
            REVIEWER,
            approval.id,
            decision="edit",
            params={"user_id": "ceo@nimbo", "days": 7},
        )
        edited = s.query(ApprovalAudit).filter_by(approval_id=approval.id, event="edited").one()
    assert edited.payload["original"]["days"] == 30
    assert edited.payload["edited"]["days"] == 7


def test_full_approve_path_through_jobs_executes_once(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    assert jobs.run_task_job(task_id, runtime) == "started"
    approval = pending_approval(app, task_id)
    assert jobs.run_task_job(task_id, runtime) == "awaiting_approval"
    with app.state.session_factory() as s:
        resolve_approval(s, REVIEWER, approval.id, decision="approve")
    assert jobs.resume_task_job(task_id, approval.id, runtime) == "resumed"
    # Entrega duplicada da retoma: nao faz nada.
    assert jobs.resume_task_job(task_id, approval.id, runtime) == "not_waiting"
    with app.state.session_factory() as s:
        assert s.query(Effect).count() == 1
        assert s.get(User, "joao@nimbo").mfa_reset_count == 1
        executed = [e.type for e in s.query(TaskEvent).filter_by(task_id=task_id)]
    assert "effect_executed" in executed


def test_rejection_path_leaves_no_effect(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    jobs.run_task_job(task_id, runtime)
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        resolve_approval(s, REVIEWER, approval.id, decision="reject", comment="sem verificacao")
    assert jobs.resume_task_job(task_id, approval.id, runtime) == "resumed"
    with app.state.session_factory() as s:
        assert s.query(Effect).count() == 0
        assert s.get(User, "joao@nimbo").mfa_reset_count == 0


def test_reexecuting_execute_node_prevents_duplicate_effect(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    jobs.run_task_job(task_id, runtime)
    approval = pending_approval(app, task_id)
    with app.state.session_factory() as s:
        resolve_approval(s, REVIEWER, approval.id, decision="approve")
    state = {
        "task_id": task_id,
        "tenant_id": "nimbo",
        "user_id": "rui@nimbo",
        "role": "reviewer",
        "pending_action": {
            "approval_id": approval.id,
            "action": "reset_mfa",
            "params": {"user_id": "joao@nimbo"},
        },
        "approval_decision": {"decision": "approve"},
    }
    node = make_execute_action(runtime.deps)
    first = node(state)
    second = node(state)  # como apos um crash e reexecucao do no
    assert first["effect_result"] == second["effect_result"]
    with app.state.session_factory() as s:
        assert s.query(Effect).count() == 1
        assert s.get(User, "joao@nimbo").mfa_reset_count == 1
        types = [e.type for e in s.query(TaskEvent).filter_by(task_id=task_id)]
    assert "duplicate_effect_prevented" in types


def test_pending_effect_is_reconciled_once(app):
    import time

    from backend.app.store.models import Effect as E
    from backend.app.tools.effects import apply_effect, idempotency_key

    task_id, approval_id = "tsk-recon", "apr-recon"
    params = {"user_id": "joao@nimbo"}
    key = idempotency_key(task_id, approval_id, "reset_mfa", params)
    with app.state.session_factory() as s:
        s.add(
            E(
                idempotency_key=key,
                task_id=task_id,
                approval_id=approval_id,
                action="reset_mfa",
                params=params,
                status="effect_pending",
                created_at=time.time(),
            )
        )
        s.commit()
    result, outcome = apply_effect(
        app.state.session_factory,
        tenant_id="nimbo",
        task_id=task_id,
        approval_id=approval_id,
        action="reset_mfa",
        params=params,
    )
    assert outcome == "reconciled"
    assert result["mfa_reset_count"] == 1
    _, outcome2 = apply_effect(
        app.state.session_factory,
        tenant_id="nimbo",
        task_id=task_id,
        approval_id=approval_id,
        action="reset_mfa",
        params=params,
    )
    assert outcome2 == "duplicate"


def test_sqlite_checkpoint_shows_pending_approval(app, runtime):
    task_id = new_task(app, "Faz reset de MFA para joao@nimbo, ticket T-105")
    jobs.run_task_job(task_id, runtime)
    snap = runtime.graph.get_state({"configurable": {"thread_id": task_id}})
    assert snap.next == ("approval_gate",)
    assert snap.values["pending_action"]["action"] == "reset_mfa"


def test_edit_validation_rejects_out_of_range_days():
    from backend.app.service import InvalidDecision, validate_edit

    with pytest.raises(InvalidDecision):
        validate_edit("suspend_account", {"user_id": "ceo@nimbo", "days": 0})
    with pytest.raises(InvalidDecision):
        validate_edit("suspend_account", {"user_id": "ceo@nimbo", "days": True})

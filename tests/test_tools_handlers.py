"""Testes das 6 ferramentas: isolamento por tenant, efeitos simulados e idempotencia."""

import pytest

from backend.app.store.models import Effect, Ticket, User
from backend.app.tools.context import ToolContext
from backend.app.tools.effects import apply_effect, idempotency_key
from backend.app.tools.errors import ToolError
from backend.app.tools.executor import execute_tool
from backend.app.tools.injection import scan_untrusted
from tests.test_tools_executor import Recorder


def ctx_for(session, tenant="nimbo", agent="triage", user="ines@nimbo", role="requester"):
    rec = Recorder()
    return (
        ToolContext(
            tenant_id=tenant,
            user_id=user,
            role=role,
            task_id="task-h",
            agent=agent,
            session=session,
            emit=rec,
        ),
        rec,
    )


@pytest.fixture
def session(app):
    with app.state.session_factory() as s:
        yield s


def test_get_ticket_from_other_tenant_is_not_found(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    outcome = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "ATL-9"}})
    assert not outcome.ok and outcome.error == "not_found"


def test_get_ticket_missing_and_foreign_look_identical(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    foreign = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "ATL-9"}})
    missing = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "T-999"}})
    assert foreign.error == missing.error == "not_found"


def test_tenant_comes_from_context_not_from_arguments(session):
    # O modelo nao consegue escolher tenant: o campo extra e rejeitado e o tenant e o do contexto.
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    outcome = execute_tool(
        ctx, {"tool": "search_tickets", "args": {"query": "mfa", "tenant_id": "atlas"}}
    )
    assert outcome.error == "invalid_arguments"


def test_search_tickets_only_returns_own_tenant(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    outcome = execute_tool(ctx, {"tool": "search_tickets", "args": {"query": "mfa"}})
    ids = [item["id"] for item in outcome.data["items"]]
    assert ids and all(i.startswith("T-") for i in ids)
    assert "ATL-9" not in ids


def test_search_procedures_is_tenant_scoped(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="knowledge_retrieval")
    outcome = execute_tool(ctx, {"tool": "search_procedures", "args": {"query": "mfa"}})
    ids = {item["id"] for item in outcome.data["items"]}
    assert {"PR-05", "PR-06"} <= ids, "procedimentos contraditorios devem ser recuperados"
    assert "ATL-PR-01" not in ids


def test_draft_reply_rejects_citation_from_other_tenant(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="reporting")
    args = {"ticket_id": "T-101", "body": "Resposta", "citations": ["ATL-PR-01"]}
    outcome = execute_tool(ctx, {"tool": "draft_reply", "args": args})
    assert outcome.error == "invalid_citation"


def test_draft_reply_with_valid_citation_is_not_a_mutation(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="reporting")
    args = {"ticket_id": "T-101", "body": "Use o portal.", "citations": ["PR-01"]}
    outcome = execute_tool(ctx, {"tool": "draft_reply", "args": args})
    assert outcome.ok and outcome.data["citations"] == ["PR-01"]
    assert outcome.proposal is None


def test_proposal_does_not_change_data_until_effect_is_applied(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    args = {"ticket_id": "T-101", "status": "resolved", "justification": "fechar"}
    outcome = execute_tool(ctx, {"tool": "propose_ticket_status", "args": args})
    assert outcome.ok and outcome.proposal["action"] == "set_ticket_status"
    session.expire_all()
    assert session.get(Ticket, "T-101").status == "open"


def test_suspend_defaults_to_30_days(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    args = {"user_id": "ceo@nimbo", "action": "suspend", "justification": "revisao"}
    outcome = execute_tool(ctx, {"tool": "propose_account_action", "args": args})
    assert outcome.proposal["params"] == {"user_id": "ceo@nimbo", "days": 30}


def test_account_action_on_other_tenant_user_is_not_found(session):
    ctx, _ = ctx_for(session, tenant="nimbo", agent="triage")
    args = {"user_id": "marta@atlas", "action": "reset_mfa", "justification": "x"}
    outcome = execute_tool(ctx, {"tool": "propose_account_action", "args": args})
    assert outcome.error == "not_found"


def test_effect_is_applied_once_for_same_key(session):
    kwargs = dict(
        tenant_id="nimbo",
        task_id="task-e",
        approval_id="appr-1",
        action="reset_mfa",
        params={"user_id": "joao@nimbo"},
    )
    result1, created1 = apply_effect(session, **kwargs)
    result2, created2 = apply_effect(session, **kwargs)
    assert created1 is True and created2 is False
    assert result1 == result2 == {"user_id": "joao@nimbo", "mfa_reset_count": 1}
    assert session.query(Effect).count() == 1
    assert session.get(User, "joao@nimbo").mfa_reset_count == 1


def test_effect_key_depends_on_approval_and_params():
    base = idempotency_key("t", "a1", "reset_mfa", {"user_id": "x@nimbo"})
    assert base == idempotency_key("t", "a1", "reset_mfa", {"user_id": " x@nimbo "})
    assert base != idempotency_key("t", "a2", "reset_mfa", {"user_id": "x@nimbo"})
    assert base != idempotency_key("t", "a1", "reset_mfa", {"user_id": "y@nimbo"})


def test_effect_on_other_tenant_fails_without_side_effect(session):
    with pytest.raises(ToolError):
        apply_effect(
            session,
            tenant_id="nimbo",
            task_id="t",
            approval_id="a",
            action="reset_mfa",
            params={"user_id": "marta@atlas"},
        )
    assert session.query(Effect).count() == 0
    assert session.get(User, "marta@atlas").mfa_reset_count == 0


def test_malicious_ticket_is_flagged_as_suspected_injection(session):
    ctx, rec = ctx_for(session, tenant="nimbo", agent="triage")
    outcome = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "T-117"}})
    assert outcome.ok
    assert "auto_approve" in outcome.suspicious
    assert any(t == "suspected_injection" for t, _ in rec.events)


def test_scan_untrusted_on_clean_text_is_empty():
    assert scan_untrusted({"body": "A VPN nao liga desde ontem."}) == []

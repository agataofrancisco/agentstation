"""Testes do executor de ferramentas: allowlist, validacao, ordem das verificacoes e eventos."""

from dataclasses import replace

import pytest

from backend.app.tools.context import ToolContext
from backend.app.tools.executor import execute_tool
from backend.app.tools.registry import REGISTRY, agent_tools


class Recorder:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))

    def codes(self) -> list[str]:
        return [p.get("code") for t, p in self.events if t == "tool_call" and p.get("code")]


def make_ctx(session, *, agent="triage", tenant="nimbo", user="ines@nimbo", role="requester"):
    rec = Recorder()
    ctx = ToolContext(
        tenant_id=tenant,
        user_id=user,
        role=role,
        task_id="task-test",
        agent=agent,
        session=session,
        emit=rec,
    )
    return ctx, rec


@pytest.fixture
def session(app):
    with app.state.session_factory() as s:
        yield s


def spy_handler(monkeypatch, name):
    """Substitui o handler por um espiao que falha se for chamado (sem acesso a dados)."""
    calls = []

    def boom(ctx, args):
        calls.append(args)
        raise AssertionError("handler nao devia ser chamado")

    monkeypatch.setitem(REGISTRY, name, replace(REGISTRY[name], handler=boom))
    return calls


def test_allowlist_has_six_tools_with_declared_mutating_flag():
    assert set(REGISTRY) == {
        "search_tickets",
        "get_ticket",
        "search_procedures",
        "draft_reply",
        "propose_ticket_status",
        "propose_account_action",
    }
    mutating = {name for name, spec in REGISTRY.items() if spec.mutating}
    assert mutating == {"propose_ticket_status", "propose_account_action"}


def test_reporting_agent_cannot_reach_account_actions():
    tools = agent_tools()
    assert "propose_account_action" in tools["triage"]
    assert "propose_account_action" not in tools["reporting"]


def test_unknown_tool_is_refused_and_recorded(session, monkeypatch):
    ctx, rec = make_ctx(session)
    outcome = execute_tool(ctx, {"tool": "delete_all_tickets", "args": {}})
    assert not outcome.ok and outcome.error == "unknown_tool"
    assert "unknown_tool" in rec.codes()


def test_invalid_ticket_id_fails_before_any_data_access(session, monkeypatch):
    calls = spy_handler(monkeypatch, "get_ticket")
    ctx, rec = make_ctx(session, agent="triage")
    outcome = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "nao valido"}})
    assert outcome.error == "invalid_arguments"
    assert calls == []
    failing = [p for t, p in rec.events if p.get("code") == "invalid_arguments"]
    assert failing and failing[0]["fields"] == ["ticket_id"]
    assert "nao valido" not in str(rec.events), "o valor enviado nao deve ser ecoado"


def test_extra_fields_are_rejected(session):
    ctx, _ = make_ctx(session, agent="triage")
    outcome = execute_tool(
        ctx, {"tool": "get_ticket", "args": {"ticket_id": "T-101", "tenant": "atlas"}}
    )
    assert outcome.error == "invalid_arguments"


def test_reporting_calling_account_action_is_tool_not_allowed(session, monkeypatch):
    calls = spy_handler(monkeypatch, "propose_account_action")
    ctx, rec = make_ctx(session, agent="reporting")
    args = {"user_id": "joao@nimbo", "action": "reset_mfa", "justification": "teste"}
    outcome = execute_tool(ctx, {"tool": "propose_account_action", "args": args})
    assert outcome.error == "tool_not_allowed"
    assert outcome.proposal is None
    assert calls == []
    assert "tool_not_allowed" in rec.codes()


def test_non_list_call_is_invalid(session):
    ctx, _ = make_ctx(session)
    assert execute_tool(ctx, "get_ticket").error == "invalid_call"


def test_ok_call_emits_tool_call_event_with_duration(session):
    ctx, rec = make_ctx(session, agent="triage")
    outcome = execute_tool(ctx, {"tool": "get_ticket", "args": {"ticket_id": "T-101"}})
    assert outcome.ok and outcome.data["id"] == "T-101"
    ok_events = [p for t, p in rec.events if t == "tool_call" and p.get("status") == "ok"]
    assert ok_events and ok_events[0]["tool"] == "get_ticket"
    assert ok_events[0]["duration_ms"] >= 0

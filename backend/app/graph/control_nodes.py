"""Nos de controlo: supervisor, verificador, porta de aprovacao, efeito e fecho."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from backend.app.agents.llm import LLMError
from backend.app.graph.limits import check_limits
from backend.app.graph.runtime import GraphDeps, emit_for
from backend.app.graph.state import TaskState
from backend.app.store.approvals import add_reason, create_or_get
from backend.app.store.models import Approval
from backend.app.tools.effects import apply_effect
from backend.app.tools.errors import ToolError

ALLOWED_ROUTES = ("triage", "knowledge_retrieval", "reporting", "verifier", "finalize")


def make_supervisor(deps: GraphDeps):
    def supervisor(state: TaskState) -> dict:
        counters: dict[str, Any] = dict(state.get("counters") or {})
        counters["iterations"] = counters.get("iterations", 0) + 1
        reason = check_limits(
            counters, started_at=state["started_at"], now=deps.clock(), settings=deps.settings
        )
        if reason:
            return {
                "counters": counters,
                "next": "finalize",
                "status": "limit_exceeded",
                "limit_reason": reason,
            }
        with deps.session_factory() as session:
            emit = emit_for(session, state, node="supervisor", agent="supervisor")
            if counters.get("iterations") == 1:
                _recall(deps, session, state, emit)
            try:
                resp = deps.llm.generate(
                    "supervisor",
                    {
                        "request": state.get("request", ""),
                        "done": list(state.get("done") or []),
                    },
                )
            except LLMError as exc:
                emit("llm_error", {"code": str(exc)})
                return {"counters": counters, "next": "finalize", "status": "failed"}
            counters["llm_calls"] = counters.get("llm_calls", 0) + 1
            counters["tokens"] = counters.get("tokens", 0) + resp.tokens
            counters["cost_usd"] = round(counters.get("cost_usd", 0.0) + resp.cost_usd, 6)
            nxt = resp.payload.get("next")
            if nxt not in ALLOWED_ROUTES:
                emit("route_rejected", {"code": "invalid_route"})
                return {
                    "counters": counters,
                    "next": "finalize",
                    "status": "failed",
                    "error": "invalid_route",
                }
            emit("delegation", {"to": nxt, "provider": resp.provider})
        return {"counters": counters, "next": nxt}

    return supervisor


def _verdict(state: TaskState) -> tuple[str, str | None]:
    results = state.get("results") or {}
    triage = results.get("triage") or {}
    knowledge = results.get("knowledge_retrieval") or {}
    reporting = results.get("reporting") or {}
    if not all(isinstance(r, dict) for r in (triage, knowledge, reporting)):
        return "needs_review", "incomplete"
    if triage.get("error") or knowledge.get("error") or reporting.get("error"):
        return "needs_review", "incomplete"
    citations = reporting.get("citations") or []
    evidence = knowledge.get("procedure_ids") or []
    if not citations or not set(citations) <= set(evidence):
        return "needs_review", "no_evidence"
    return "ok", None


def make_verifier(deps: GraphDeps):
    def verifier(state: TaskState) -> dict:
        verdict, reason = _verdict(state)
        update: dict[str, Any] = {}
        with deps.session_factory() as session:
            emit = emit_for(session, state, node="verifier", agent="verifier")
            if verdict == "needs_review":
                update.update({"verdict": "needs_review", "status": "needs_review"})
                emit("verifier", {"verdict": "needs_review", "reason": reason})
                return update

            knowledge = (state.get("results") or {}).get("knowledge_retrieval") or {}
            pending = state.get("pending_action")
            flags = list(state.get("flags") or [])
            conflict = bool(knowledge.get("conflict"))
            reasons: list[str] = []
            if pending:
                approval = session.get(Approval, pending["approval_id"])
                if conflict:
                    add_reason(session, approval, "conflicting_evidence")
                    reasons.append("conflicting_evidence")
                if "suspected_injection" in flags:
                    add_reason(session, approval, "suspected_injection")
                    reasons.append("suspected_injection")
                approval_id = pending["approval_id"]
                reasons.insert(0, "mutating_action")
                needs_approval = True
            elif conflict:
                approval = create_or_get(
                    session,
                    task_id=state["task_id"],
                    tenant_id=state["tenant_id"],
                    requester_id=state["user_id"],
                    kind="review",
                    action="review_conflict",
                    params={"procedure_ids": knowledge.get("procedure_ids", [])},
                    justification="Procedimentos recuperados dão instruções contraditórias.",
                    evidence=list(knowledge.get("procedure_ids", [])),
                    reason="conflicting_evidence",
                )
                approval_id = approval.id
                reasons.append("conflicting_evidence")
                needs_approval = True
            else:
                approval_id = None
                needs_approval = False

            if needs_approval:
                update.update({"verdict": "needs_approval", "approval_id": approval_id})
            else:
                update.update({"verdict": "ok"})
            emit("verifier", {"verdict": update["verdict"], "reasons": reasons})
        return update

    return verifier


def route_after_verifier(state: TaskState) -> str:
    verdict = state.get("verdict")
    if verdict == "needs_approval":
        return "approval_gate"
    return "finalize"


def make_approval_gate(deps: GraphDeps):
    def approval_gate(state: TaskState) -> dict:
        # Sem efeitos neste no: ao retomar, o no e reexecutado desde o inicio (ver docs/learn/04).
        approval_id = state.get("approval_id")
        with deps.session_factory() as session:
            approval = session.get(Approval, approval_id)
            payload = {
                "approval_id": approval_id,
                "kind": approval.kind,
                "action": approval.action,
                "params": dict(approval.params),
                "reason": approval.reason,
                "justification": approval.justification,
                "evidence": list(approval.evidence),
            }
        decision = interrupt(payload)
        return {"approval_decision": decision}

    return approval_gate


def route_after_gate(state: TaskState) -> str:
    decision = (state.get("approval_decision") or {}).get("decision")
    if decision == "reject":
        return "finalize"
    if state.get("pending_action"):
        return "execute_action"
    return "finalize"


def make_execute_action(deps: GraphDeps):
    def execute_action(state: TaskState) -> dict:
        pending = state["pending_action"]
        decision = state.get("approval_decision") or {}
        params = decision.get("params") or pending["params"]
        with deps.session_factory() as session:
            emit = emit_for(session, state, node="execute_action", agent="execute_action")
            if decision.get("params") and decision["params"] != pending["params"]:
                emit("approval_edited", {"original": pending["params"], "edited": params})
            try:
                result, outcome = apply_effect(
                    deps.session_factory,
                    tenant_id=state["tenant_id"],
                    task_id=state["task_id"],
                    approval_id=pending["approval_id"],
                    action=pending["action"],
                    params=params,
                )
            except ToolError as exc:
                emit("effect_failed", {"action": pending["action"], "code": exc.code})
                return {"status": "failed", "error": exc.code}
            event = {
                "executed": "effect_executed",
                "duplicate": "duplicate_effect_prevented",
                "reconciled": "effect_reconciled",
            }[outcome]
            emit(event, {"action": pending["action"], "result": result})
            approval = session.get(Approval, pending["approval_id"])
            approval.execution_result = result
            session.commit()
        return {"effect_result": result}

    return execute_action


def make_finalize(deps: GraphDeps):
    def finalize(state: TaskState) -> dict:
        decision = (state.get("approval_decision") or {}).get("decision")
        status = state.get("status")
        if not status:
            status = "rejected" if decision == "reject" else "completed"
        with deps.session_factory() as session:
            emit = emit_for(session, state, node="finalize", agent="finalize")
            if status == "completed":
                _remember(deps, session, state, emit)
            emit("task_finished", {"status": status, "limit_reason": state.get("limit_reason")})
        return {"status": status}

    return finalize


def _memory_enabled(session, user_id: str) -> bool:
    from backend.app.store.models import User

    user = session.get(User, user_id)
    return bool(user and user.memory_enabled)


def _recall(deps: GraphDeps, session, state: TaskState, emit) -> None:
    if deps.memory is None or not _memory_enabled(session, state["user_id"]):
        return
    hits = deps.memory.search(
        tenant_id=state["tenant_id"], user_id=state["user_id"], query=state.get("request", "")
    )
    emit(
        "memory_recalled",
        {
            "memories": [{"id": m.id, "text": m.text, "source_task": m.source_task} for m in hits],
            "reason": "similaridade semantica com o pedido, dentro da validade",
        },
    )


def _remember(deps: GraphDeps, session, state: TaskState, emit) -> None:
    from backend.app.memory.filter import write_decision

    if deps.memory is None or not _memory_enabled(session, state["user_id"]):
        return
    results = state.get("results") or {}
    triage = results.get("triage") or {}
    knowledge = results.get("knowledge_retrieval") or {}
    summary = (
        f"Ticket {triage.get('ticket_id')}; "
        f"procedimentos: {', '.join(knowledge.get('procedure_ids') or [])}"
    )
    candidate = f"{state.get('request', '')} | {summary}"
    untrusted = "suspected_injection" in (state.get("flags") or [])
    allowed, reason = write_decision(candidate, untrusted_origin=untrusted)
    if not allowed:
        emit("memory_write_blocked", {"reason": reason})
        return
    mem_id = deps.memory.add(
        tenant_id=state["tenant_id"],
        user_id=state["user_id"],
        text=candidate,
        source_task=state["task_id"],
        ttl_days=deps.settings.memory_ttl_days,
        memory_id=f"mem-{state['task_id']}",  # idempotente se o no for reexecutado
    )
    emit("memory_written", {"memory_id": mem_id})

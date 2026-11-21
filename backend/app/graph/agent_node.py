"""No de agente: ate MAX_AGENT_STEPS chamadas ao LLM; ferramentas passam pelo executor."""

from __future__ import annotations

from typing import Any

from backend.app.agents.llm import LLMError
from backend.app.graph.limits import check_limits
from backend.app.graph.runtime import GraphDeps, emit_for
from backend.app.graph.state import TaskState
from backend.app.store.approvals import create_or_get
from backend.app.tools.context import ToolContext
from backend.app.tools.executor import execute_tool

MAX_AGENT_STEPS = 3


def build_prompt(agent: str, state: TaskState, observations: list[dict]) -> dict[str, Any]:
    return {
        "agent": agent,
        "request": state.get("request", ""),
        "results": state.get("results") or {},
        "done": list(state.get("done") or []),
        "observations": observations,
    }


def make_agent_node(name: str, deps: GraphDeps):
    def agent_node(state: TaskState) -> dict:
        counters: dict[str, Any] = dict(state.get("counters") or {})
        results = dict(state.get("results") or {})
        flags = list(state.get("flags") or [])
        pending = state.get("pending_action")
        approval_id = state.get("approval_id")
        observations: list[dict] = []
        result: dict | None = None

        with deps.session_factory() as session:
            emit = emit_for(session, state, node=name, agent=name)
            ctx = ToolContext(
                tenant_id=state["tenant_id"],
                user_id=state["user_id"],
                role=state["role"],
                task_id=state["task_id"],
                agent=name,
                session=session,
                emit=emit,
            )
            for _ in range(MAX_AGENT_STEPS):
                reason = check_limits(
                    counters,
                    started_at=state["started_at"],
                    now=deps.clock(),
                    settings=deps.settings,
                )
                if reason:
                    break
                try:
                    resp = deps.llm.generate(name, build_prompt(name, state, observations))
                except LLMError as exc:
                    emit("llm_error", {"code": str(exc)})
                    break
                counters["llm_calls"] = counters.get("llm_calls", 0) + 1
                counters["tokens"] = counters.get("tokens", 0) + resp.tokens
                counters["cost_usd"] = round(counters.get("cost_usd", 0.0) + resp.cost_usd, 6)
                emit(
                    "llm_call",
                    {"provider": resp.provider, "tokens": resp.tokens, "cost_usd": resp.cost_usd},
                )

                calls = resp.payload.get("tool_calls")
                calls = calls if isinstance(calls, list) else []
                for call in calls:
                    if counters.get("tool_calls", 0) >= deps.settings.max_tool_calls:
                        break
                    outcome = execute_tool(ctx, call)
                    counters["tool_calls"] = counters.get("tool_calls", 0) + 1
                    if outcome.suspicious and "suspected_injection" not in flags:
                        flags.append("suspected_injection")
                    if outcome.ok and outcome.proposal is not None:
                        proposal = outcome.proposal
                        approval = create_or_get(
                            session,
                            task_id=state["task_id"],
                            tenant_id=state["tenant_id"],
                            requester_id=state["user_id"],
                            kind="action",
                            action=proposal["action"],
                            params=proposal["params"],
                            justification=proposal["justification"],
                            evidence=proposal["evidence"],
                            reason="mutating_action",
                        )
                        pending = {
                            "approval_id": approval.id,
                            "action": proposal["action"],
                            "params": proposal["params"],
                        }
                        approval_id = approval.id
                        observations.append({"tool": outcome.tool, "proposed": True})
                    else:
                        observations.append(
                            {
                                "tool": outcome.tool,
                                "error": outcome.error,
                                "data": outcome.data,
                            }
                        )

                payload_result = resp.payload.get("result")
                if not calls and isinstance(payload_result, dict):
                    result = payload_result
                    break

        results[name] = result if result is not None else {"error": "no_result"}
        return {
            "results": results,
            "done": [*list(state.get("done") or []), name],
            "counters": counters,
            "flags": flags,
            "pending_action": pending,
            "approval_id": approval_id,
        }

    return agent_node

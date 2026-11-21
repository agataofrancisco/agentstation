"""Estado do grafo. Guarda apenas dados serializaveis (vai para o checkpointer)."""

from __future__ import annotations

from typing import Any, TypedDict


class Counters(TypedDict, total=False):
    iterations: int
    llm_calls: int
    tool_calls: int
    tokens: int
    cost_usd: float


class TaskState(TypedDict, total=False):
    task_id: str
    tenant_id: str
    user_id: str
    role: str
    request: str
    started_at: float
    counters: Counters
    next: str
    done: list[str]
    results: dict[str, Any]
    flags: list[str]
    pending_action: dict[str, Any] | None
    approval_id: str | None
    approval_decision: dict[str, Any] | None
    effect_result: dict[str, Any] | None
    verdict: str
    status: str
    limit_reason: str | None
    error: str | None
    provider: str

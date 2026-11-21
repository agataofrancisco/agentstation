"""Limites rigidos por tarefa. Funcao pura: recebe contadores e devolve o motivo ou None."""

from __future__ import annotations

from backend.app.config import Settings


def check_limits(
    counters: dict,
    *,
    started_at: float,
    now: float,
    settings: Settings,
) -> str | None:
    if counters.get("iterations", 0) > settings.max_iterations:
        return "max_iterations"
    if counters.get("tool_calls", 0) >= settings.max_tool_calls:
        return "max_tool_calls"
    if now - started_at > settings.max_seconds:
        return "max_seconds"
    if counters.get("tokens", 0) >= settings.max_tokens:
        return "max_tokens"
    if counters.get("cost_usd", 0.0) >= settings.max_cost_usd:
        return "max_cost"
    return None

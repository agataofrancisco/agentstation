"""Executor central: allowlist -> validacao de argumentos -> autorizacao -> execucao -> saida.

Ordem fixa: nada toca nos dados antes de a chamada passar pela allowlist, pelo schema e pelo papel.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from backend.app.tools.context import ToolContext
from backend.app.tools.errors import ToolError
from backend.app.tools.injection import scan_untrusted
from backend.app.tools.registry import REGISTRY


@dataclass
class ToolOutcome:
    tool: str | None
    ok: bool
    error: str | None = None
    data: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    suspicious: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


def _fail(ctx: ToolContext, tool: Any, code: str, start: float) -> ToolOutcome:
    duration = (perf_counter() - start) * 1000
    name = tool if isinstance(tool, str) else None
    ctx.emit(
        "tool_call",
        {
            "agent": ctx.agent,
            "tool": name,
            "status": "error",
            "code": code,
            "duration_ms": round(duration, 3),
        },
    )
    return ToolOutcome(tool=name, ok=False, error=code, duration_ms=duration)


def _invalid_fields(exc: ValidationError) -> list[str]:
    # Apenas os nomes dos campos: os valores enviados pelo modelo nunca voltam a ser ecoados.
    return sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})


def execute_tool(ctx: ToolContext, call: Any) -> ToolOutcome:
    start = perf_counter()
    if not isinstance(call, Mapping):
        return _fail(ctx, None, "invalid_call", start)
    name = call.get("tool")
    if not isinstance(name, str) or name not in REGISTRY:
        return _fail(ctx, name, "unknown_tool", start)
    spec = REGISTRY[name]
    if ctx.agent not in spec.allowed_agents:
        return _fail(ctx, name, "tool_not_allowed", start)
    if ctx.role not in spec.allowed_roles:
        return _fail(ctx, name, "forbidden", start)

    raw_args = call.get("args")
    if raw_args is None:
        raw_args = {}
    if not isinstance(raw_args, Mapping):
        return _fail(ctx, name, "invalid_arguments", start)
    try:
        args = spec.input_model.model_validate(dict(raw_args))
    except ValidationError as exc:
        ctx.emit(
            "tool_call",
            {
                "agent": ctx.agent,
                "tool": name,
                "status": "error",
                "code": "invalid_arguments",
                "fields": _invalid_fields(exc),
            },
        )
        return ToolOutcome(tool=name, ok=False, error="invalid_arguments")

    try:
        raw = spec.handler(ctx, args)
        data = spec.output_model.model_validate(raw).model_dump()
    except ToolError as exc:
        return _fail(ctx, name, exc.code, start)

    suspicious = scan_untrusted(data)
    duration = (perf_counter() - start) * 1000
    if suspicious:
        ctx.emit(
            "suspected_injection",
            {"agent": ctx.agent, "tool": name, "patterns": suspicious},
        )
    ctx.emit(
        "tool_call",
        {
            "agent": ctx.agent,
            "tool": name,
            "status": "ok",
            "mutating": spec.mutating,
            "duration_ms": round(duration, 3),
        },
    )
    if spec.mutating:
        return ToolOutcome(
            tool=name,
            ok=True,
            proposal=data,
            suspicious=suspicious,
            duration_ms=duration,
        )
    return ToolOutcome(tool=name, ok=True, data=data, suspicious=suspicious, duration_ms=duration)

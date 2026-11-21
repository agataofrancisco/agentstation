"""Contexto de execucao de uma ferramenta: identidade do requester (nunca vinda do modelo)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    user_id: str
    role: str
    task_id: str
    agent: str
    session: Session
    emit: EmitFn

"""Registo de eventos da tarefa (linha temporal). Ordenados por `seq` autoincrementado."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from backend.app.store.models import TaskEvent


def add_event(
    session: Session,
    *,
    task_id: str,
    tenant_id: str,
    type_: str,
    node: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
    duration_ms: float | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    event = TaskEvent(
        task_id=task_id,
        tenant_id=tenant_id,
        type=type_,
        node=node,
        agent=agent,
        tool=tool,
        duration_ms=duration_ms,
        payload=dict(payload or {}),
        created_at=time.time(),
    )
    session.add(event)
    session.commit()
    return event.seq


def list_events(session: Session, task_id: str, after_seq: int = 0) -> list[TaskEvent]:
    return (
        session.query(TaskEvent)
        .filter(TaskEvent.task_id == task_id, TaskEvent.seq > after_seq)
        .order_by(TaskEvent.seq)
        .all()
    )

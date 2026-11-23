"""Tarefas: criar, consultar (com escopo por papel) e SSE com Last-Event-ID."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_session
from backend.app.api.views import OPEN_STATUSES, event_view, task_view
from backend.app.auth.deps import get_principal
from backend.app.auth.security import Principal
from backend.app.service import create_task
from backend.app.store.events import list_events
from backend.app.store.models import Approval, Task
from backend.app.workers.enqueue import enqueue_run

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskIn(BaseModel):
    request: str = Field(min_length=1, max_length=2000)


def _visible(task: Task | None, principal: Principal) -> Task:
    """Requester ve so as suas; reviewer/admin veem o tenant; outro tenant ou inexistente -> 404."""
    if task is None or task.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if not principal.is_reviewer and task.requester_id != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return task


def _pending_ids(session: Session, task_id: str) -> list[str]:
    rows = session.query(Approval.id).filter_by(task_id=task_id, status="pending").all()
    return [r[0] for r in rows]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create(
    body: TaskIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    task = create_task(session, principal, body.request.strip())
    enqueue_run(request.app.state.settings, task.id)
    session.refresh(task)
    return {"task_id": task.id, "status": task.status}


@router.get("")
def list_tasks(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    query = session.query(Task).filter(Task.tenant_id == principal.tenant_id)
    if not principal.is_reviewer:
        query = query.filter(Task.requester_id == principal.user_id)
    tasks = query.order_by(Task.created_at.desc()).limit(100).all()
    return {"items": [task_view(t) for t in tasks]}


@router.get("/{task_id}")
def get_task(
    task_id: str,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    task = _visible(session.get(Task, task_id), principal)
    return task_view(task, _pending_ids(session, task.id))


def _terminal_or_waiting(session_factory, task_id: str) -> bool:
    with session_factory() as s:
        task = s.get(Task, task_id)
        return task is None or task.status not in OPEN_STATUSES


async def _event_stream(request: Request, task_id: str, after: int) -> AsyncIterator[str]:
    session_factory = request.app.state.session_factory
    last = after
    while True:
        with session_factory() as s:
            rows = list_events(s, task_id, after_seq=last)
            events = [event_view(e) for e in rows]
        for ev in events:
            last = ev["seq"]
            data = json.dumps(ev, ensure_ascii=False)
            yield (f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {data}\n\n")
        if not events and _terminal_or_waiting(session_factory, task_id):
            # Fecha ao terminar ou ao esperar aprovacao; o cliente reconecta com Last-Event-ID.
            return
        if await request.is_disconnected():
            return
        await asyncio.sleep(0.25)


@router.get("/{task_id}/events")
def stream_events(
    task_id: str,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> Response:
    _visible(session.get(Task, task_id), principal)
    raw = request.headers.get("last-event-id", "0")
    after = int(raw) if raw.isdigit() else 0
    return StreamingResponse(
        _event_stream(request, task_id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

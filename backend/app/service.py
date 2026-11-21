"""Servico de tarefas: criar, executar/retomar o grafo e persistir o resultado na tarefa.

Regra: thread_id do checkpointer = id da tarefa. So o grafo altera o estado da execucao.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from langgraph.types import Command
from sqlalchemy.orm import Session

from backend.app.auth.security import Principal
from backend.app.graph.build import recursion_limit_for
from backend.app.graph.runtime import GraphDeps
from backend.app.graph.state import TaskState
from backend.app.store.events import add_event
from backend.app.store.models import Task

TERMINAL = {"completed", "rejected", "failed", "limit_exceeded", "needs_review"}


def create_task(session: Session, principal: Principal, request: str, clock=time.time) -> Task:
    now = clock()
    task = Task(
        id=f"tsk-{uuid.uuid4().hex[:20]}",
        tenant_id=principal.tenant_id,
        requester_id=principal.user_id,
        request=request,
        status="queued",
        counters={},
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.commit()
    add_event(
        session,
        task_id=task.id,
        tenant_id=task.tenant_id,
        type_="task_queued",
        payload={"requester": principal.user_id},
    )
    return task


def initial_state(task: Task, principal: Principal, clock=time.time) -> TaskState:
    return {
        "task_id": task.id,
        "tenant_id": task.tenant_id,
        "user_id": principal.user_id,
        "role": principal.role,
        "request": task.request,
        "started_at": clock(),
        "counters": {
            "iterations": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "tokens": 0,
            "cost_usd": 0.0,
        },
        "done": [],
        "results": {},
        "flags": [],
        "pending_action": None,
        "approval_id": None,
        "approval_decision": None,
        "effect_result": None,
        "status": "",
        "limit_reason": None,
        "error": None,
    }


def graph_config(task_id: str, deps: GraphDeps) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": task_id},
        "recursion_limit": recursion_limit_for(deps),
    }


def run_graph(graph, deps: GraphDeps, task_id: str, payload: Any) -> dict[str, Any]:
    """payload: TaskState inicial, None (continuar checkpoint) ou Command(resume=...)."""
    config = graph_config(task_id, deps)
    result = graph.invoke(payload, config=config)
    persist_outcome(deps, task_id, result)
    return result


def persist_outcome(deps: GraphDeps, task_id: str, result: dict[str, Any]) -> None:
    with deps.session_factory() as session:
        task = session.get(Task, task_id)
        if task is None:
            return
        if "__interrupt__" in result:
            task.status = "awaiting_approval"
        else:
            task.status = result.get("status") or "running"
            task.limit_reason = result.get("limit_reason")
            task.plan = list(result.get("done") or [])
            task.results = result.get("results") or {}
        task.counters = dict(result.get("counters") or {})
        task.updated_at = deps.clock()
        session.commit()


def mark_running(deps: GraphDeps, task_id: str) -> None:
    with deps.session_factory() as session:
        task = session.get(Task, task_id)
        if task is not None and task.status not in TERMINAL:
            task.status = "running"
            task.updated_at = deps.clock()
            session.commit()


def interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    items = result.get("__interrupt__") or []
    if not items:
        return None
    value = getattr(items[0], "value", None)
    return value if isinstance(value, dict) else None


def resume_command(decision: dict[str, Any]) -> Command:
    return Command(resume=decision)

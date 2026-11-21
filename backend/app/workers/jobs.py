"""Trabalhos do grafo (funcoes puras, sem Celery). Celery apenas os invoca (ver tasks.py).

- run_task_job: primeira execucao, ou continuacao a partir do checkpoint depois de um crash.
- resume_task_job: retoma com a decisao humana persistida na base de dados (nunca vinda da fila).
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Command

from backend.app.auth.security import Principal
from backend.app.service import graph_config, initial_state, mark_running, run_graph
from backend.app.store.models import Approval, Task, User
from backend.app.workers.runtime import Runtime, current


def principal_for(session, task: Task) -> Principal:
    user = session.get(User, task.requester_id)
    if user is None:
        raise LookupError("requester inexistente")
    return Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email)


def _waiting_for_approval(snapshot) -> bool:
    return any(getattr(task, "interrupts", ()) for task in snapshot.tasks)


def run_task_job(task_id: str, rt: Runtime | None = None) -> str:
    rt = rt or current()
    with rt.deps.session_factory() as session:
        task = session.get(Task, task_id)
        if task is None:
            return "missing"
        principal = principal_for(session, task)
        task_obj = task
    config = graph_config(task_id, rt.deps)
    snapshot = rt.graph.get_state(config)
    if _waiting_for_approval(snapshot):
        return "awaiting_approval"
    if snapshot.values and not snapshot.next:
        return "already_finished"
    mark_running(rt.deps, task_id)
    if snapshot.values:  # ha checkpoint: continuar do ultimo passo guardado
        run_graph(rt.graph, rt.deps, task_id, None)
        return "resumed_from_checkpoint"
    state = initial_state(task_obj, principal, clock=rt.deps.clock)
    run_graph(rt.graph, rt.deps, task_id, state)
    return "started"


def resume_task_job(task_id: str, approval_id: str, rt: Runtime | None = None) -> str:
    rt = rt or current()
    with rt.deps.session_factory() as session:
        approval = session.get(Approval, approval_id)
        if approval is None or approval.task_id != task_id:
            return "missing"
        if approval.status == "pending":
            return "not_decided"
        decision: dict[str, Any] = {
            "decision": approval.decision,
            "approval_id": approval.id,
            "params": dict(approval.params) if approval.decision == "edit" else None,
            "comment": approval.decision_comment,
        }
    snapshot = rt.graph.get_state(graph_config(task_id, rt.deps))
    if not _waiting_for_approval(snapshot):
        return "not_waiting"  # ja retomada: retoma duplicada e inofensiva
    run_graph(rt.graph, rt.deps, task_id, Command(resume=decision))
    return "resumed"

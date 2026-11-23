"""Serializacao das respostas da API. Nunca devolve campos internos (ex.: hashes de chaves)."""

from __future__ import annotations

from typing import Any

from backend.app.store.models import Approval, ApprovalAudit, Task, TaskEvent

TERMINAL_STATUSES = ("completed", "rejected", "failed", "limit_exceeded", "needs_review")
OPEN_STATUSES = ("queued", "running")


def task_view(task: Task, pending_approvals: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": task.id,
        "tenant_id": task.tenant_id,
        "requester_id": task.requester_id,
        "request": task.request,
        "status": task.status,
        "limit_reason": task.limit_reason,
        "subtasks": list(task.plan or []),
        "results": task.results or {},
        "counters": task.counters or {},
        "pending_approvals": list(pending_approvals or []),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def approval_view(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "task_id": approval.task_id,
        "tenant_id": approval.tenant_id,
        "requester_id": approval.requester_id,
        "kind": approval.kind,
        "action": approval.action,
        "params": dict(approval.params or {}),
        "original_params": dict(approval.original_params or {}),
        "justification": approval.justification,
        "evidence": list(approval.evidence or []),
        "reason": approval.reason,
        "status": approval.status,
        "decision": approval.decision,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at,
        "decision_comment": approval.decision_comment,
        "execution_result": approval.execution_result,
        "created_at": approval.created_at,
    }


def audit_view(row: ApprovalAudit) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "event": row.event,
        "actor_id": row.actor_id,
        "payload": dict(row.payload or {}),
        "created_at": row.created_at,
    }


def event_view(event: TaskEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "type": event.type,
        "node": event.node,
        "agent": event.agent,
        "tool": event.tool,
        "duration_ms": event.duration_ms,
        "payload": dict(event.payload or {}),
        "created_at": event.created_at,
    }

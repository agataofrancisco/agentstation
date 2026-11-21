"""Repositorio de aprovacoes. Criacao idempotente (id derivado) e auditoria apenas de insercao."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from backend.app.store.models import Approval, ApprovalAudit


def approval_id_for(task_id: str, kind: str, action: str, params: dict[str, Any]) -> str:
    canonical = json.dumps([task_id, kind, action, params], sort_keys=True, separators=(",", ":"))
    return "apr-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def audit(session: Session, approval: Approval, actor_id: str, event: str, payload: dict) -> None:
    session.add(
        ApprovalAudit(
            approval_id=approval.id,
            tenant_id=approval.tenant_id,
            actor_id=actor_id,
            event=event,
            payload=dict(payload),
            created_at=time.time(),
        )
    )


def create_or_get(
    session: Session,
    *,
    task_id: str,
    tenant_id: str,
    requester_id: str,
    kind: str,
    action: str,
    params: dict[str, Any],
    justification: str,
    evidence: list[str],
    reason: str,
) -> Approval:
    """Se o no for reexecutado devolve a aprovacao existente, sem duplicar."""
    app_id = approval_id_for(task_id, kind, action, params)
    existing = session.get(Approval, app_id)
    if existing is not None:
        return existing
    approval = Approval(
        id=app_id,
        task_id=task_id,
        tenant_id=tenant_id,
        requester_id=requester_id,
        kind=kind,
        action=action,
        params=dict(params),
        original_params=dict(params),
        justification=justification,
        evidence=list(evidence),
        reason=reason,
        status="pending",
        created_at=time.time(),
    )
    session.add(approval)
    session.flush()
    audit(session, approval, requester_id, "requested", {"reason": reason, "action": action})
    session.commit()
    return approval


def add_reason(session: Session, approval: Approval, reason: str) -> None:
    """Acrescenta motivo a uma aprovacao ainda pendente (ex.: conflito mais proposta mutavel)."""
    if approval.status != "pending" or reason in approval.reason.split("+"):
        return
    approval.reason = f"{approval.reason}+{reason}"
    audit(session, approval, "system", "reason_added", {"reason": reason})
    session.commit()

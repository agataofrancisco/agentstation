"""Aprovacoes: fila para revisores, consulta com auditoria e resolucao."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_session
from backend.app.api.views import approval_view, audit_view
from backend.app.auth.deps import get_principal, require_reviewer
from backend.app.auth.security import Principal
from backend.app.service import (
    ApprovalForbidden,
    ApprovalNotFound,
    InvalidDecision,
    resolve_approval,
)
from backend.app.store.models import Approval, ApprovalAudit
from backend.app.workers.enqueue import enqueue_resume

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ResolveIn(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    params: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=1000)


@router.get("")
def list_approvals(
    status_filter: str = "pending",
    principal: Principal = Depends(require_reviewer),
    session: Session = Depends(get_session),
) -> dict:
    query = session.query(Approval).filter(Approval.tenant_id == principal.tenant_id)
    if status_filter != "all":
        query = query.filter(Approval.status == status_filter)
    rows = query.order_by(Approval.created_at).limit(200).all()
    return {"items": [approval_view(a) for a in rows]}


@router.get("/{approval_id}")
def get_approval(
    approval_id: str,
    principal: Principal = Depends(require_reviewer),
    session: Session = Depends(get_session),
) -> dict:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    audit = (
        session.query(ApprovalAudit)
        .filter_by(approval_id=approval_id)
        .order_by(ApprovalAudit.seq)
        .all()
    )
    return {**approval_view(approval), "audit": [audit_view(a) for a in audit]}


@router.post("/{approval_id}/resolve")
def resolve(
    approval_id: str,
    body: ResolveIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    try:
        approval, changed = resolve_approval(
            session,
            principal,
            approval_id,
            decision=body.decision,
            params=body.params,
            comment=body.comment,
        )
    except ApprovalNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    except ApprovalForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from exc
    except InvalidDecision as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if changed:
        enqueue_resume(request.app.state.settings, approval.task_id, approval.id)
    return {**approval_view(approval), "changed": changed}

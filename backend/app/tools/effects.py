"""Sistema simulado com registo de efeitos. Nenhum sistema externo e contactado.

A chave de idempotencia e derivada de (task_id, approval_id, action, params normalizados),
por isso a mesma aprovacao nunca produz dois efeitos.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from backend.app.store.models import Effect, Ticket, User
from backend.app.tools.errors import ToolError


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(params):
        value = params[key]
        out[key] = value.strip() if isinstance(value, str) else value
    return out


def idempotency_key(task_id: str, approval_id: str, action: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(
        [task_id, approval_id, action, normalize_params(params)],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _perform(session: Session, tenant_id: str, action: str, params: dict[str, Any]) -> dict:
    if action == "set_ticket_status":
        ticket = session.get(Ticket, params.get("ticket_id"))
        if ticket is None or ticket.tenant_id != tenant_id:
            raise ToolError("not_found")
        ticket.status = params["status"]
        return {"ticket_id": ticket.id, "status": ticket.status}
    if action in ("reset_mfa", "suspend_account", "unsuspend_account"):
        user = session.get(User, params.get("user_id"))
        if user is None or user.tenant_id != tenant_id:
            raise ToolError("not_found")
        if action == "reset_mfa":
            user.mfa_reset_count += 1
            return {"user_id": user.id, "mfa_reset_count": user.mfa_reset_count}
        user.suspended = action == "suspend_account"
        result: dict[str, Any] = {"user_id": user.id, "suspended": user.suspended}
        if user.suspended:
            result["days"] = params.get("days")
        return result
    raise ToolError("unknown_action")


def apply_effect(
    session: Session,
    *,
    tenant_id: str,
    task_id: str,
    approval_id: str,
    action: str,
    params: dict[str, Any],
) -> tuple[dict, bool]:
    """Aplica o efeito no maximo uma vez. Devolve (resultado, criado_agora)."""
    key = idempotency_key(task_id, approval_id, action, params)
    existing = session.query(Effect).filter(Effect.idempotency_key == key).one_or_none()
    if existing is not None:
        return dict(existing.result or {}), False
    result = _perform(session, tenant_id, action, normalize_params(params))
    now = time.time()
    session.add(
        Effect(
            idempotency_key=key,
            task_id=task_id,
            approval_id=approval_id,
            action=action,
            params=normalize_params(params),
            status="done",
            result=result,
            created_at=now,
            completed_at=now,
        )
    )
    session.commit()
    return result, True

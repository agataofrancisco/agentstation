"""Sistema simulado com registo de efeitos. Nenhum sistema externo e contactado.

Duas fases (ver docs/learn/05):
  1. INSERT do registo `effect_pending` (com chave UNIQUE) e commit: marca a intencao.
  2. Uma transaccao: aplicar a alteracao + marcar `done` com o resultado. Ou ambas ou nenhuma.
Se o processo morrer entre as fases, a linha `effect_pending` e reconciliada na retoma.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.store.models import Effect, Task, Ticket, User
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
    session_factory: sessionmaker,
    *,
    tenant_id: str,
    task_id: str,
    approval_id: str,
    action: str,
    params: dict[str, Any],
) -> tuple[dict, str]:
    """Aplica o efeito no maximo uma vez.

    Devolve (resultado, estado) com estado em {"executed", "duplicate", "reconciled"}.
    """
    params = normalize_params(params)
    key = idempotency_key(task_id, approval_id, action, params)

    with session_factory() as s:
        existing = s.query(Effect).filter(Effect.idempotency_key == key).one_or_none()
        if existing is not None and existing.status == "done":
            return dict(existing.result or {}), "duplicate"
        pending_before = existing is not None
        if existing is None:
            s.add(
                Effect(
                    idempotency_key=key,
                    task_id=task_id,
                    approval_id=approval_id,
                    action=action,
                    params=params,
                    status="effect_pending",
                    created_at=time.time(),
                )
            )
            try:
                s.commit()  # fase 1: intencao durável
            except IntegrityError:
                s.rollback()
                return apply_effect(
                    session_factory,
                    tenant_id=tenant_id,
                    task_id=task_id,
                    approval_id=approval_id,
                    action=action,
                    params=params,
                )

        try:
            result = _perform(
                s, tenant_id, action, params
            )  # fase 2: efeito + done na mesma transaccao
        except ToolError:
            s.rollback()
            row = s.query(Effect).filter(Effect.idempotency_key == key).one()
            row.status = "failed"
            row.completed_at = time.time()
            s.commit()
            raise
        row = s.query(Effect).filter(Effect.idempotency_key == key).one()
        row.status = "done"
        row.result = result
        row.completed_at = time.time()
        s.commit()
    return result, "reconciled" if pending_before else "executed"


def reconcile_pending(session_factory: sessionmaker) -> list[str]:
    """Na arranque: refaz os efeitos `effect_pending` (o simulado e atomico)."""
    done: list[str] = []
    with session_factory() as s:
        pending = s.query(Effect).filter(Effect.status == "effect_pending").all()
        items = [
            (e.idempotency_key, e.task_id, e.approval_id, e.action, dict(e.params)) for e in pending
        ]
    for key, task_id, approval_id, action, params in items:
        with session_factory() as s:
            task = s.get(Task, task_id)
            tenant = task.tenant_id if task is not None else None
        if tenant is None:
            continue
        try:
            apply_effect(
                session_factory,
                tenant_id=tenant,
                task_id=task_id,
                approval_id=approval_id,
                action=action,
                params=params,
            )
            done.append(key)
        except ToolError:
            continue
    return done

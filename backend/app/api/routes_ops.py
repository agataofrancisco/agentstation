"""Saude (API, base de dados, fila, worker) e metricas (so admin)."""

from __future__ import annotations

import time
from collections import Counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_session
from backend.app.auth.deps import require_roles
from backend.app.auth.security import Principal
from backend.app.store.models import Approval, Effect, Task, TaskEvent
from backend.app.workers.heartbeat import worker_alive

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    components: dict[str, str] = {"api": "ok"}
    try:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            components["database"] = "ok"
            alive = worker_alive(s, settings.worker_heartbeat_ttl_s)
    except Exception:  # noqa: BLE001 - a saude nunca deve rebentar; reporta o componente
        components["database"] = "down"
        alive = False
    components["queue"] = "eager" if settings.celery_eager else "configured"
    if settings.celery_eager:
        components["worker"] = "eager"  # sem processo separado (testes e demo)
    else:
        components["worker"] = "ok" if alive else "down"
    overall = "degraded" if "down" in components.values() else "ok"
    return {"status": overall, "components": components}


@router.get("/metrics")
def metrics(
    principal: Principal = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> dict:
    tasks = session.query(Task).filter(Task.tenant_id == principal.tenant_id).all()
    by_status = Counter(t.status for t in tasks)
    n = len(tasks) or 1
    calls = [t.counters or {} for t in tasks]
    approvals = session.query(Approval).filter(Approval.tenant_id == principal.tenant_id).all()
    decided = [a for a in approvals if a.decided_at is not None]
    waits = []
    for a in decided:
        task = session.get(Task, a.task_id)
        if task is not None:
            waits.append(a.decided_at - task.created_at)
    duplicates = (
        session.query(TaskEvent)
        .filter(
            TaskEvent.tenant_id == principal.tenant_id,
            TaskEvent.type == "duplicate_effect_prevented",
        )
        .count()
    )
    return {
        "generated_at": time.time(),
        "provider_note": "valores medidos na base de dados; custo pode ser estimado (fake)",
        "tasks_by_status": dict(by_status),
        "avg_llm_calls_per_task": round(sum(c.get("llm_calls", 0) for c in calls) / n, 3),
        "avg_tool_calls_per_task": round(sum(c.get("tool_calls", 0) for c in calls) / n, 3),
        "total_cost_usd_estimated": round(sum(c.get("cost_usd", 0.0) for c in calls), 6),
        "avg_seconds_to_decision": round(sum(waits) / len(waits), 3) if waits else None,
        "duplicate_effects_prevented": duplicates,
        "effects_done": session.query(Effect).filter(Effect.status == "done").count(),
    }

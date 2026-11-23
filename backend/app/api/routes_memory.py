"""Memoria do proprio utilizador: listar e eliminar. Nunca de outros utilizadores."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.app.auth.deps import get_principal
from backend.app.auth.security import Principal
from backend.app.memory.store import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])


def _store(request: Request) -> MemoryStore:
    from backend.app.workers.runtime import current

    return current(request.app.state.settings).deps.memory


@router.get("")
def list_memory(request: Request, principal: Principal = Depends(get_principal)) -> dict:
    items = _store(request).list_for_user(tenant_id=principal.tenant_id, user_id=principal.user_id)
    return {
        "items": [
            {
                "id": m.id,
                "text": m.text,
                "source_task": m.source_task,
                "created_at": m.created_at,
                "expires_at": m.expires_at,
            }
            for m in items
        ]
    }


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    ok = _store(request).delete(
        tenant_id=principal.tenant_id, user_id=principal.user_id, memory_id=memory_id
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

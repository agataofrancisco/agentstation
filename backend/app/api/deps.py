"""Dependencias partilhadas pelos routers: sessao de base de dados e acesso com escopo."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_scoped_or_404[T](session: Session, model: type[T], object_id: str, tenant_id: str) -> T:
    """Devolve o registo se for do tenant; senao 404 (nunca 403, para nao revelar existencia)."""
    row = session.get(model, object_id)
    if row is None or getattr(row, "tenant_id", None) != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return row

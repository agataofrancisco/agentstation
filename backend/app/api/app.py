"""Fabrica da aplicacao FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes_auth import router as auth_router
from backend.app.config import Settings, get_settings
from backend.app.store.db import Base, make_engine, make_session_factory


def create_app(settings: Settings | None = None, *, create_tables: bool = False) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(title="AgentStation", version="0.1.0")
    engine = make_engine(cfg.database_url)
    if create_tables:
        # Producao: esquema pelas migracoes Alembic. create_all serve testes e demos locais.
        Base.metadata.create_all(engine)
    app.state.settings = cfg
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    app.include_router(auth_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "api": "ok"}

    return app

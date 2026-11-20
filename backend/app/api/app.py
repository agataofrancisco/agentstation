"""Fabrica da aplicacao FastAPI."""

from fastapi import FastAPI

from backend.app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(title="AgentStation", version="0.1.0")
    app.state.settings = cfg

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "api": "ok"}

    return app

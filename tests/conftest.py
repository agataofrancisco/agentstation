from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.config import Settings
from backend.app.seed import load_seed

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "demo" / "seed.json"


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=sqlite_url(tmp_path / "app.db"),
        checkpoint_url=sqlite_url(tmp_path / "checkpoints.db"),
        chroma_path=str(tmp_path / "chroma"),
        celery_eager=True,
        demo_mode=True,
    )


@pytest.fixture
def app(settings, tmp_path):
    from backend.app.graph.checkpointer import open_checkpointer
    from backend.app.workers.runtime import configure

    application = create_app(settings, create_tables=True)
    load_seed(application.state.session_factory, SEED_PATH)
    # Execucao eager (sem worker): o runtime do processo usa checkpointer SQLite de teste.
    configure(settings, checkpointer=open_checkpointer(sqlite_url(tmp_path / "cp.db")))
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

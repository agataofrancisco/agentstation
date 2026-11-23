from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.config import Settings


def test_health_reports_components(tmp_path):
    cfg = Settings(
        celery_eager=True,
        database_url=f"sqlite:///{(tmp_path / 'h.db').as_posix()}",
    )
    client = TestClient(create_app(cfg, create_tables=True))
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["components"]["database"] == "ok"
    assert body["components"]["worker"] == "eager"
    assert body["status"] == "ok"

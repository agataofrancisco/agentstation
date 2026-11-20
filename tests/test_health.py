from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.config import Settings


def test_health_minimal():
    client = TestClient(create_app(Settings()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

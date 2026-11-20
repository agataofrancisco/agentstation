from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends

from backend.app.api.deps import get_scoped_or_404
from backend.app.auth.deps import get_principal, require_roles
from backend.app.auth.security import ALGORITHM, Principal
from backend.app.store.models import Ticket
from tests.conftest import login


def test_missing_token_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_is_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer nao-e-jwt"})
    assert response.status_code == 401


def test_expired_token_is_401(client, app):
    payload = {
        "sub": "ines@nimbo",
        "tenant": "nimbo",
        "role": "requester",
        "email": "ines@nimbo",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    token = jwt.encode(payload, app.state.settings.jwt_secret, algorithm=ALGORITHM)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_signed_with_other_secret_is_401(client, app):
    payload = {"sub": "ines@nimbo", "tenant": "nimbo", "role": "admin", "email": "ines@nimbo"}
    token = jwt.encode(payload, "outro-segredo", algorithm=ALGORITHM)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_login_returns_persona_identity(client):
    headers = login(client, "ines@nimbo")
    me = client.get("/auth/me", headers=headers).json()
    assert me == {
        "id": "ines@nimbo",
        "tenant_id": "nimbo",
        "role": "requester",
        "email": "ines@nimbo",
    }


def test_unknown_persona_is_401(client):
    assert client.post("/auth/login", json={"email": "ninguem@nimbo"}).status_code == 401


def test_login_disabled_outside_demo_mode(settings, app):
    from fastapi.testclient import TestClient

    app.state.settings = settings.model_copy(update={"demo_mode": False})
    response = TestClient(app).post("/auth/login", json={"email": "ines@nimbo"})
    assert response.status_code == 404


def test_role_guard_returns_403_for_requester(client, app):
    @app.get("/probe/reviewer")
    def probe(principal: Principal = Depends(require_roles("reviewer", "admin"))):
        return {"ok": principal.user_id}

    assert client.get("/probe/reviewer", headers=login(client, "ines@nimbo")).status_code == 403
    assert client.get("/probe/reviewer", headers=login(client, "rui@nimbo")).status_code == 200


def test_cross_tenant_object_is_404_like_missing(client, app):
    @app.get("/probe/tickets/{ticket_id}")
    def probe(ticket_id: str, principal: Principal = Depends(get_principal)):
        with app.state.session_factory() as session:
            row = get_scoped_or_404(session, Ticket, ticket_id, principal.tenant_id)
            return {"id": row.id}

    headers = login(client, "ines@nimbo")  # tenant nimbo
    assert client.get("/probe/tickets/T-101", headers=headers).status_code == 200
    cross = client.get("/probe/tickets/ATL-1", headers=headers)
    missing = client.get("/probe/tickets/NAO-EXISTE", headers=headers)
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()

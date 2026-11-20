"""JWT demo com papeis e tenant. Validado em cada pedido; nunca se confia em dados do cliente."""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt

from backend.app.config import Settings

ROLES = ("requester", "reviewer", "admin")
ALGORITHM = "HS256"


class InvalidToken(Exception):
    """Token ausente, mal formado, expirado ou com assinatura invalida."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    email: str

    @property
    def is_reviewer(self) -> bool:
        return self.role in ("reviewer", "admin")


def issue_token(principal: Principal, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": principal.user_id,
        "tenant": principal.tenant_id,
        "role": principal.role,
        "email": principal.email,
        "iat": now,
        "exp": now + settings.jwt_ttl_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, settings: Settings) -> Principal:
    if not isinstance(token, str) or not token:
        raise InvalidToken("missing")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    role = claims.get("role")
    if role not in ROLES:
        raise InvalidToken("unknown role")
    user_id, tenant_id, email = claims.get("sub"), claims.get("tenant"), claims.get("email")
    if not all(isinstance(v, str) and v for v in (user_id, tenant_id, email)):
        raise InvalidToken("malformed claims")
    return Principal(user_id=user_id, tenant_id=tenant_id, role=role, email=email)

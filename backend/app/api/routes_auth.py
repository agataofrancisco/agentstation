"""Login demo por persona (sem palavra-passe: apenas DEMO_MODE) e identidade actual."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_session
from backend.app.auth.deps import get_principal
from backend.app.auth.security import Principal, issue_token
from backend.app.store.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


@router.post("/login")
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)) -> dict:
    settings = request.app.state.settings
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    user = session.query(User).filter(User.email == body.email.strip().lower()).one_or_none()
    if user is None or user.suspended:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown persona")
    principal = Principal(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email
    )
    return {
        "access_token": issue_token(principal, settings),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "email": user.email,
            "display_name": user.display_name,
        },
    }


@router.get("/me")
def me(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "role": principal.role,
        "email": principal.email,
    }

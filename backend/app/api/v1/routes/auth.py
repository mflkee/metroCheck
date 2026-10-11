"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import (
    create_access_token,
    get_admin_info,
    verify_admin,
)
from app.core.config import settings
from app.api.v1.dependencies.auth import get_current_user
from app.services import accounts_client

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str | None = None
    username: str | None = None  # legacy field, treated as an email too
    password: str

    @property
    def identifier(self) -> str:
        return (self.email or self.username or "").strip()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    identifier = payload.identifier

    if accounts_client.is_enabled():
        identity = await accounts_client.verify(email=identifier, password=payload.password)
        token = create_access_token(
            data={
                "sub": "admin",
                "email": identity["email"],
                "name": identity["name"],
                "auth_method": "registry",
            }
        )
        return LoginResponse(
            access_token=token,
            user={
                "username": identity["email"],
                "role": "admin",
                "email": identity["email"],
                "name": identity["name"],
                "auth_method": "registry",
            },
        )

    if not verify_admin(identifier, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(data={"sub": "admin"})
    return LoginResponse(
        access_token=token,
        user=get_admin_info(),
    )


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return current_user

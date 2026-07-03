"""Authentication endpoints."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import verify_admin, create_access_token, get_admin_info
from app.api.v1.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    if not verify_admin(payload.username, payload.password):
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

"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.auth import (
    create_access_token,
    create_signed_payload,
    decode_signed_payload,
    get_admin_info,
    verify_admin,
)
from app.core.config import settings
from app.api.v1.dependencies.auth import get_current_user
from app.services import oidc_service
from app.services import accounts_client
from app.services.oidc_service import OidcError, OidcTransaction

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


# --------------------------------------------------------------------------- #
# Single sign-on (Authentik OIDC)
# --------------------------------------------------------------------------- #


@router.get("/oidc/status")
async def oidc_status() -> dict[str, bool]:
    """Whether the frontend should offer the "sign in with MKAIR" button."""

    return {"enabled": oidc_service.is_enabled()}


@router.get("/oidc/login")
async def oidc_login() -> RedirectResponse:
    """Start the SSO flow: remember the transaction in a signed cookie and go to Authentik."""

    try:
        url, transaction = await oidc_service.build_login_url()
    except OidcError as exc:
        return RedirectResponse(oidc_service.frontend_error_url(exc.code), status_code=302)

    cookie = create_signed_payload(
        transaction, ttl_seconds=settings.OIDC_TRANSACTION_TTL_SECONDS
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        oidc_service.OIDC_COOKIE,
        cookie,
        max_age=settings.OIDC_TRANSACTION_TTL_SECONDS,
        httponly=True,
        secure=settings.OIDC_COOKIE_SECURE,
        samesite="lax",
        path=oidc_service.OIDC_COOKIE_PATH,
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    """Finish the SSO flow and hand the app's own token back to the frontend."""

    cookie = request.cookies.get(oidc_service.OIDC_COOKIE)
    if not cookie:
        return RedirectResponse(oidc_service.frontend_error_url("missing_txn"), status_code=302)

    try:
        payload = decode_signed_payload(cookie)
        transaction = OidcTransaction(
            state=str(payload["state"]),
            nonce=str(payload["nonce"]),
            code_verifier=str(payload["code_verifier"]),
        )
    except (KeyError, TypeError, ValueError):
        return RedirectResponse(oidc_service.frontend_error_url("bad_txn"), status_code=302)

    try:
        identity = await oidc_service.resolve_callback(
            code=code,
            state=state,
            transaction=transaction,
        )
    except OidcError as exc:
        return RedirectResponse(oidc_service.frontend_error_url(exc.code), status_code=302)

    token = create_access_token(
        data={
            "sub": "admin",
            "email": identity["email"],
            "name": identity["name"],
            "auth_method": "oidc",
        }
    )
    response = RedirectResponse(oidc_service.frontend_success_url(token=token), status_code=302)
    response.delete_cookie(oidc_service.OIDC_COOKIE, path=oidc_service.OIDC_COOKIE_PATH)
    return response

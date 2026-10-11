"""Single sign-on against Authentik (OpenID Connect, authorization code + PKCE).

metroCheck keeps a single administrator account and has no user table. Through SSO
any member of the ``metrocheck-*`` groups in Authentik gets the same full access,
and the app still issues its own JWT so every existing guard keeps working.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import settings

OIDC_COOKIE = "metrocheck_oidc_txn"
OIDC_COOKIE_PATH = "/api/v1/auth/oidc"

ACCESS_GROUP = "metrocheck-users"
ACCESS_GROUP_PREFIX = "metrocheck-"

_DISCOVERY_TTL_SECONDS = 3600


class OidcError(Exception):
    """A user-facing failure of the SSO flow; carries a short machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _Discovery:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    fetched_at: float


@dataclass(frozen=True)
class OidcTransaction:
    state: str
    nonce: str
    code_verifier: str


_discovery: _Discovery | None = None
_jwks: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0


def is_enabled() -> bool:
    return bool(settings.OIDC_ENABLED and settings.OIDC_CLIENT_SECRET)


async def build_login_url() -> tuple[str, dict[str, str]]:
    """Return the Authentik authorize URL plus the transaction we must remember."""

    if not is_enabled():
        raise OidcError("disabled", "Single sign-on is not enabled.")

    discovery = await _get_discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_challenge(code_verifier)

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.OIDC_CLIENT_ID,
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "scope": settings.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{discovery.authorization_endpoint}?{query}", {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
    }


async def resolve_callback(*, code: str, state: str, transaction: OidcTransaction) -> dict[str, str]:
    """Exchange the code, verify the identity token and return the identity."""

    if not is_enabled():
        raise OidcError("disabled", "Single sign-on is not enabled.")
    if not code:
        raise OidcError("no_code", "Authentik did not return an authorization code.")
    if not state or not secrets.compare_digest(state, transaction.state):
        raise OidcError("bad_state", "The login session is invalid or has expired.")

    tokens = await _exchange_code(code=code, code_verifier=transaction.code_verifier)
    id_token = tokens.get("id_token")
    if not id_token:
        raise OidcError("no_id_token", "Authentik did not return an identity token.")

    claims = await _verify_id_token(id_token, nonce=transaction.nonce)

    groups = _claim_groups(claims)
    if not _has_access(groups):
        raise OidcError("no_access", "Учётная запись не имеет доступа к metroCheck.")

    email = str(claims.get("email") or "").strip()
    if not email:
        raise OidcError("no_email", "Authentik did not provide an email address.")

    name = str(claims.get("name") or claims.get("preferred_username") or email).strip()
    return {"email": email, "name": name}


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #


def _has_access(groups: list[str]) -> bool:
    if ACCESS_GROUP in groups:
        return True
    return any(group.startswith(ACCESS_GROUP_PREFIX) for group in groups)


def _claim_groups(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("groups")
    if isinstance(raw, str):
        return [item for item in (part.strip() for part in raw.split(",")) if item]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


async def _get_discovery() -> _Discovery:
    global _discovery
    if _discovery is not None and time.monotonic() - _discovery.fetched_at < _DISCOVERY_TTL_SECONDS:
        return _discovery

    url = f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=settings.OIDC_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            document = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("discovery_failed", "Не удалось связаться с сервером входа.") from exc

    _discovery = _Discovery(
        authorization_endpoint=document["authorization_endpoint"],
        token_endpoint=document["token_endpoint"],
        jwks_uri=document["jwks_uri"],
        fetched_at=time.monotonic(),
    )
    return _discovery


async def _exchange_code(*, code: str, code_verifier: str) -> dict[str, Any]:
    discovery = await _get_discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
        "code_verifier": code_verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.OIDC_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(discovery.token_endpoint, data=data)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("token_exchange_failed", "Не удалось завершить вход.") from exc


async def _get_jwks(jwks_uri: str, *, force: bool = False) -> dict[str, Any]:
    global _jwks, _jwks_fetched_at
    fresh = _jwks is not None and time.monotonic() - _jwks_fetched_at < 300
    if fresh and not force:
        return _jwks

    try:
        async with httpx.AsyncClient(timeout=settings.OIDC_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
            _jwks = response.json()
            _jwks_fetched_at = time.monotonic()
            return _jwks
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("discovery_failed", "Не удалось получить ключи сервера входа.") from exc


def _select_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    keys = jwks.get("keys") or []
    for key in keys:
        if kid is None or key.get("kid") == kid:
            return key
    return keys[0] if keys else None


async def _verify_id_token(id_token: str, *, nonce: str) -> dict[str, Any]:
    discovery = await _get_discovery()
    try:
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        jwks = await _get_jwks(discovery.jwks_uri)
        key = _select_jwk(jwks, kid)
        if key is None:
            jwks = await _get_jwks(discovery.jwks_uri, force=True)
            key = _select_jwk(jwks, kid)
        if key is None:
            raise OidcError("bad_id_token", "Токен входа недействителен.")

        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.OIDC_CLIENT_ID,
            issuer=settings.OIDC_ISSUER,
        )
    except (JWTError, ValueError) as exc:
        raise OidcError("bad_id_token", "Токен входа недействителен.") from exc

    token_nonce = claims.get("nonce")
    if not token_nonce or not secrets.compare_digest(str(token_nonce), nonce):
        raise OidcError("bad_nonce", "Токен входа не соответствует сессии.")
    return claims


def frontend_error_url(code: str) -> str:
    base = settings.FRONTEND_APP_URL.rstrip("/")
    return f"{base}/login#oidc_error={code}"


def frontend_success_url(*, token: str) -> str:
    # The token goes in the fragment: it is never sent to the server and never
    # ends up in nginx access logs or the Referer header.
    base = settings.FRONTEND_APP_URL.rstrip("/")
    return f"{base}/#token={token}"

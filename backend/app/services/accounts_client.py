"""Thin async client for the unified account registry (metroAccounts).

metroCheck keeps a single role: anyone the registry lets into ``metrocheck`` gets
full access. The registry owns credentials and the access flag.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class AccountsUnavailable(HTTPException):
    def __init__(self, message: str = "Сервис учётных записей недоступен.") -> None:
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)


def is_enabled() -> bool:
    return bool(
        settings.ACCOUNTS_ENABLED and settings.ACCOUNTS_URL and settings.ACCOUNTS_SERVICE_TOKEN
    )


def _headers() -> dict[str, str]:
    return {
        "X-Service-Name": settings.ACCOUNTS_SERVICE_NAME,
        "X-Service-Token": settings.ACCOUNTS_SERVICE_TOKEN,
    }


async def _request(method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{settings.ACCOUNTS_URL.rstrip('/')}/api/v1{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.ACCOUNTS_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, json=json, headers=_headers())
    except httpx.HTTPError as exc:
        raise AccountsUnavailable() from exc

    if response.status_code >= 500:
        raise AccountsUnavailable()
    if response.status_code >= 400:
        detail = "Ошибка сервиса учётных записей."
        try:
            payload = response.json()
            if isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        return response.json()
    except ValueError as exc:
        raise AccountsUnavailable() from exc


async def verify(*, email: str, password: str) -> dict[str, str]:
    """Return the signed-in identity (email + display name)."""

    payload = await _request(
        "POST",
        "/internal/verify",
        json={"email": email, "password": password, "service": settings.ACCOUNTS_SERVICE_NAME},
    )
    account = payload.get("account") or {}
    resolved_email = str(account.get("email") or email)
    name = " ".join(
        part
        for part in (
            str(account.get("last_name") or "").strip(),
            str(account.get("first_name") or "").strip(),
            str(account.get("patronymic") or "").strip(),
        )
        if part
    )
    return {"email": resolved_email, "name": name or resolved_email}

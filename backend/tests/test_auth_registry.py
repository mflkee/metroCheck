from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1.routes.auth import LoginRequest, login
from app.core import auth as core_auth
from app.core.config import settings
from app.services import accounts_client


def _enable_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ACCOUNTS_ENABLED", True)
    monkeypatch.setattr(settings, "ACCOUNTS_URL", "http://registry:8000")
    monkeypatch.setattr(settings, "ACCOUNTS_SERVICE_TOKEN", "service-token")


def test_accounts_client_uses_the_versioned_internal_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_registry(monkeypatch)
    captured: dict = {}

    class _Response:
        status_code = 200

        def json(self) -> dict:
            return {
                "account": {"email": "x@mkair.ru", "first_name": "Иван", "last_name": "Тестов"},
                "role": None,
            }

    class _Client:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs):
            captured.update(method=method, url=url, headers=kwargs.get("headers"))
            return _Response()

    monkeypatch.setattr(accounts_client.httpx, "AsyncClient", _Client)

    identity = asyncio.run(accounts_client.verify(email="x@mkair.ru", password="secret"))

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/v1/internal/verify")
    assert captured["headers"]["X-Service-Name"] == "metrocheck"
    assert identity["email"] == "x@mkair.ru"
    assert identity["name"] == "Тестов Иван"


async def test_login_via_registry_issues_an_identity_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_registry(monkeypatch)

    async def fake_verify(**_kwargs) -> dict:
        return {"email": "user@mkair.ru", "name": "Тестов Иван"}

    monkeypatch.setattr(accounts_client, "verify", fake_verify)

    response = await login(LoginRequest(email="user@mkair.ru", password="whatever"))

    assert response.access_token
    assert response.user["email"] == "user@mkair.ru"
    assert response.user["auth_method"] == "registry"
    assert response.user["role"] == "admin"


async def test_login_via_registry_propagates_denial(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_registry(monkeypatch)

    async def deny(**_kwargs) -> dict:
        raise HTTPException(status_code=403, detail="Нет доступа к сервису «metrocheck».")

    monkeypatch.setattr(accounts_client, "verify", deny)

    with pytest.raises(HTTPException) as excinfo:
        await login(LoginRequest(email="user@mkair.ru", password="whatever"))
    assert excinfo.value.status_code == 403


async def test_legacy_admin_login_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ACCOUNTS_ENABLED", False)
    core_auth.init_admin("admin-metrochek", "AdminPass-1")

    response = await login(LoginRequest(username="admin-metrochek", password="AdminPass-1"))

    assert response.user["username"] == "admin-metrochek"
    assert response.access_token

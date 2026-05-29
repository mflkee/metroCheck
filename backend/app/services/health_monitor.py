"""Health monitor — checks status of all integrations."""

import asyncio
import time
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.arshin_client import ArshinClient


class HealthMonitor:
    """Monitors health of all external services."""

    def __init__(self) -> None:
        self._status: dict[str, Any] = {
            "arshin_api": {"status": "unknown", "last_check": 0},
            "arshin_token": {"status": "unknown", "expires_in": 0, "last_check": 0},
            "n8n": {"status": "unknown", "last_check": 0},
            "openrouter": {"status": "unknown", "last_check": 0},
            "token_agent": {"status": "unknown", "last_check": 0},
        }
        self._last_update = 0

    async def check_all(self) -> dict[str, Any]:
        """Run all health checks."""
        await asyncio.gather(
            self._check_arshin_api(),
            self._check_arshin_token(),
            self._check_n8n(),
            self._check_openrouter(),
            self._check_token_agent(),
        )
        self._last_update = time.time()
        return self._status

    async def _check_arshin_api(self) -> None:
        """Check ARSHIN public API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://fgis.gost.ru/fundmetrology/eapi/vri",
                    params={"rows": 1},
                )
                self._status["arshin_api"] = {
                    "status": "ok" if r.status_code == 200 else "error",
                    "code": r.status_code,
                    "last_check": time.time(),
                }
        except Exception as e:
            self._status["arshin_api"] = {
                "status": "error",
                "error": str(e),
                "last_check": time.time(),
            }

    async def _check_arshin_token(self) -> None:
        """Check ARSHIN Bearer token."""
        try:
            client = ArshinClient()
            token = client.bearer_token
            if token:
                expires_in = max(0, int(client._token_expires - time.time()))
                self._status["arshin_token"] = {
                    "status": "ok",
                    "expires_in": expires_in,
                    "expires_min": expires_in // 60,
                    "last_check": time.time(),
                }
            else:
                self._status["arshin_token"] = {
                    "status": "expired",
                    "expires_in": 0,
                    "last_check": time.time(),
                }
        except Exception as e:
            self._status["arshin_token"] = {
                "status": "error",
                "error": str(e),
                "last_check": time.time(),
            }

    async def _check_n8n(self) -> None:
        """Check n8n availability."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # n8n is at metroCheck_n8n:5678 inside Docker network
                r = await client.get("http://metroCheck_n8n:5678/healthz")
                self._status["n8n"] = {
                    "status": "ok" if r.status_code == 200 else "error",
                    "code": r.status_code,
                    "last_check": time.time(),
                }
        except Exception as e:
            self._status["n8n"] = {
                "status": "error",
                "error": str(e)[:100],
                "last_check": time.time(),
            }

    async def _check_openrouter(self) -> None:
        """Check OpenRouter API key balance."""
        try:
            api_key = settings.OPENROUTER_API_KEY
            if not api_key:
                self._status["openrouter"] = {
                    "status": "not_configured",
                    "last_check": time.time(),
                }
                return

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if r.status_code == 200:
                    data = r.json()
                    self._status["openrouter"] = {
                        "status": "ok",
                        "balance": data.get("data", {}).get("limit_remaining", "unknown"),
                        "last_check": time.time(),
                    }
                else:
                    self._status["openrouter"] = {
                        "status": "error",
                        "code": r.status_code,
                        "last_check": time.time(),
                    }
        except Exception as e:
            self._status["openrouter"] = {
                "status": "error",
                "error": str(e),
                "last_check": time.time(),
            }

    async def _check_token_agent(self) -> None:
        """Check token-agent on Зонов's PC."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"http://{settings.ZONOV_IP}:8003/health",
                )
                self._status["token_agent"] = {
                    "status": "ok" if r.status_code == 200 else "error",
                    "code": r.status_code,
                    "last_check": time.time(),
                }
        except Exception as e:
            self._status["token_agent"] = {
                "status": "unreachable",
                "error": str(e)[:100],
                "last_check": time.time(),
            }

    def get_status(self) -> dict[str, Any]:
        """Get cached status (fast)."""
        return {
            **self._status,
            "last_update": self._last_update,
            "stale": time.time() - self._last_update > 60,
        }


# Singleton
_health_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor

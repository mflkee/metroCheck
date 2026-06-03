"""Health monitor — checks status of all integrations."""

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors health of all external services."""

    def __init__(self) -> None:
        self._status: dict[str, Any] = {
            "arshin_api": {"status": "unknown", "last_check": 0},
            "arshin_token": {"status": "unknown", "age_seconds": None, "age_minutes": None, "last_check": 0},
            "openrouter": {"status": "unknown", "last_check": 0},
            "token_agent": {"status": "unknown", "last_check": 0},
        }
        self._last_update = 0

    async def check_all(self) -> dict[str, Any]:
        """Run all health checks."""
        await asyncio.gather(
            self._check_arshin_api(),
            self._check_arshin_token(),
            self._check_openrouter(),
            self._check_token_agent(),
            self._check_current_job(),
        )
        self._last_update = time.time()
        return self._status

    async def _check_current_job(self) -> None:
        """Check current running job status."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.repositories.job_repository import JobRepository
            from sqlalchemy import select
            from app.models.job import Job

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Job).where(Job.status == "running").limit(1)
                )
                job = result.scalar_one_or_none()

                if job:
                    import json
                    phase_stats = {}
                    if job.phase_stats:
                        try:
                            phase_stats = json.loads(job.phase_stats)
                        except Exception:
                            pass

                    self._status["current_job"] = {
                        "status": "running",
                        "year": job.year,
                        "month": job.month,
                        "phase": job.current_phase or "unknown",
                        "progress": job.progress,
                        "progress_percent": job.progress_percent,
                        "total_devices": job.total_devices,
                        "processed_devices": job.processed_devices,
                        "phase_stats": phase_stats,
                        "waiting_for_token": job.waiting_for_token,
                    }
                else:
                    # Check pending jobs
                    result = await db.execute(
                        select(Job).where(Job.status.in_(["pending", "paused"]))
                        .order_by(Job.priority.desc(), Job.created_at.asc())
                        .limit(1)
                    )
                    pending = result.scalar_one_or_none()
                    if pending:
                        self._status["current_job"] = {
                            "status": "pending",
                            "year": pending.year,
                            "month": pending.month,
                            "priority": pending.priority,
                            "message": f"Ожидает запуска: {pending.month:02d}.{pending.year}",
                        }
                    else:
                        self._status["current_job"] = {
                            "status": "idle",
                            "message": "Нет активных задач",
                        }
        except Exception as e:
            self._status["current_job"] = {
                "status": "error",
                "error": str(e)[:100],
            }

    async def _check_arshin_api(self) -> None:
        """Check ARSHIN public API."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
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
        """Check ARSHIN Bearer token from file."""
        token_path = settings.TOKEN_FILE_PATH
        try:
            if not os.path.isfile(token_path):
                self._status["arshin_token"] = {
                    "status": "waiting",
                    "note": "файл не найден",
                    "expires_in": 0,
                    "last_check": time.time(),
                }
                return

            def _read_token():
                with open(token_path, "r") as f:
                    return json.load(f)

            def _jwt_expires_in(raw: str, default: int = 3600) -> int:
                try:
                    parts = raw.split(".")
                    if len(parts) < 2:
                        return default
                    payload = parts[1]
                    # base64url → base64
                    payload = payload.replace("-", "+").replace("_", "/")
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += "=" * padding
                    decoded = json.loads(base64.b64decode(payload))
                    exp = decoded.get("exp")
                    if exp is None:
                        return default
                    remaining = int(exp - time.time())
                    return max(remaining, 0)
                except Exception:
                    return default

            data = await asyncio.to_thread(_read_token)
            token = data.get("token")
            updated_at = data.get("updated_at", 0)
            expires_in = _jwt_expires_in(token)
            age = time.time() - updated_at
            age_min = int(age) // 60

            if token and expires_in > 0:
                self._status["arshin_token"] = {
                    "status": "ok",
                    "age_seconds": int(age),
                    "age_minutes": age_min,
                    "last_check": time.time(),
                }
            else:
                self._status["arshin_token"] = {
                    "status": "expired",
                    "age_seconds": int(age) if updated_at else None,
                    "age_minutes": age_min if updated_at else None,
                    "note": f"возраст токена {age_min} мин" if token else "токен отсутствует",
                    "last_check": time.time(),
                }
        except Exception as e:
            self._status["arshin_token"] = {
                "status": "error",
                "error": str(e)[:200],
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

            async with httpx.AsyncClient(timeout=5.0) as client:
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
        """Check token file from agent."""
        token_path = settings.TOKEN_FILE_PATH
        try:
            exists = await asyncio.to_thread(os.path.isfile, token_path)
            self._status["token_agent"] = {
                "status": "ok" if exists else "waiting",
                "note": "файл синхронизирован" if exists else "ожидание файла",
                "last_check": time.time(),
            }
        except Exception as e:
            self._status["token_agent"] = {
                "status": "error",
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

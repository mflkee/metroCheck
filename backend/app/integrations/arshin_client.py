"""ARSHIN (ФГИС Росаккредитации) API client."""

import asyncio
import time
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

# Global polling state for token-agent
_token_needed_event = asyncio.Event()
_polling_token: str | None = None


def get_token_needed() -> bool:
    """Check if backend is waiting for a token."""
    return _token_needed_event.is_set()


def deliver_polling_token(token: str) -> bool:
    """Deliver token from polling agent."""
    global _polling_token
    if not _token_needed_event.is_set():
        return False
    _polling_token = token
    _token_needed_event.set()
    return True


class ArshinClient:
    """Client for ARSHIN public API and LK API with automatic token refresh."""

    def __init__(self) -> None:
        self.base_url = settings.ARSHIN_BASE_URL
        self.lk_base_url = "https://fgis.gost.ru/fundmetrology/cm/lk/api"
        self._token = settings.ARSHIN_BEARER_TOKEN
        self._token_expires: float = 0.0
        self._zonov_ip = settings.ZONOV_IP
        self._agent_key = settings.TOKEN_AGENT_KEY

    @property
    def bearer_token(self) -> str | None:
        if time.time() > self._token_expires:
            return None
        return self._token

    async def _ensure_token(self) -> str:
        token = self.bearer_token
        if token:
            return token
        return await self._request_new_token()

    async def _request_new_token(self) -> str:
        """Request token via polling: set flag, wait for token-agent to deliver."""
        global _token_needed_event, _polling_token

        # Reset state
        _polling_token = None
        _token_needed_event.set()

        # Wait for token-agent to deliver token (timeout 24 hours)
        try:
            await asyncio.wait_for(_token_needed_event.wait(), timeout=86400)
        except asyncio.TimeoutError:
            _token_needed_event.clear()
            raise RuntimeError("Timeout waiting for token from agent")

        _token_needed_event.clear()

        if _polling_token:
            self._token = _polling_token
            self._token_expires = time.time() + 3600
            return self._token
        raise RuntimeError("Token delivery failed")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_calibrations(
        self,
        org_title: str,
        verification_date_start: date,
        verification_date_end: date,
        start: int = 0,
        rows: int = 100,
    ) -> dict[str, Any]:
        """Search calibrations by organization and date range."""
        params = {
            "org_title": org_title,
            "verification_date_start": verification_date_start.strftime("%Y-%m-%d"),
            "verification_date_end": verification_date_end.strftime("%Y-%m-%d"),
            "rows": rows,
        }
        if start > 0:
            params["start"] = start
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{self.base_url}/vri", params=params)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_calibration_count(
        self,
        org_title: str,
        verification_date_start: date,
        verification_date_end: date,
    ) -> int:
        """Get total count of calibrations for pagination."""
        params = {
            "org_title": org_title,
            "verification_date_start": verification_date_start.strftime("%Y-%m-%d"),
            "verification_date_end": verification_date_end.strftime("%Y-%m-%d"),
            "rows": 1,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/vri", params=params)
            response.raise_for_status()
            data = response.json()
            return int(data.get("result", {}).get("count", 0))

    async def _lk_request(self, url: str, params: dict | None = None) -> dict[str, Any] | None:
        token = await self._ensure_token()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_3_1) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Safari/605.1.15"
            ),
            "Authorization": f"Bearer {token.removeprefix('Bearer ')}",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 401:
                self._token_expires = 0
                token = await self._ensure_token()
                headers["Authorization"] = f"Bearer {token.removeprefix('Bearer ')}"
                response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_lk_details_by_docnum(self, document_number: str) -> dict[str, Any] | None:
        """Fetch details from ARSHIN LK by document number."""
        url = f"{self.lk_base_url}/rgsprepvriview/2163"
        params = {"status": "PUBLISHED", "text": document_number}
        data = await self._lk_request(url, params)
        if data is None:
            return None
        views = data.get("rgsPrepVriViews", [])
        return views[0] if views else None

    async def get_lk_data2_by_id(self, record_id: int) -> dict[str, Any] | None:
        """Fetch extended data from ARSHIN LK by record ID."""
        url = f"{self.lk_base_url}/rgsprepvri/2163/{record_id}"
        data = await self._lk_request(url)
        if data is None:
            return None
        if "miInfo" in data and isinstance(data["miInfo"], dict):
            vri_mi = data["miInfo"].get("vriMi", {})
            data.update(vri_mi)
            del data["miInfo"]
        return data

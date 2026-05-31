"""ARSHIN (ФГИС Росаккредитации) API client."""

import asyncio
import base64
import json
import os
import time
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class ArshinClient:
    """Client for ARSHIN public API and LK API with automatic token refresh."""

    def __init__(self) -> None:
        self.base_url = settings.ARSHIN_BASE_URL
        self.lk_base_url = "https://fgis.gost.ru/fundmetrology/cm/lk/api"
        self._token = settings.ARSHIN_BEARER_TOKEN
        self._token_expires: float = 0.0

    @staticmethod
    def _jwt_expires_in(token: str, default: int = 3600) -> int:
        """Decode JWT payload to get real expiration time."""
        try:
            parts = token.split(".")
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
        """Read token from shared file (Synology Drive sync)."""
        token_file = settings.TOKEN_FILE_PATH

        if not token_file:
            raise RuntimeError("TOKEN_FILE_PATH not configured")

        logger = __import__("logging").getLogger(__name__)
        logger.info("Waiting for token file: %s", token_file)

        while True:
            if os.path.exists(token_file):
                try:
                    with open(token_file, "r") as f:
                        data = json.load(f)

                    token = data.get("token")
                    updated_at = data.get("updated_at", 0)

                    expires_in = self._jwt_expires_in(token)

                    # Check if token is fresh (not expired)
                    age = time.time() - updated_at

                    if token and (age < expires_in or expires_in > 0):
                        self._token = token
                        self._token_expires = time.time() + expires_in

                        # Archive file to avoid reusing
                        archive_path = token_file + ".used"
                        os.rename(token_file, archive_path)

                        logger.info(
                            "Token read from file, expires_in=%ds",
                            expires_in,
                        )
                        return self._token
                    else:
                        logger.warning(
                            "Token in file is expired (age=%ds, expires_in=%ds)",
                            int(age),
                            expires_in,
                        )
                        # Remove expired token file
                        os.remove(token_file)

                except Exception as e:
                    logger.error("Error reading token file: %s", e)

            await asyncio.sleep(10)  # Check every 10 seconds

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_calibrations(
        self,
        org_title: str,
        *,
        year: int,
        start: int = 0,
        rows: int = 100,
    ) -> dict[str, Any]:
        """Search calibrations by organization and year."""
        params: dict[str, Any] = {
            "org_title": org_title,
            "year": year,
            "rows": rows,
        }
        if start > 0:
            params["start"] = start
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{self.base_url}/vri", params=params)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(1), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_calibration_count(
        self,
        org_title: str,
        *,
        year: int,
    ) -> int:
        """Get total count of calibrations for pagination."""
        params = {
            "org_title": org_title,
            "year": year,
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

"""ArshinService — бизнес-логика работы с АРШИНом."""

import asyncio
import logging
from datetime import date
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.arshin_client import ArshinClient
from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.calibration_cache_repository import CalibrationCacheRepository

logger = logging.getLogger(__name__)


class ArshinService:
    """Service for fetching and processing ARSHIN calibration data with caching."""

    def __init__(self, db: AsyncSession) -> None:
        self.client = ArshinClient()
        self.repo = CalibrationRepository(db)
        self.cache_repo = CalibrationCacheRepository(db)

    async def fetch_and_save_calibrations(self, year: int, month: int, force_refresh: bool = False) -> dict[str, Any]:
        """Fetch all calibrations for a year with caching.
        
        Args:
            year: Year to fetch
            month: Month to filter (only saves records for this month)
            force_refresh: If True, ignore cache and fetch fresh data
            
        Returns:
            Dict with total, saved, errors, and cache status
        """
        org = 'ООО "МКАИР"'
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            is_valid = await self.cache_repo.is_cache_valid(year)
            if is_valid:
                logger.info("Using cached data for year %d (cache valid)", year)
                # Count how many records we have for this month
                month_records = await self.repo.get_by_month(year, month)
                return {
                    "total": len(month_records),
                    "saved": len(month_records),
                    "errors": 0,
                    "year": year,
                    "month": month,
                    "cached": True,
                    "message": f"Использованы кэшированные данные ({len(month_records)} записей за {month:02d}.{year})",
                }

        # Fetch fresh data from API
        logger.info("Fetching fresh data from ARSHIN API for year %d", year)
        
        total = await self.client.get_calibration_count(org, year=year)
        if total == 0:
            return {"total": 0, "saved": 0, "errors": 0, "message": "No calibrations found", "cached": False}

        all_items: list[dict] = []
        start = 0
        page_size = 100  # API limit, don't exceed
        consecutive_failures = 0
        max_consecutive_failures = 20

        while start < total:
            if consecutive_failures >= max_consecutive_failures:
                logger.warning(
                    "Too many consecutive failures (%d), stopping at start=%d",
                    consecutive_failures, start,
                )
                break

            await asyncio.sleep(0.3)  # Уменьшили задержку

            try:
                data = await self.client.search_calibrations(org, year=year, start=start, rows=page_size)
                items = data.get("result", {}).get("items", [])
                all_items.extend(items)
                start += len(items)
                consecutive_failures = 0
                page_size = min(page_size * 2, 100)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited (429), waiting 10s...")
                    await asyncio.sleep(10)
                    continue
                logger.warning("Failed start=%d page_size=%d: %s", start, page_size, e)
                if page_size > 5:
                    page_size = max(page_size // 2, 100)
                else:
                    start += 1
                consecutive_failures += 1
            except Exception as e:
                logger.warning("Failed start=%d page_size=%d: %s", start, page_size, e)
                start += 1
                consecutive_failures += 1

        # Save all items to DB (for all months)
        saved = 0
        errors = 0
        month_str = f"{month:02d}"
        
        for item in all_items:
            vdate = item.get("verification_date", "")
            # verification_date format: "DD.MM.YYYY" or "YYYY-MM-DD"
            item_month = vdate[3:5] if len(vdate) >= 7 and vdate[2] == "." else vdate[5:7] if len(vdate) >= 7 else ""
            
            try:
                # Сохраняем все записи за год (для всех месяцев)
                item_year = year
                item_month_int = int(item_month) if item_month else month
                await self.repo.create_or_update(item, item_year, item_month_int)
                
                # Считаем только записи за нужный месяц
                if item_month == month_str:
                    saved += 1
            except Exception as e:
                errors += 1
                logger.warning("Failed to save calibration %s: %s", item.get("vri_id"), e)

        # Update cache
        await self.cache_repo.update_cache(year, total)
        
        return {
            "total": total,
            "saved": saved,
            "errors": errors,
            "year": year,
            "month": month,
            "cached": False,
            "message": f"Загружено {total} записей за {year} год, сохранено {saved} за {month:02d}.{year}",
        }

    async def fetch_lk_details(self, year: int, month: int) -> dict[str, Any]:
        """Fetch LK details for all calibrations without them."""
        calibrations = await self.repo.get_without_lk_details(year, month)

        updated = 0
        errors = 0
        for cal in calibrations:
            if not cal.result_docnum:
                continue

            try:
                detail = await self.client.get_lk_details_by_docnum(cal.result_docnum)
                if detail:
                    await self.repo.update_lk_details(cal.id, detail)
                    updated += 1
            except Exception:
                errors += 1

        return {"total": len(calibrations), "updated": updated, "errors": errors}

    async def fetch_lk_data2(self, year: int, month: int) -> dict[str, Any]:
        """Fetch extended LK data (data2) for all calibrations."""
        calibrations = await self.repo.get_without_data2(year, month)

        updated = 0
        errors = 0
        for cal in calibrations:
            if not cal.vri_id:
                continue

            try:
                # vri_id from LK details is the ID for data2
                data2 = await self.client.get_lk_data2_by_id(int(cal.vri_id))
                if data2:
                    await self.repo.update_data2(cal.id, data2)
                    updated += 1
            except Exception:
                errors += 1

        return {"total": len(calibrations), "updated": updated, "errors": errors}

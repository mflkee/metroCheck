"""ArshinService — бизнес-логика работы с АРШИНом."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.arshin_client import ArshinClient
from app.repositories.calibration_cache_repository import CalibrationCacheRepository
from app.repositories.calibration_repository import CalibrationRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, int, int], Any]  # fetched, total, saved_for_month, errors


class ArshinService:
    """Service for fetching and processing ARSHIN calibration data with caching."""

    def __init__(self, db: AsyncSession) -> None:
        self.client = ArshinClient()
        self.repo = CalibrationRepository(db)
        self.cache_repo = CalibrationCacheRepository(db)

    def _extract_month(self, vdate: str) -> str:
        """Extract MM from 'DD.MM.YYYY' or 'YYYY-MM-DD'."""
        if len(vdate) >= 7 and vdate[2] == ".":
            return vdate[3:5]
        if len(vdate) >= 7:
            return vdate[5:7]
        return ""

    async def fetch_and_save_calibrations(
        self,
        year: int,
        month: int,
        force_refresh: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Fetch all calibrations for a year with caching and batch save.

        Args:
            year: Year to fetch
            month: Month to filter (only counts records for this month)
            force_refresh: If True, ignore cache and fetch fresh data
            progress_callback: Optional async callback(fetched, total, saved, errors)

        Returns:
            Dict with total, saved, errors, and cache status
        """
        org = 'ООО "МКАИР"'
        month_str = f"{month:02d}"

        # Check cache first (unless force refresh)
        if not force_refresh:
            is_valid = await self.cache_repo.is_cache_valid(year)
            if is_valid:
                logger.info("Using cached data for year %d (cache valid)", year)
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

        logger.info("Fetching fresh data from ARSHIN API for year %d", year)

        total = await self.client.get_calibration_count(org, year=year)
        if total == 0:
            return {"total": 0, "saved": 0, "errors": 0, "message": "No calibrations found", "cached": False}

        # Fetch all pages first (no DB writes during network phase)
        all_items: list[dict] = []
        start = 0
        page_size = 100
        consecutive_failures = 0
        max_consecutive_failures = 10
        last_progress_emit = 0

        async def _emit_progress(saved: int = 0, errors: int = 0) -> None:
            nonlocal last_progress_emit
            fetched = len(all_items)
            if progress_callback and (fetched - last_progress_emit >= 100 or fetched >= total or saved > 0 or errors > 0):
                await progress_callback(fetched, total, saved, errors)
                last_progress_emit = fetched

        while start < total:
            if consecutive_failures >= max_consecutive_failures:
                logger.warning(
                    "Too many consecutive failures (%d), stopping at start=%d",
                    consecutive_failures, start,
                )
                break

            await asyncio.sleep(0.3)

            try:
                data = await self.client.search_calibrations(org, year=year, start=start, rows=page_size)
                items = data.get("result", {}).get("items", [])
                consecutive_failures = 0

                if not items:
                    logger.warning("Empty page at start=%d, advancing", start)
                    start += page_size
                    continue

                all_items.extend(items)
                start += len(items)
                page_size = min(page_size * 2, 100)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited (429), waiting 10s...")
                    await asyncio.sleep(10)
                    continue
                logger.warning("Failed start=%d page_size=%d: %s", start, page_size, e)
                consecutive_failures += 1
                start += max(page_size // 4, 1)
                page_size = max(page_size // 2, 10)
            except Exception as e:
                logger.warning("Failed start=%d page_size=%d: %s", start, page_size, e)
                consecutive_failures += 1
                start += max(page_size // 4, 1)
                page_size = max(page_size // 2, 10)

            await _emit_progress()

        # Save all fetched items in batches using bulk upsert.
        saved_for_month = 0
        errors = 0
        batch_size = 1000

        for batch_start in range(0, len(all_items), batch_size):
            batch = all_items[batch_start:batch_start + batch_size]

            # Group batch by actual item month for correct DB partitioning
            rows_by_month: dict[int, list[dict]] = {}
            for item in batch:
                vdate = item.get("verification_date", "")
                item_month = self._extract_month(vdate)
                item_month_int = int(item_month) if item_month else month
                rows_by_month.setdefault(item_month_int, []).append(item)
                if item_month == month_str:
                    saved_for_month += 1

            for item_month_int, month_items in rows_by_month.items():
                try:
                    result = await self.repo.bulk_upsert(month_items, year, item_month_int)
                    errors += result.get("errors", 0)
                except Exception as e:
                    logger.error("Bulk upsert failed for month %d: %s", item_month_int, e)
                    errors += len(month_items)

            await _emit_progress(saved_for_month, errors)

        fetched = len(all_items)

        # Update cache only if we fetched most of the data
        if fetched >= total * 0.8:
            await self.cache_repo.update_cache(year, total)

        return {
            "total": total,
            "saved": saved_for_month,
            "errors": errors,
            "year": year,
            "month": month,
            "cached": False,
            "message": f"Загружено {fetched}/{total} записей за {year} год, сохранено {saved_for_month} за {month:02d}.{year}",
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
                # Step 1: Search by document number to get LK record id
                search_result = await self.client.get_lk_details_by_docnum(cal.result_docnum)
                if not search_result:
                    continue

                # Step 2: Fetch detailed record using LK id (not vri_id!)
                lk_id = search_result.get("id")
                if not lk_id:
                    continue

                detail = await self.client.get_lk_data2_by_id(lk_id)
                if detail:
                    await self.repo.update_lk_details(cal.id, detail)
                    updated += 1
            except Exception:
                errors += 1

        return {"total": len(calibrations), "updated": updated, "errors": errors}

    async def fetch_lk_data2(self, year: int, month: int) -> dict[str, Any]:
        """Fetch extended LK data (data2) for all calibrations.

        Deprecated: all data now fetched in fetch_lk_details.
        Kept for pipeline compatibility.
        """
        calibrations = await self.repo.get_without_data2(year, month)

        updated = 0
        errors = 0
        for cal in calibrations:
            if not cal.result_docnum:
                continue

            try:
                # Re-fetch using the same flow as fetch_lk_details
                search_result = await self.client.get_lk_details_by_docnum(cal.result_docnum)
                if not search_result:
                    continue

                lk_id = search_result.get("id")
                if not lk_id:
                    continue

                detail = await self.client.get_lk_data2_by_id(lk_id)
                if detail:
                    await self.repo.update_data2(cal.id, detail)
                    updated += 1
            except Exception:
                errors += 1

        return {"total": len(calibrations), "updated": updated, "errors": errors}

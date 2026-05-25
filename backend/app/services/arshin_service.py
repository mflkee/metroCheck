"""ArshinService — бизнес-логика работы с АРШИНом."""

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.arshin_client import ArshinClient
from app.repositories.calibration_repository import CalibrationRepository


class ArshinService:
    """Service for fetching and processing ARSHIN calibration data."""

    def __init__(self, db: AsyncSession) -> None:
        self.client = ArshinClient()
        self.repo = CalibrationRepository(db)

    async def fetch_and_save_calibrations(self, year: int, month: int) -> dict[str, Any]:
        """Fetch all calibrations for a month and save to DB.

        Returns:
            dict with total, saved, errors counts
        """
        from calendar import monthrange

        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        org = 'ООО "МКАИР"'

        # Get total count
        total = await self.client.get_calibration_count(org, first_day, last_day)
        if total == 0:
            return {"total": 0, "saved": 0, "errors": 0, "message": "No calibrations found"}

        # Fetch all pages
        all_items: list[dict] = []
        start = 0
        while start < total:
            data = await self.client.search_calibrations(org, first_day, last_day, start, 100)
            items = data.get("result", {}).get("items", [])
            all_items.extend(items)
            start += len(items)

        # Save to DB
        saved = 0
        errors = 0
        for item in all_items:
            try:
                await self.repo.create_or_update(item, year, month)
                saved += 1
            except Exception:
                errors += 1

        return {
            "total": total,
            "saved": saved,
            "errors": errors,
            "year": year,
            "month": month,
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

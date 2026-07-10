"""Calibration repository."""

import contextlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration import Calibration


class CalibrationRepository:
    """Repository for Calibration model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _parse_date(value: str | None) -> Any:
        """Parse date from 'DD.MM.YYYY' or 'YYYY-MM-DD'."""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return None

    @staticmethod
    def _bool_or_none(val):
        if val is None:
            return None
        return bool(val)

    def _item_to_row(self, data: dict[str, Any], year: int, month: int) -> dict[str, Any]:
        """Convert ARSHIN API item to DB row dict."""
        return {
            "vri_id": str(data.get("vri_id", "")),
            "mi_number": (data.get("mi_number") or "").strip(),
            "mit_number": data.get("mit_number"),
            "mit_title": data.get("mit_title"),
            "mit_notation": data.get("mit_notation"),
            "mi_modification": data.get("mi_modification"),
            "verification_date": self._parse_date(data.get("verification_date")),
            "valid_date": self._parse_date(data.get("valid_date")),
            "result_docnum": data.get("result_docnum"),
            "result": data.get("result"),
            "applicability": self._bool_or_none(data.get("applicability")),
            "org_title": data.get("org_title", 'ООО "МКАИР"'),
            "year": year,
            "month": month,
        }

    async def bulk_upsert(self, items: list[dict[str, Any]], year: int, month: int) -> dict[str, int]:
        """Bulk upsert calibration records.

        Returns dict with saved_count and errors_count.
        """
        if not items:
            return {"saved": 0, "errors": 0}

        rows = []
        errors = 0
        for item in items:
            try:
                rows.append(self._item_to_row(item, year, month))
            except Exception as e:
                errors += 1
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Failed to prepare calibration row %s: %s", item.get("vri_id"), e)

        if not rows:
            return {"saved": 0, "errors": errors}

        # Deduplicate by vri_id within the same batch to avoid
        # "ON CONFLICT DO UPDATE command cannot affect row a second time".
        unique_rows: dict[str, dict[str, Any]] = {}
        for row in rows:
            unique_rows[row["vri_id"]] = row
        rows = list(unique_rows.values())

        try:
            stmt = insert(Calibration).values(rows)
            update_cols = [
                "mi_number", "mit_number", "mit_title", "mit_notation",
                "mi_modification", "verification_date", "valid_date",
                "result_docnum", "result", "applicability", "org_title",
                "year", "month",
            ]
            stmt = stmt.on_conflict_do_update(
                index_elements=["vri_id"],
                set_={col: stmt.excluded[col] for col in update_cols},
            )

            await self.db.execute(stmt)
            await self.db.commit()

            return {"saved": len(rows), "errors": errors}
        except Exception as e:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Bulk upsert failed for month %d (%d items): %s", month, len(items), e)
            with contextlib.suppress(Exception):
                await self.db.rollback()
            return {"saved": 0, "errors": len(items)}

    async def create_or_update(self, data: dict[str, Any], year: int, month: int) -> Calibration:
        """Create or update calibration from ARSHIN API data."""
        vri_id = str(data.get("vri_id", ""))
        if not vri_id:
            raise ValueError("vri_id is required")

        # Check existing
        result = await self.db.execute(select(Calibration).where(Calibration.vri_id == vri_id))
        existing = result.scalar_one_or_none()

        if existing:
            existing.mi_number = (data.get("mi_number") or "").strip()
            existing.mit_number = data.get("mit_number")
            existing.mit_title = data.get("mit_title")
            existing.mit_notation = data.get("mit_notation")
            existing.mi_modification = data.get("mi_modification")
            existing.verification_date = self._parse_date(data.get("verification_date"))
            existing.valid_date = self._parse_date(data.get("valid_date"))
            existing.result_docnum = data.get("result_docnum")
            existing.result = data.get("result")
            existing.applicability = self._bool_or_none(data.get("applicability"))
            existing.org_title = data.get("org_title", 'ООО "МКАИР"')
            existing.year = year
            existing.month = month
            cal = existing
        else:
            cal = Calibration(
                vri_id=vri_id,
                mi_number=(data.get("mi_number") or "").strip(),
                mit_number=data.get("mit_number"),
                mit_title=data.get("mit_title"),
                mit_notation=data.get("mit_notation"),
                mi_modification=data.get("mi_modification"),
                verification_date=self._parse_date(data.get("verification_date")),
                valid_date=self._parse_date(data.get("valid_date")),
                result_docnum=data.get("result_docnum"),
                result=data.get("result"),
                applicability=self._bool_or_none(data.get("applicability")),
                org_title=data.get("org_title", 'ООО "МКАИР"'),
                year=year,
                month=month,
            )
            self.db.add(cal)

        await self.db.commit()
        await self.db.refresh(cal)
        return cal

    async def get_without_lk_details(self, year: int, month: int) -> list[Calibration]:
        """Get calibrations without LK details."""
        result = await self.db.execute(
            select(Calibration)
            .where(Calibration.year == year)
            .where(Calibration.month == month)
            .where(Calibration.verifier.is_(None))
        )
        return list(result.scalars().all())

    async def get_without_data2(self, year: int, month: int) -> list[Calibration]:
        """Get calibrations without extended data2."""
        result = await self.db.execute(
            select(Calibration)
            .where(Calibration.year == year)
            .where(Calibration.month == month)
            .where(Calibration.conditions.is_(None))
        )
        return list(result.scalars().all())

    async def get_by_month(self, year: int, month: int) -> list[Calibration]:
        """Get all calibrations for a given month."""
        result = await self.db.execute(
            select(Calibration)
            .where(Calibration.year == year)
            .where(Calibration.month == month)
        )
        return list(result.scalars().all())

    async def get_by_serial(self, serial_number: str, year: int | None = None, month: int | None = None) -> Calibration | None:
        """Get calibration by serial number.

        Args:
            serial_number: Serial number to search
            year: Optional year filter
            month: Optional month filter
        """
        query = select(Calibration).where(Calibration.mi_number == serial_number)
        if year is not None:
            query = query.where(Calibration.year == year)
        if month is not None:
            query = query.where(Calibration.month == month)
        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def update_lk_details(self, cal_id: int, detail: dict[str, Any]) -> None:
        """Update calibration with LK details."""
        result = await self.db.execute(select(Calibration).where(Calibration.id == cal_id))
        cal = result.scalar_one_or_none()
        if cal:
            import json

            # verifierName from detailed LK record
            cal.verifier = detail.get("verifierName") or detail.get("author")

            # Conditions from detailed LK record
            conditions = {
                "temperature": detail.get("conditionsTemperature"),
                "humidity": detail.get("conditionsHymidity"),
                "pressure": detail.get("conditionsPressure"),
            }
            cal.conditions = json.dumps(conditions)

            # Modification from miInfo
            mi_info = detail.get("miInfo", {})
            vri_mi = mi_info.get("vriMi", {})
            cal.mi_modification = vri_mi.get("modification") or cal.mi_modification

            # Methodology from docTitle
            if detail.get("docTitle"):
                # Store in conditions or a separate field; for now append to conditions
                cond = json.loads(cal.conditions or "{}")
                cond["methodology"] = detail.get("docTitle")
                cal.conditions = json.dumps(cond)

            await self.db.commit()

    async def update_data2(self, cal_id: int, data2: dict[str, Any]) -> None:
        """Update calibration with extended data2."""
        result = await self.db.execute(select(Calibration).where(Calibration.id == cal_id))
        cal = result.scalar_one_or_none()
        if cal:
            import json

            # Merge data2 fields from detailed LK record
            if "factoryNum" in data2:
                cal.mi_number = str(data2.get("factoryNum", cal.mi_number or ""))
            if "mitypeNumber" in data2:
                cal.mit_number = data2.get("mitypeNumber", cal.mit_number)

            # Update conditions if present
            if any(k in data2 for k in ("conditionsTemperature", "conditionsHymidity", "conditionsPressure")):
                conditions = json.loads(cal.conditions or "{}")
                conditions["temperature"] = data2.get("conditionsTemperature", conditions.get("temperature"))
                conditions["humidity"] = data2.get("conditionsHymidity", conditions.get("humidity"))
                conditions["pressure"] = data2.get("conditionsPressure", conditions.get("pressure"))
                cal.conditions = json.dumps(conditions)

            await self.db.commit()

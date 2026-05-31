"""Calibration cache repository."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration_cache import CalibrationCache


class CalibrationCacheRepository:
    """Repository for CalibrationCache model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_year(self, year: int) -> Optional[CalibrationCache]:
        """Get cache entry for a specific year."""
        result = await self.db.execute(
            select(CalibrationCache).where(CalibrationCache.year == year)
        )
        return result.scalar_one_or_none()

    async def update_cache(self, year: int, total_records: int, ttl_hours: int = 168) -> CalibrationCache:
        """Update or create cache entry.
        
        Args:
            year: The year of calibration data
            total_records: Total number of records fetched
            ttl_hours: Cache time-to-live in hours (default 7 days)
        """
        cache = await self.get_by_year(year)
        now = datetime.utcnow()
        expires = now + timedelta(hours=ttl_hours)
        
        if cache:
            cache.total_records = total_records
            cache.last_fetched = now
            cache.expires_at = expires
        else:
            cache = CalibrationCache(
                year=year,
                total_records=total_records,
                last_fetched=now,
                expires_at=expires,
            )
            self.db.add(cache)
        
        await self.db.commit()
        await self.db.refresh(cache)
        return cache

    async def is_cache_valid(self, year: int) -> bool:
        """Check if cache is valid (exists and not expired)."""
        cache = await self.get_by_year(year)
        if not cache:
            return False
        return not cache.is_expired()

"""Check run repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.check_run import CheckRun


class CheckRunRepository:
    """Repository for CheckRun model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, run_id: int) -> CheckRun | None:
        """Get check run by ID."""
        result = await self.db.execute(
            select(CheckRun).where(CheckRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_by_month(self, year: int, month: int) -> list[CheckRun]:
        """Get check runs for a given month."""
        result = await self.db.execute(
            select(CheckRun)
            .where(CheckRun.year == year)
            .where(CheckRun.month == month)
            .order_by(CheckRun.started_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest(self) -> CheckRun | None:
        """Get the latest check run."""
        result = await self.db.execute(
            select(CheckRun).order_by(CheckRun.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

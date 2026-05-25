"""Check result repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.check_result import CheckResult


class CheckResultRepository:
    """Repository for CheckResult model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_run_id(self, run_id: int) -> list[CheckResult]:
        """Get all check results for a run."""
        result = await self.db.execute(
            select(CheckResult).where(CheckResult.check_run_id == run_id)
        )
        return list(result.scalars().all())

    async def get_errors(self, run_id: int) -> list[CheckResult]:
        """Get only error results for a run."""
        result = await self.db.execute(
            select(CheckResult)
            .where(CheckResult.check_run_id == run_id)
            .where(CheckResult.status.in_(["error", "missing"]))
        )
        return list(result.scalars().all())

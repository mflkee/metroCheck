"""Protocol file repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_file import ProtocolFile


class ProtocolFileRepository:
    """Repository for ProtocolFile model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_path(self, relative_path: str) -> ProtocolFile | None:
        """Get protocol file by relative path."""
        result = await self.db.execute(
            select(ProtocolFile).where(ProtocolFile.relative_path == relative_path)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, protocol_file_id: int) -> ProtocolFile | None:
        """Get protocol file by ID."""
        result = await self.db.execute(
            select(ProtocolFile).where(ProtocolFile.id == protocol_file_id)
        )
        return result.scalar_one_or_none()

    async def get_by_month(self, year: int, month: int) -> list[ProtocolFile]:
        """Get all protocol files for a given month."""
        result = await self.db.execute(
            select(ProtocolFile)
            .where(ProtocolFile.year == year)
            .where(ProtocolFile.month == month)
        )
        return list(result.scalars().all())

"""Protocol data repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_data import ProtocolData


class ProtocolDataRepository:
    """Repository for ProtocolData model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_serial(self, serial_number: str) -> ProtocolData | None:
        """Get protocol data by serial number (exact match)."""
        result = await self.db.execute(
            select(ProtocolData).where(ProtocolData.serial_number == serial_number)
        )
        return result.scalar_one_or_none()

    async def get_by_month(self, year: int, month: int) -> list[ProtocolData]:
        """Get all protocol data for a given month."""
        from app.models.protocol_file import ProtocolFile
        result = await self.db.execute(
            select(ProtocolData)
            .join(ProtocolFile)
            .where(ProtocolFile.year == year)
            .where(ProtocolFile.month == month)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ProtocolData:
        """Create new protocol data record."""
        data = ProtocolData(**kwargs)
        self.db.add(data)
        await self.db.commit()
        await self.db.refresh(data)
        return data

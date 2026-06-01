"""Protocol data repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_data import ProtocolData


class ProtocolDataRepository:
    """Repository for ProtocolData model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_protocol_file_id(self, protocol_file_id: int) -> ProtocolData | None:
        """Get protocol data by protocol file ID (latest)."""
        result = await self.db.execute(
            select(ProtocolData)
            .where(ProtocolData.protocol_file_id == protocol_file_id)
            .order_by(ProtocolData.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_by_protocol_file_id(self, protocol_file_id: int) -> int:
        """Delete all protocol data for a given protocol file."""
        from sqlalchemy import delete
        result = await self.db.execute(
            delete(ProtocolData).where(ProtocolData.protocol_file_id == protocol_file_id)
        )
        await self.db.commit()
        return result.rowcount

    async def get_by_serial(self, serial_number: str) -> ProtocolData | None:
        """Get protocol data by serial number (exact match)."""
        result = await self.db.execute(
            select(ProtocolData).where(ProtocolData.serial_number == serial_number).limit(1)
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

    async def get_by_mit_number(self, mit_number: str, year: int, month: int) -> ProtocolData | None:
        """Get protocol data by MIT number + year/month."""
        from app.models.protocol_file import ProtocolFile
        result = await self.db.execute(
            select(ProtocolData)
            .join(ProtocolFile)
            .where(ProtocolData.mit_number == mit_number)
            .where(ProtocolFile.year == year)
            .where(ProtocolFile.month == month)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> ProtocolData:
        """Create new protocol data record."""
        data = ProtocolData(**kwargs)
        self.db.add(data)
        await self.db.commit()
        await self.db.refresh(data)
        return data

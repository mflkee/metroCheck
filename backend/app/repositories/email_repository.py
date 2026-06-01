from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report_email import ReportEmail


class EmailRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> list[ReportEmail]:
        result = await self.db.execute(
            select(ReportEmail).order_by(ReportEmail.created_at)
        )
        return list(result.scalars().all())

    async def create(self, email: str) -> ReportEmail:
        entry = ReportEmail(email=email)
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete(self, email_id: int) -> bool:
        result = await self.db.execute(
            delete(ReportEmail).where(ReportEmail.id == email_id)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def get_by_email(self, email: str) -> Optional[ReportEmail]:
        result = await self.db.execute(
            select(ReportEmail).where(ReportEmail.email == email)
        )
        return result.scalar_one_or_none()

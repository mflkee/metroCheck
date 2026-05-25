"""AI request repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_request import AIRequest


class AIRequestRepository:
    """Repository for AIRequest model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> AIRequest:
        """Create new AI request log."""
        req = AIRequest(**kwargs)
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def get_stats(self) -> dict:
        """Get AI usage statistics."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(AIRequest.cost_usd).label("total_cost"),
            )
        )
        row = result.one()
        return {
            "total_requests": row.total or 0,
            "total_cost_usd": float(row.total_cost or 0),
        }

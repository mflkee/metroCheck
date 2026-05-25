"""AI request log."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIRequest(Base):
    """Log of AI model requests for cost tracking and monitoring."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(100))  # which workflow triggered
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    response_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="success")  # success / error / fallback
    error: Mapped[Optional[str]] = mapped_column(Text)
    protocol_file_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

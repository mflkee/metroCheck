"""Cache for ARSHIN calibration data fetching."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CalibrationCache(Base):
    """Tracks when calibration data was last fetched for a year."""

    __tablename__ = "calibration_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    def is_expired(self) -> bool:
        """Check if cache is expired."""
        return datetime.utcnow() > self.expires_at

"""Check result (результат проверки)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CheckResult(Base):
    """Result of a single check (completeness or data match)."""

    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_run_id: Mapped[int] = mapped_column(ForeignKey("check_runs.id"))
    calibration_id: Mapped[Optional[int]] = mapped_column(ForeignKey("calibrations.id"))
    protocol_data_id: Mapped[Optional[int]] = mapped_column(ForeignKey("protocol_data.id"))
    check_type: Mapped[str] = mapped_column(String(50))  # completeness / data_match / protocol_found
    status: Mapped[str] = mapped_column(String(50))  # ok / error / missing / warning
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

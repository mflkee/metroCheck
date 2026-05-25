"""Calibration (поверка) from ARSHIN."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Calibration(Base):
    """Calibration record from ARSHIN public API."""

    __tablename__ = "calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    vri_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    org_title: Mapped[str] = mapped_column(String(255), nullable=False)
    mit_number: Mapped[Optional[str]] = mapped_column(String(100))
    mit_title: Mapped[Optional[str]] = mapped_column(Text)
    mi_number: Mapped[Optional[str]] = mapped_column(String(100))  # serial number
    verification_date: Mapped[Optional[date]] = mapped_column(Date)
    valid_date: Mapped[Optional[date]] = mapped_column(Date)
    result_docnum: Mapped[Optional[str]] = mapped_column(String(100))  # document number
    result: Mapped[Optional[str]] = mapped_column(String(50))  # suitable / unsuitable
    verifier: Mapped[Optional[str]] = mapped_column(String(255))  # from LK
    conditions: Mapped[Optional[str]] = mapped_column(Text)  # JSON string from LK
    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

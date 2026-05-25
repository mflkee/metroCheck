"""Data extracted from PDF protocol by AI."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Date, DateTime, Float, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProtocolData(Base):
    """Extracted data from a protocol PDF."""

    __tablename__ = "protocol_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    protocol_file_id: Mapped[int] = mapped_column(ForeignKey("protocol_files.id"))
    protocol_number: Mapped[Optional[str]] = mapped_column(String(100))
    device_name: Mapped[Optional[str]] = mapped_column(String(255))
    device_type: Mapped[Optional[str]] = mapped_column(String(255))
    serial_number: Mapped[Optional[str]] = mapped_column(String(100))
    mit_number: Mapped[Optional[str]] = mapped_column(String(100))
    manufacture_year: Mapped[Optional[int]] = mapped_column(Integer)
    owner: Mapped[Optional[str]] = mapped_column(String(255))
    verification_date: Mapped[Optional[date]] = mapped_column(Date)
    verifier: Mapped[Optional[str]] = mapped_column(String(255))
    temperature: Mapped[Optional[float]] = mapped_column(Float)
    humidity: Mapped[Optional[float]] = mapped_column(Float)
    pressure: Mapped[Optional[float]] = mapped_column(Float)
    pressure_units: Mapped[Optional[str]] = mapped_column(String(50))
    result: Mapped[Optional[str]] = mapped_column(String(50))  # suitable / unsuitable
    verification_method: Mapped[Optional[str]] = mapped_column(Text)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="success")  # success / manual_review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    protocol_file: Mapped["ProtocolFile"] = relationship("ProtocolFile")

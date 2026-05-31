"""Protocol file (PDF) found on SMB share."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProtocolFile(Base):
    """PDF protocol file found during scan."""

    __tablename__ = "protocol_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending / scanned / error
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

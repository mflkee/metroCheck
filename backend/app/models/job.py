"""Job queue model for check runs."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Job(Base):
    """A job in the check queue."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    job_type: Mapped[str] = mapped_column(String(20), default="auto")  # auto / manual
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / running / paused / completed / failed / cancelled
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher = more important (manual=10, auto=0)
    
    # Progress tracking
    progress: Mapped[str] = mapped_column(String(255), default="")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Results
    check_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_json: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Who triggered
    triggered_by: Mapped[str] = mapped_column(String(50), default="system")  # system / user / cron
    
    # If this job is waiting for token
    waiting_for_token: Mapped[bool] = mapped_column(Boolean, default=False)

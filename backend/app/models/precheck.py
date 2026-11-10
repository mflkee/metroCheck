"""Справочник типов СИ и история проверок «перед АРШИНом»."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ArshinType(Base):
    """Утверждённый тип СИ (ОТ) из реестра АРШИН."""

    __tablename__ = "arshin_types"

    ot: Mapped[str] = mapped_column(String(32), primary_key=True)
    mit_uuid: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(512))
    notation: Mapped[str | None] = mapped_column(String(512))
    valid_to: Mapped[str | None] = mapped_column(String(16))
    spec_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArshinMpi(Base):
    """Межповерочный интервал типа: месяцев + текстовое условие."""

    __tablename__ = "arshin_mpi"

    id: Mapped[int] = mapped_column(primary_key=True)
    ot: Mapped[str] = mapped_column(String(32), index=True)
    months: Mapped[int | None] = mapped_column(Integer)
    parameter: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[str | None] = mapped_column(String(16))
    valid_to: Mapped[str | None] = mapped_column(String(16))


class ArshinMeth(Base):
    """Методика поверки типа."""

    __tablename__ = "arshin_meth"

    id: Mapped[int] = mapped_column(primary_key=True)
    ot: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    dec_num: Mapped[str | None] = mapped_column(String(128))
    valid_from: Mapped[str | None] = mapped_column(String(16))
    valid_to: Mapped[str | None] = mapped_column(String(16))


class PrecheckRun(Base):
    """Запуск проверки пачки перед загрузкой в АРШИН (файлы не сохраняем)."""

    __tablename__ = "precheck_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user: Mapped[str | None] = mapped_column(String(255))
    profile: Mapped[str] = mapped_column(String(16), default="mvp")
    files: Mapped[list | None] = mapped_column(JSONB)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[int] = mapped_column(Integer, default=0)
    report_path: Mapped[str | None] = mapped_column(String(512))


class ArshinMod(Base):
    """Модификация типа СИ (из описания типа / подтверждена вручную)."""

    __tablename__ = "arshin_mods"

    id: Mapped[int] = mapped_column(primary_key=True)
    ot: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(32), default="pdf")

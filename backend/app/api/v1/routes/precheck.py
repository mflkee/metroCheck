"""Проверка пачки перед загрузкой в АРШИН («Перед АРШИНом»)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user
from app.core.database import get_db
from app.models.precheck import ArshinMeth, ArshinMpi, ArshinType, PrecheckRun
from app.services.precheck import reference
from app.services.precheck.service import run_precheck

router = APIRouter()


class RunFileInfo(BaseModel):
    name: str
    sheet: str
    rows: int
    errors: int
    warnings: int


class RunTotals(BaseModel):
    rows: int
    errors: int
    warnings: int


class RunResponse(BaseModel):
    run_id: int
    profile: str
    files: list[RunFileInfo]
    skipped: list[str] = []
    totals: RunTotals
    report_url: str


class RunHistoryItem(BaseModel):
    id: int
    created_at: str
    user: str | None
    profile: str
    rows: int
    errors: int
    warnings: int


class ReferenceStats(BaseModel):
    types: int
    mpi: int
    meth: int


@router.post("/run", response_model=RunResponse)
async def run_check(
    files: list[UploadFile] = File(..., description="пачки .xlsm/.xlsx и/или XML"),
    profile: str = Form("mvp"),
    online: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> RunResponse:
    """Проверить загруженные файлы и вернуть сводку (отчёт — по report_url)."""
    if profile not in ("mvp", "full"):
        raise HTTPException(status_code=400, detail="profile должен быть mvp или full")
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        data = await upload.read()
        payload.append((upload.filename or "без имени", data))
    try:
        result = await run_precheck(
            db, payload, profile=profile, online=online,
            user=user.get("email") or user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunResponse(**result)


@router.get("/runs", response_model=list[RunHistoryItem])
async def list_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),  # noqa: ARG001
) -> list[RunHistoryItem]:
    """Последние проверки (файлы не храним — только статистику)."""
    rows = (await db.execute(
        select(PrecheckRun).order_by(PrecheckRun.created_at.desc()).limit(min(limit, 100))
    )).scalars()
    return [
        RunHistoryItem(
            id=r.id,
            created_at=r.created_at.strftime("%d.%m.%Y %H:%M"),
            user=r.user,
            profile=r.profile,
            rows=r.rows,
            errors=r.errors,
            warnings=r.warnings,
        )
        for r in rows
    ]


@router.get("/runs/{run_id}/report")
async def download_report(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),  # noqa: ARG001
) -> FileResponse:
    """Скачать отчёт проверки."""
    run = await db.get(PrecheckRun, run_id)
    if run is None or not run.report_path or not os.path.exists(run.report_path):
        raise HTTPException(status_code=404, detail="отчёт не найден")
    return FileResponse(
        run.report_path,
        filename=os.path.basename(run.report_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/reference", response_model=ReferenceStats)
async def reference_stats(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),  # noqa: ARG001
) -> ReferenceStats:
    """Сколько типов СИ в справочнике."""
    async def count(model: Any) -> int:
        return int((await db.execute(select(func.count()).select_from(model))).scalar() or 0)

    return ReferenceStats(types=await count(ArshinType), mpi=await count(ArshinMpi),
                          meth=await count(ArshinMeth))


@router.post("/reference/sync")
async def reference_sync(
    ots: str = Form("", description="номера ОТ через запятую или с новой строки"),
    limit: int = Form(500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),  # noqa: ARG001
) -> dict:
    """Обновить справочник по списку типов СИ из реестра АРШИН."""
    items = [part.strip() for part in ots.replace(",", "\n").split("\n") if part.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="передайте список ОТ (ots)")
    stats = await reference.sync_types(db, items, limit=min(limit, 1000), source="manual")
    return {"status": "ok", **stats}

"""Оркестратор проверки пачки: чтение файлов → правила → отчёт + запись истории."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.calibration import Calibration
from app.models.precheck import PrecheckRun
from app.services.precheck import loader, rules
from app.services.precheck.reference import ensure_types
from app.services.precheck.report import build_report

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_RECORDS = 50_000


@dataclass
class ParsedFile:
    name: str
    sheet: str
    records: list[dict]


REPORT_TTL_DAYS = 14


def _object_stats(parsed: list[ParsedFile], issues: list[rules.Issue]) -> list[dict]:
    """Сводка по объектам — если в файлах есть колонка «Объект».

    Схема «месяц × объект»: одна книга за месяц может содержать несколько объектов,
    и руководителю нужен итог по каждому. Если колонки нет — возвращаем пустой список.
    """
    row_object: dict[tuple[str, int], str] = {}
    stats: dict[str, dict] = {}
    for item in parsed:
        for r in item.records:
            obj = (r.get("object") or "").strip()
            if not obj:
                continue
            row_object[(item.name, r["row"])] = obj
            entry = stats.setdefault(obj, {"name": obj, "rows": 0, "errors": 0, "warnings": 0})
            entry["rows"] += 1
    if not stats:
        return []
    for issue in issues:
        obj = row_object.get((issue.file, issue.row))
        if not obj:
            continue
        if issue.level == rules.ERROR:
            stats[obj]["errors"] += 1
        elif issue.level == rules.WARNING:
            stats[obj]["warnings"] += 1
    return sorted(stats.values(), key=lambda s: (-s["errors"], -s["warnings"], s["name"]))


def _reports_dir() -> str:
    """Каталог отчётов (volume /reports — переживает пересоздание контейнера)."""
    path = settings.PRECHECK_REPORTS_DIR
    os.makedirs(path, exist_ok=True)
    cutoff = datetime.now().timestamp() - REPORT_TTL_DAYS * 86400
    for old in Path(path).glob("проверка_*.xlsx"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    return path


async def _load_history(
    session: AsyncSession, records: list[dict],
) -> tuple[dict[tuple[str, str], list[dict]], dict[str, dict]]:
    """История поверок из нашей базы: для проверки «раньше окончания предыдущей»
    и сверки с тем, что уже опубликовано."""
    from app.services.precheck.common import norm_number

    ots = sorted({(r.get("ot") or "").strip() for r in records if r.get("ot")})
    serials = {norm_number(r.get("mi_number") or r.get("inventory_number")) for r in records}
    serials.discard("")
    if not ots or not serials:
        return {}, {}

    rows = (await session.execute(
        select(Calibration).where(Calibration.mit_number.in_(ots))
    )).scalars()

    previous: dict[tuple[str, str], list[dict]] = {}
    published: dict[str, dict] = {}
    for cal in rows:
        key = (cal.mit_number or "", norm_number(cal.mi_number))
        if key[1] not in serials:
            continue
        item = {
            "vrf_date": cal.verification_date.isoformat() if cal.verification_date else None,
            "valid_date": cal.valid_date.isoformat() if cal.valid_date else None,
            "docnum": cal.result_docnum,
            "org": cal.org_title,
        }
        previous.setdefault(key, []).append(item)
        if cal.result_docnum:
            published[cal.result_docnum] = {
                "ot": cal.mit_number,
                "mi_number": cal.mi_number,
                "vrf_date": item["vrf_date"],
                "valid_date": item["valid_date"],
            }
    return previous, published


async def run_precheck(
    session: AsyncSession,
    files: list[tuple[str, bytes]],
    profile: str = "mvp",
    online: bool = True,
    user: str | None = None,
) -> dict:
    """Проверить файлы и сохранить отчёт.

    Возвращает словарь: run_id, files[], totals{}, report_url.
    """
    if not files:
        raise ValueError("не передано ни одного файла")

    parsed: list[ParsedFile] = []
    problems: list[str] = []
    conditions: dict[str, tuple[str, str, str]] = {}

    for name, data in files:
        if len(data) > MAX_FILE_BYTES:
            problems.append(f"{name}: файл больше 50 МБ")
            continue
        try:
            records, sheet = loader.read_batch(name, data)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: {exc}")
            continue
        if not records:
            problems.append(f"{name}: нет записей")
            continue
        if len(records) > MAX_RECORDS:
            problems.append(f"{name}: больше {MAX_RECORDS} записей — разбейте пачку")
            continue
        parsed.append(ParsedFile(name=name, sheet=sheet, records=records))
        if not conditions:
            conditions = loader.read_input_conditions(data)

    if not parsed:
        raise ValueError("ни один файл не удалось прочитать: " + "; ".join(problems))

    ots = sorted({(r.get("ot") or "").strip() for f in parsed for r in f.records
                  if r.get("ot")})
    types, ref_stats = await ensure_types(
        session, ots, online=online,
        limit=settings.PRECHECK_ONLINE_LIMIT,
        ttl_days=settings.PRECHECK_REFERENCE_TTL_DAYS,
    )

    previous, published = await _load_history(session, [r for f in parsed for r in f.records])

    ctx = rules.Context(
        types=types,
        previous=previous,
        published=published,
        conditions_by_date=conditions,
        profile=profile,
        mpi_mode=settings.PRECHECK_MPI_MODE,
        ot_expired=settings.PRECHECK_OT_EXPIRED,
        ot_expired_renewed=settings.PRECHECK_OT_EXPIRED_RENEWED,
        allowed_ciphers={c.strip().upper() for c in settings.PRECHECK_CIPHERS.split(",")
                         if c.strip()},
        successors=rules.build_successors(types),
        today=datetime.now().date().isoformat(),
    )

    all_issues: list[rules.Issue] = []
    file_rows: list[dict] = []
    titles = {ot: (card.get("title") or "") for ot, card in types.items()}

    for item in parsed:
        issues = rules.run(item.records, ctx)
        issues += rules.check_filename(item.name, item.records, titles)
        issues += rules.check_ciphers(item.records, ctx.allowed_ciphers)
        for issue in issues:
            issue.file = item.name
        all_issues.extend(issues)
        file_rows.append({
            "name": item.name,
            "sheet": item.sheet,
            "rows": len(item.records),
            "errors": sum(1 for i in issues if i.level == rules.ERROR),
            "warnings": sum(1 for i in issues if i.level == rules.WARNING),
        })

    reference_note = ""
    if ref_stats.get("refreshed"):
        reference_note = (f"справочник обновлён из АРШИН: {ref_stats['refreshed']} тип(ов), "
                          f"из них новых — {ref_stats['missing']}")
    objects = _object_stats(parsed, all_issues)
    report = build_report(file_rows, all_issues, profile, reference_note=reference_note,
                          objects=objects)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(_reports_dir(), f"проверка_{stamp}.xlsx")
    with open(report_path, "wb") as fh:
        fh.write(report)

    run = PrecheckRun(
        user=user,
        profile=profile,
        files=file_rows,
        rows=sum(f["rows"] for f in file_rows),
        errors=sum(f["errors"] for f in file_rows),
        warnings=sum(f["warnings"] for f in file_rows),
        report_path=report_path,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    return {
        "run_id": run.id,
        "profile": profile,
        "files": file_rows,
        "skipped": problems,
        "totals": {
            "rows": run.rows,
            "errors": run.errors,
            "warnings": run.warnings,
        },
        "report_url": f"/api/v1/precheck/runs/{run.id}/report",
    }

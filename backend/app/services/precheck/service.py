"""Оркестратор проверки пачки: чтение файлов → правила → отчёт + запись истории."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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


def _reports_dir() -> str:
    path = settings.PRECHECK_REPORTS_DIR
    os.makedirs(path, exist_ok=True)
    return path


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

    ctx = rules.Context(
        types=types,
        conditions_by_date=conditions,
        profile=profile,
        mpi_mode=settings.PRECHECK_MPI_MODE,
        ot_expired=settings.PRECHECK_OT_EXPIRED,
        allowed_ciphers={c.strip().upper() for c in settings.PRECHECK_CIPHERS.split(",")
                         if c.strip()},
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
    report = build_report(file_rows, all_issues, profile, reference_note=reference_note)
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

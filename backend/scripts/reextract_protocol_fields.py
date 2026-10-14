"""Одноразовая переобработка уже сохранённых протоколов.

Прогоняет regex-извлечение (`owner`, `serial_number`, `mit_number`,
`verification_date`) по сохранённому `raw_text` и обновляет те поля, где
исправленные правила дали другое значение. Полезно после правок извлечения —
пере-OCR протоколов не требуется.

Запуск (внутри контейнера бэкенда):

    docker exec -i metroCheck_backend python /app/scripts/reextract_protocol_fields.py --dry-run
    docker exec -i metroCheck_backend python /app/scripts/reextract_protocol_fields.py

`--dry-run` только показывает, что изменится (и примеры), ничего не пишет.
`--year 2026 --month 3` ограничивает выборку.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.protocol_extraction_service import ProtocolExtractionService

FIELDS = ("owner", "serial_number", "mit_number", "verification_date")


async def run(*, dry_run: bool, year: int | None, month: int | None) -> None:
    service = ProtocolExtractionService()

    where = []
    params: dict[str, int] = {}
    if year is not None:
        where.append("pf.year = :year")
        params["year"] = year
    if month is not None:
        where.append("pf.month = :month")
        params["month"] = month
    where_sql = ("where " + " and ".join(where)) if where else ""

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    f"""
                    select pd.id, pd.owner, pd.serial_number, pd.mit_number,
                           pd.verification_date::text as vdate, pd.raw_text, pf.file_name
                    from protocol_data pd
                    join protocol_files pf on pf.id = pd.protocol_file_id
                    {where_sql}
                    """
                ),
                params,
            )
        ).all()

        changes: Counter[str] = Counter()
        samples: dict[str, list] = {field: [] for field in FIELDS}
        updates: list[dict] = []

        for row in rows:
            raw = row.raw_text or ""
            new = {
                "owner": service._extract_owner(raw),
                "serial_number": service._extract_serial_number(raw, row.file_name),
                "mit_number": service._extract_mit_number(raw),
                "verification_date": service._extract_verification_date(raw),
            }
            current = {
                "owner": row.owner,
                "serial_number": row.serial_number,
                "mit_number": row.mit_number,
                "verification_date": row.vdate,
            }
            diff = {
                field: new[field]
                for field in FIELDS
                if (current[field] or "") != (new[field] or "")
            }
            if not diff:
                continue
            # asyncpg строг к типам: дату нужно передавать объектом date
            if diff.get("verification_date"):
                diff["verification_date"] = date.fromisoformat(diff["verification_date"])
            for field in diff:
                changes[field] += 1
                if len(samples[field]) < 10:
                    samples[field].append((row.id, current[field], diff[field]))
            updates.append({"id": row.id, **diff})

        print(f"протоколов проверено: {len(rows)}")
        print(f"к обновлению: {len(updates)}")
        for field in FIELDS:
            print(f"  {field}: {changes[field]}")
        for field in FIELDS:
            for pid, old, new in samples[field]:
                print(f"  [{field}] id={pid}: {old!r} -> {new!r}")

        if dry_run or not updates:
            print("dry-run: изменения не записаны")
            return

        written = 0
        try:
            for item in updates:
                pid = item.pop("id")
                set_sql = ", ".join(f"{field} = :{field}" for field in item)
                await session.execute(
                    text(f"update protocol_data set {set_sql} where id = :id"),
                    {**item, "id": pid},
                )
                written += 1
            await session.commit()
        except Exception:
            await session.rollback()
            print(f"ошибка, откат транзакции (успело записаться: {written})")
            raise
        print(f"обновлено записей: {written}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="не записывать изменения")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, year=args.year, month=args.month))


if __name__ == "__main__":
    main()

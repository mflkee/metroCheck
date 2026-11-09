"""Отчёт проверки: xlsx с листами «Сводка по файлам», «Все замечания», «Итоги»."""

from __future__ import annotations

import io
from collections import Counter
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.services.precheck.rules import ERROR, INFO, WARNING, Issue

RED = PatternFill("solid", fgColor="FFC7CE")
YELLOW = PatternFill("solid", fgColor="FFEB9C")
GREEN = PatternFill("solid", fgColor="C6EFCE")


def build_report(
    files: list[dict],
    issues: list[Issue],
    profile: str,
    checked_at: datetime | None = None,
    reference_note: str = "",
) -> bytes:
    """Собрать xlsx в память.

    files: [{name, sheet, rows, errors, warnings}]
    issues: замечания с привязкой к файлу через атрибут `file` (см. service)
    """
    wb = Workbook()

    ws = wb.active
    ws.title = "Сводка по файлам"
    ws.append(["Файл", "Лист", "Записей", "Ошибок", "Предупреждений"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for item in sorted(files, key=lambda f: (-f["errors"], -f["warnings"], f["name"])):
        ws.append([item["name"], item["sheet"], item["rows"], item["errors"],
                   item["warnings"]])
        if item["errors"]:
            for cell in ws[ws.max_row]:
                cell.fill = RED
        elif item["warnings"]:
            for cell in ws[ws.max_row]:
                cell.fill = YELLOW
    for i, width in enumerate([50, 14, 10, 10, 16], 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    ws2 = wb.create_sheet("Все замечания")
    ws2.append(["Файл", "Строка", "Колонка", "Уровень", "Правило", "Сообщение", "Подсказка"])
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    ordered = sorted(issues, key=lambda i: (i.file, i.row, i.level != ERROR))
    for issue in ordered:
        ws2.append([issue.file, issue.row, issue.column, issue.level,
                    issue.rule, issue.message, issue.hint])
        if issue.level == ERROR:
            ws2.cell(row=ws2.max_row, column=4).fill = RED
        elif issue.level == WARNING:
            ws2.cell(row=ws2.max_row, column=4).fill = YELLOW
    if ws2.max_row == 1:
        ws2.append(["—", "—", "—", "—", "—", "Замечаний нет", ""])
        ws2.cell(row=2, column=4).fill = GREEN
    for i, width in enumerate([40, 8, 24, 14, 22, 80, 55], 1):
        ws2.column_dimensions[ws2.cell(row=1, column=i).column_letter].width = width
    ws2.freeze_panes = "A2"
    ws2.auto_filter.ref = ws2.dimensions

    ws3 = wb.create_sheet("Итоги")
    errors = sum(1 for i in issues if i.level == ERROR)
    warnings = sum(1 for i in issues if i.level == WARNING)
    info = sum(1 for i in issues if i.level == INFO)
    ws3.append(["Профиль", "mvp — МПИ и ОТ (по ТЗ)" if profile == "mvp" else "full — все правила"])
    ws3.append(["Проверено", (checked_at or datetime.now()).strftime("%d.%m.%Y %H:%M")])
    ws3.append(["Файлов", len(files)])
    ws3.append(["Записей", sum(f["rows"] for f in files)])
    ws3.append(["Ошибок (блокируют загрузку)", errors])
    ws3.append(["Предупреждений", warnings])
    ws3.append(["Информационных", info])
    if reference_note:
        ws3.append(["Справочник", reference_note])
    ws3.append([])
    ws3.append(["Правило", "Ошибок"])
    ws3.cell(row=ws3.max_row, column=1).font = Font(bold=True)
    by_rule = Counter(i.rule for i in issues if i.level == ERROR)
    for rule, count in by_rule.most_common():
        ws3.append([rule, count])
    ws3.column_dimensions["A"].width = 34
    ws3.column_dimensions["B"].width = 60
    for row in ws3.iter_rows(min_row=1, max_row=7):
        row[1].alignment = Alignment(wrap_text=True)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

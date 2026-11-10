"""Отчёт проверки пачки — в оформлении отчётов metroCheck.

Структура и стиль повторяют ReportService (сводка проверки протоколов):
синий заголовок листа, серая отметка формирования, KPI-строка с цветными значениями,
таблица с синей шапкой, итоговая строка, тонкие границы, автофильтр и закреплённые шапки.
"""

from __future__ import annotations

import io
import math
from collections import Counter
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services.precheck.rules import ERROR, WARNING, Issue

# ── палитра metroCheck ────────────────────────────────────────────────
SECTION_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
SECTION_FONT = Font(bold=True, color="FFFFFF", size=12)
HEADER_FILL = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
TOTAL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
TOTAL_FONT = Font(bold=True, color="305496")
LABEL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
LABEL_FONT = Font(color="305496", bold=True, size=9)
VALUE_FONT = Font(color="305496", bold=True, size=16)
GOOD_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
GOOD_FONT = Font(color="006100", bold=True)
WARN_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
WARN_FONT = Font(color="9C5700", bold=True)
BAD_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
BAD_FONT = Font(color="9C0006", bold=True)
MUTED = Font(color="808080", size=9, italic=True)
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

LINE_HEIGHT = 14.5
ROW_PADDING = 4.0


def _write(ws: Worksheet, row: int, col: int, value: object, *, fill=None, font=None,
           align: Alignment | None = None, border: Border | None = None) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    if fill is not None:
        cell.fill = fill
    if font is not None:
        cell.font = font
    cell.alignment = align or Alignment(vertical="center", wrap_text=True)
    if border is not None:
        cell.border = border


def _widths(ws: Worksheet, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _fit_rows(ws: Worksheet, first: int, last: int, widths: dict[int, float],
              min_height: float = 15.0) -> None:
    """Подобрать высоту строк под перенос текста (Excel сам не умеет для merged/переносов)."""
    for row in range(first, last + 1):
        lines = 1
        for col in range(1, (ws.max_column or 1) + 1):
            cell = ws.cell(row=row, column=col)
            if cell.value is None or isinstance(cell.value, (int, float)):
                continue
            width = widths.get(col, 8.43)
            per_line = max(int(width * 1.05), 6)
            text = str(cell.value)
            estimate = 0
            for chunk in text.split("\n"):
                estimate += max(1, math.ceil(len(chunk) / per_line))
            lines = max(lines, estimate)
        ws.row_dimensions[row].height = max(min_height, lines * LINE_HEIGHT + ROW_PADDING)


def _status(errors: int, warnings: int) -> tuple[str, PatternFill, Font]:
    if errors:
        return "Ошибки", BAD_FILL, BAD_FONT
    if warnings:
        return "Замечания", WARN_FILL, WARN_FONT
    return "OK", GOOD_FILL, GOOD_FONT


def build_report(
    files: list[dict],
    issues: list[Issue],
    profile: str,
    checked_at: datetime | None = None,
    reference_note: str = "",
) -> bytes:
    """Собрать xlsx в память (два листа: «Сводка» и «Замечания»)."""
    stamp = (checked_at or datetime.now()).strftime("%d.%m.%Y %H:%M")
    errors = [i for i in issues if i.level == ERROR]
    warnings = [i for i in issues if i.level == WARNING]
    rows_total = sum(f["rows"] for f in files)

    wb = Workbook()

    # ────────────────────────────── лист «Сводка» ──────────────────────────────
    ws = wb.active
    ws.title = "Сводка"
    widths = {1: 46, 2: 12, 3: 12, 4: 14, 5: 16}
    _widths(ws, widths)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    _write(ws, 1, 1, "Проверка пачки перед загрузкой в АРШИН",
           fill=SECTION_FILL, font=SECTION_FONT,
           align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=5)
    _write(ws, 2, 1,
           f"Сформировано: {stamp}  ·  metroCheck  ·  профиль: "
           f"{'МПИ, ОТ, методика' if profile == 'mvp' else 'полный'}",
           font=MUTED, align=Alignment(horizontal="right", vertical="center"))
    ws.row_dimensions[2].height = 16

    kpi = [
        ("Файлов", len(files), "plain"),
        ("Записей", rows_total, "plain"),
        ("Ошибок", len(errors), "bad" if errors else "good"),
        ("Предупреждений", len(warnings), "warn" if warnings else "good"),
        ("Статус", "Готово к загрузке" if not errors else "Есть ошибки",
         "good" if not errors else "bad"),
    ]
    value_style = {
        "good": (GOOD_FILL, GOOD_FONT),
        "warn": (WARN_FILL, WARN_FONT),
        "bad": (BAD_FILL, BAD_FONT),
        "plain": (None, VALUE_FONT),
    }
    for col, (label, value, kind) in enumerate(kpi, 1):
        _write(ws, 4, col, label, fill=LABEL_FILL, font=LABEL_FONT,
               align=Alignment(horizontal="center", vertical="center"))
        fill, font = value_style[kind]
        _write(ws, 5, col, value, fill=fill,
               font=font if kind != "plain" else Font(color="305496", bold=True, size=12),
               align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[4].height = 28
    ws.row_dimensions[5].height = 34

    row = 7
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    _write(ws, row, 1, "Разбивка по файлам", fill=SECTION_FILL, font=SECTION_FONT,
           align=Alignment(horizontal="left", vertical="center"))
    ws.row_dimensions[row].height = 24

    row += 1
    file_header = ["Файл", "Лист", "Записей", "Ошибок", "Предупр.", "Статус"]
    widths = {1: 50, 2: 12, 3: 12, 4: 12, 5: 12, 6: 18}
    _widths(ws, widths)
    for col, title in enumerate(file_header, 1):
        _write(ws, row, col, title, fill=HEADER_FILL, font=HEADER_FONT, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[row].height = 22
    header_row = row

    row += 1
    first_data_row = row
    for item in sorted(files, key=lambda f: (-f["errors"], -f["warnings"], f["name"])):
        _write(ws, row, 1, item["name"], border=THIN)
        _write(ws, row, 2, item["sheet"], border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws, row, 3, item["rows"], border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws, row, 4, item["errors"], border=THIN,
               align=Alignment(horizontal="center", vertical="center"),
               fill=BAD_FILL if item["errors"] else None,
               font=BAD_FONT if item["errors"] else None)
        _write(ws, row, 5, item["warnings"], border=THIN,
               align=Alignment(horizontal="center", vertical="center"),
               fill=WARN_FILL if item["warnings"] else None,
               font=WARN_FONT if item["warnings"] else None)
        status, fill, font = _status(item["errors"], item["warnings"])
        _write(ws, row, 6, status, fill=fill, font=font, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        row += 1
    _fit_rows(ws, first_data_row, row - 1, widths, min_height=16)

    # итоговая строка
    _write(ws, row, 1, "Итого", fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN)
    for col, key in ((2, None), (3, "rows"), (4, "errors"), (5, "warnings")):
        value = sum(f[key] for f in files) if key else ""
        _write(ws, row, col, value, fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
    _write(ws, row, 6, "", fill=TOTAL_FILL, border=THIN)
    ws.row_dimensions[row].height = 16
    row += 2

    # разбивка по правилам
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    _write(ws, row, 1, "Разбивка по правилам", fill=SECTION_FILL, font=SECTION_FONT,
           align=Alignment(horizontal="left", vertical="center"))
    ws.row_dimensions[row].height = 24

    row += 1
    for col, title in enumerate(["Правило", "Ошибок", "Предупр.", "", "", ""], 1):
        if title:
            _write(ws, row, col, title, fill=HEADER_FILL, font=HEADER_FONT, border=THIN,
                   align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[row].height = 22

    row += 1
    by_rule_err = Counter(i.rule for i in errors)
    by_rule_warn = Counter(i.rule for i in warnings)
    rules_sorted = sorted(set(by_rule_err) | set(by_rule_warn),
                          key=lambda r: (-by_rule_err.get(r, 0), -by_rule_warn.get(r, 0), r))
    if not rules_sorted:
        _write(ws, row, 1, "Замечаний нет", fill=GOOD_FILL, font=GOOD_FONT, border=THIN,
               align=Alignment(horizontal="left", vertical="center"))
        row += 1
    for rule in rules_sorted:
        _write(ws, row, 1, rule, border=THIN)
        _write(ws, row, 2, by_rule_err.get(rule, 0), border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws, row, 3, by_rule_warn.get(rule, 0), border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        row += 1

    row += 1
    legend = [
        ("Красное", "ошибка: с такой пачкой загрузка не пройдёт или данные уйдут неверные",
         BAD_FILL, BAD_FONT),
        ("Жёлтое", "предупреждение: посмотреть и решить", WARN_FILL, WARN_FONT),
        ("Зелёное", "всё в порядке", GOOD_FILL, GOOD_FONT),
    ]
    for label, text, fill, font in legend:
        _write(ws, row, 1, label, fill=fill, font=font, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        _write(ws, row, 2, text, align=Alignment(horizontal="left", vertical="center"))
        row += 1

    if reference_note:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        _write(ws, row, 1, reference_note, font=MUTED,
               align=Alignment(horizontal="left", vertical="center"))
    ws.sheet_view.showGridLines = False

    # ───────────────────────────── лист «Замечания» ─────────────────────────────
    ws2 = wb.create_sheet("Замечания")
    widths2 = {1: 34, 2: 8, 3: 20, 4: 14, 5: 20, 6: 70, 7: 48}
    _widths(ws2, widths2)

    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
    _write(ws2, 1, 1, "Замечания по пачке", fill=SECTION_FILL, font=SECTION_FONT,
           align=Alignment(horizontal="center", vertical="center"))
    ws2.row_dimensions[1].height = 28

    ws2.merge_cells(start_row=2, start_column=1, end_row=2, end_column=7)
    _write(ws2, 2, 1, f"Сформировано: {stamp}  ·  metroCheck", font=MUTED,
           align=Alignment(horizontal="right", vertical="center"))
    ws2.row_dimensions[2].height = 16

    headers2 = ["Файл", "Стр.", "Колонка", "Уровень", "Правило", "Что не так", "Что делать"]
    for col, title in enumerate(headers2, 1):
        _write(ws2, 3, col, title, fill=HEADER_FILL, font=HEADER_FONT, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
    ws2.row_dimensions[3].height = 22

    ordered = sorted(issues, key=lambda i: (i.file, i.row, i.level != ERROR))
    row = 4
    if not ordered:
        ws2.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        _write(ws2, row, 1, "Замечаний нет: все записи прошли проверку",
               fill=GOOD_FILL, font=GOOD_FONT, border=THIN,
               align=Alignment(horizontal="left", vertical="center"))
        row += 1
    for issue in ordered:
        is_error = issue.level == ERROR
        _write(ws2, row, 1, issue.file, border=THIN)
        _write(ws2, row, 2, issue.row if issue.row else "—", border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws2, row, 3, issue.column or "—", border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws2, row, 4, "ошибка" if is_error else "предупреждение",
               fill=BAD_FILL if is_error else WARN_FILL,
               font=BAD_FONT if is_error else WARN_FONT, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
        _write(ws2, row, 5, issue.rule, border=THIN)
        _write(ws2, row, 6, issue.message, border=THIN)
        _write(ws2, row, 7, issue.hint or "", border=THIN)
        row += 1

    if ordered:
        _fit_rows(ws2, 4, row - 1, widths2, min_height=16)
    ws2.freeze_panes = "A4"
    ws2.auto_filter.ref = f"A3:G{max(row - 1, 4)}"
    ws2.sheet_view.showGridLines = False

    # автофильтр и закрепление на сводке
    ws.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

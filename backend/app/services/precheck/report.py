"""Отчёт проверки пачки — в оформлении отчётов metroCheck.

Вёрстка повторяет сводку проверки протоколов (`ReportService`): широкий лист из
8 колонок, синяя плашка заголовка, серая отметка формирования, KPI-карточки,
отдельная полоса статуса, секции с отбивкой, синие шапки таблиц, итоговые строки,
зебра в списке замечаний и настройки печати.
"""

from __future__ import annotations

import io
import math
from collections import Counter
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

from app.services.precheck.rules import ERROR, INFO, WARNING, Issue

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
KPI_SMALL_FONT = Font(color="305496", bold=True, size=12)
GOOD_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
GOOD_FONT = Font(color="006100", bold=True)
WARN_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
WARN_FONT = Font(color="9C5700", bold=True)
BAD_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
BAD_FONT = Font(color="9C0006", bold=True)
ZEBRA_FILL = PatternFill(start_color="F5F8FC", end_color="F5F8FC", fill_type="solid")
INFO_FILL = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
INFO_FONT = Font(color="1F4E79")
MUTED = Font(color="808080", size=9, italic=True)
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

LINE_HEIGHT = 14.5
ROW_PADDING = 4.0
LAST_COL = 8

# ширины листа «Сводка»: под файлы, объекты и правила одновременно
SUMMARY_WIDTHS = {1: 44, 2: 16, 3: 13, 4: 13, 5: 13, 6: 14, 7: 16, 8: 20}
ISSUES_WIDTHS = {1: 34, 2: 6, 3: 15, 4: 17, 5: 20, 6: 60, 7: 42}

# человеческие названия правил для отчёта
RULE_LABEL = {
    "обязательное поле": "Обязательные поля",
    "ОТ не найден": "ОТ не найден",
    "ОТ не действует": "ОТ не действует",
    "ОТ распознан": "ОТ распознан (справочно)",
    "МПИ": "МПИ",
    "МПИ не установлен": "МПИ не установлен",
    "повторная поверка": "Повторная поверка",
    "методика": "Методика поверки",
    "модификация": "Модификация",
    "дата": "Даты поверки",
    "дубли": "Дубли заводских номеров",
    "похоже на протяжку": "Похоже на протяжку ОТ",
    "условия среды": "Условия среды",
    "опубликовано": "Сверка с АРШИН",
    "имя файла": "Имя файла",
    "чужой файл": "Чужой файл",
    "сбой правила": "Сбой правила",
}

# короткое объяснение для разбивки по правилам
RULE_DESC = {
    "обязательное поле": "не заполнено поле, без которого АРШИН не примет запись",
    "ОТ не найден": "номера типа нет в реестре — запись не пройдёт",
    "ОТ не действует": "срок утверждения типа истёк до даты поверки",
    "ОТ распознан": "справочно: тип найден в реестре, это не замечание",
    "МПИ": "«действительно до» не соответствует межповерочному интервалу",
    "МПИ не установлен": "в карточке типа нет интервала — проверить вручную",
    "повторная поверка": "новая поверка раньше окончания предыдущей",
    "методика": "методика не совпадает с действующей редакцией в описании типа",
    "модификация": "модификации нет в перечне типа (описание типа)",
    "дата": "дата поверки позже «действительно до» или в будущем",
    "дубли": "один заводской номер встречается несколько раз",
    "похоже на протяжку": "номер ОТ похож на соседний из реестра",
    "условия среды": "условия в строке расходятся с листом «Ввод»",
    "опубликовано": "сверка со записью, уже опубликованной в АРШИН",
    "имя файла": "имя файла не совпадает с содержимым",
    "чужой файл": "шифр клейма другой организации",
    "сбой правила": "внутренняя ошибка проверки",
}


# ── вспомогательные функции оформления ────────────────────────────────
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


def _span(ws: Worksheet, row: int, first: int, last: int, value: object = None, *,
          fill=None, font=None, align: Alignment | None = None,
          border: Border | None = None) -> None:
    """Записать значение в объединённый диапазон и закрасить его целиком."""
    if last > first:
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
    for col in range(first, last + 1):
        cell = ws.cell(row=row, column=col)
        if fill is not None:
            cell.fill = fill
        if border is not None:
            cell.border = border
        if col == first:
            cell.value = value
            if font is not None:
                cell.font = font
            cell.alignment = align or Alignment(vertical="center", wrap_text=True)
        else:
            cell.alignment = Alignment(vertical="center")


def _widths(ws: Worksheet, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _fit_rows(ws: Worksheet, first: int, last: int, widths: dict[int, float],
              min_height: float = 16.5) -> None:
    """Подобрать высоту строк под перенос текста (в том числе в объединённых ячейках)."""
    merged_width: dict[tuple[int, int], float] = {}
    merged_skip: set[tuple[int, int]] = set()
    for rng in ws.merged_cells.ranges:
        width = sum(widths.get(c, 8.43) for c in range(rng.min_col, rng.max_col + 1))
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) == (rng.min_row, rng.min_col):
                    merged_width[(r, c)] = width
                else:
                    merged_skip.add((r, c))

    for row in range(first, last + 1):
        lines = 1
        for col in range(1, (ws.max_column or 1) + 1):
            if (row, col) in merged_skip:
                continue
            cell = ws.cell(row=row, column=col)
            if cell.value is None or isinstance(cell.value, (int, float)):
                continue
            width = merged_width.get((row, col), widths.get(col, 8.43))
            per_line = max(int(width * 1.05), 6)
            estimate = sum(max(1, math.ceil(len(chunk) / per_line))
                           for chunk in str(cell.value).split("\n"))
            lines = max(lines, estimate)
        ws.row_dimensions[row].height = max(min_height, lines * LINE_HEIGHT + ROW_PADDING)


def _status(errors: int, warnings: int) -> tuple[str, PatternFill, Font]:
    if errors:
        return "Ошибки", BAD_FILL, BAD_FONT
    if warnings:
        return "Замечания", WARN_FILL, WARN_FONT
    return "OK", GOOD_FILL, GOOD_FONT


def _band(ws: Worksheet, row: int, title: str) -> int:
    """Синяя плашка секции на всю ширину листа."""
    _span(ws, row, 1, LAST_COL, title, fill=SECTION_FILL, font=SECTION_FONT,
          align=Alignment(horizontal="left", vertical="center"))
    ws.row_dimensions[row].height = 24
    return row + 1


def _setup_print(ws: Worksheet, title_rows: str | None) -> None:
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if title_rows:
        ws.print_title_rows = title_rows
    ws.print_options.horizontalCentered = True
    ws.sheet_view.showGridLines = False


def build_report(
    files: list[dict],
    issues: list[Issue],
    profile: str,
    checked_at: datetime | None = None,
    reference_note: str = "",
    objects: list[dict] | None = None,
) -> bytes:
    """Собрать xlsx в память (листы «Сводка» и «Замечания»)."""
    stamp = (checked_at or datetime.now()).strftime("%d.%m.%Y %H:%M")
    errors = [i for i in issues if i.level == ERROR]
    warnings = [i for i in issues if i.level == WARNING]
    rows_total = sum(f["rows"] for f in files)
    files_with_errors = sum(1 for f in files if f["errors"])

    wb = Workbook()

    # ────────────────────────────── лист «Сводка» ──────────────────────────────
    ws = wb.active
    ws.title = "Сводка"
    ws.sheet_properties.tabColor = "4472C4"
    _widths(ws, SUMMARY_WIDTHS)

    # заголовок и отметка формирования
    _span(ws, 1, 1, LAST_COL, "Проверка пачки перед загрузкой в АРШИН",
          fill=SECTION_FILL, font=SECTION_FONT,
          align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[1].height = 30

    _span(ws, 2, 1, LAST_COL,
          f"Сформировано: {stamp}  ·  metroCheck  ·  профиль: "
          f"{'МПИ, ОТ, методика' if profile == 'mvp' else 'полный'}",
          font=MUTED, align=Alignment(horizontal="right", vertical="center"))
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 6

    # KPI: четыре карточки по две колонки
    kpi = [
        ("ФАЙЛОВ", len(files), "plain"),
        ("ЗАПИСЕЙ", rows_total, "plain"),
        ("ОШИБОК", len(errors), "bad" if errors else "good"),
        ("ПРЕДУПРЕЖДЕНИЙ", len(warnings), "warn" if warnings else "good"),
    ]
    value_style = {
        "good": (GOOD_FILL, Font(color="006100", bold=True, size=16)),
        "warn": (WARN_FILL, Font(color="9C5700", bold=True, size=16)),
        "bad": (BAD_FILL, Font(color="9C0006", bold=True, size=16)),
        "plain": (None, VALUE_FONT),
    }
    for index, (label, value, kind) in enumerate(kpi):
        first = 1 + index * 2
        _span(ws, 4, first, first + 1, label, fill=LABEL_FILL, font=LABEL_FONT,
              align=Alignment(horizontal="center", vertical="center"))
        fill, font = value_style[kind]
        _span(ws, 5, first, first + 1, value, fill=fill,
              font=font if kind != "plain" else VALUE_FONT,
              align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[4].height = 26
    ws.row_dimensions[5].height = 42

    # полоса статуса
    if errors:
        status_text = (f"Есть ошибки: {len(errors)} — с такой пачкой загрузка в АРШИН "
                       f"не пройдёт. Исправьте красное на листе «Замечания».")
        status_fill, status_font = BAD_FILL, BAD_FONT
    elif warnings:
        status_text = (f"Готово к загрузке, но есть {len(warnings)} предупреждений — "
                       f"посмотрите жёлтое на листе «Замечания».")
        status_fill, status_font = WARN_FILL, WARN_FONT
    else:
        status_text = "Готово к загрузке: замечаний нет."
        status_fill, status_font = GOOD_FILL, GOOD_FONT
    _span(ws, 6, 1, LAST_COL, status_text, fill=status_fill,
          font=Font(bold=True, size=11, color=status_font.color),
          align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[6].height = 30
    ws.row_dimensions[7].height = 10

    row = 8

    # ── разбивка по файлам ─────────────────────────────────────────────
    row = _band(ws, row, "Разбивка по файлам")
    file_spans = [(1, 1, "Файл"), (2, 2, "Лист"), (3, 3, "Записей"),
                  (4, 4, "Ошибок"), (5, 5, "Предупр."), (6, LAST_COL, "Статус")]
    for first, last, title in file_spans:
        _span(ws, row, first, last, title, fill=HEADER_FILL, font=HEADER_FONT,
              border=THIN, align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[row].height = 22
    row += 1

    first_data = row
    for index, item in enumerate(sorted(
            files, key=lambda f: (-f["errors"], -f["warnings"], f["name"]))):
        zebra = ZEBRA_FILL if index % 2 else None
        _span(ws, row, 1, 1, item["name"], fill=zebra, border=THIN,
              align=Alignment(horizontal="left", vertical="center", wrap_text=True))
        _span(ws, row, 2, 2, item["sheet"], fill=zebra, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 3, 3, item["rows"], fill=zebra, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 4, 4, item["errors"], fill=BAD_FILL if item["errors"] else zebra,
              font=BAD_FONT if item["errors"] else None, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 5, 5, item["warnings"], fill=WARN_FILL if item["warnings"] else zebra,
              font=WARN_FONT if item["warnings"] else None, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        status, fill, font = _status(item["errors"], item["warnings"])
        _span(ws, row, 6, LAST_COL, status, fill=fill, font=font, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        row += 1
    _fit_rows(ws, first_data, row - 1, SUMMARY_WIDTHS)

    _span(ws, row, 1, 1, "Итого", fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN)
    _span(ws, row, 2, 2, "", fill=TOTAL_FILL, border=THIN)
    _span(ws, row, 3, 3, rows_total, fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
          align=Alignment(horizontal="center", vertical="center"))
    _span(ws, row, 4, 4, len(errors), fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
          align=Alignment(horizontal="center", vertical="center"))
    _span(ws, row, 5, 5, len(warnings), fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
          align=Alignment(horizontal="center", vertical="center"))
    _span(ws, row, 6, LAST_COL, f"файлов с ошибками: {files_with_errors}/{len(files)}",
          fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
          align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[row].height = 18
    row += 2
    ws.row_dimensions[row - 1].height = 8

    # ── разбивка по объектам (если в книгах есть колонка «Объект») ─────
    if objects:
        row = _band(ws, row, "Разбивка по объектам")
        object_spans = [(1, 2, "Объект"), (3, 3, "Записей"), (4, 4, "Ошибок"),
                        (5, 5, "Предупр."), (6, LAST_COL, "Статус")]
        for first, last, title in object_spans:
            _span(ws, row, first, last, title, fill=HEADER_FILL, font=HEADER_FONT,
                  border=THIN, align=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 22
        row += 1

        first_data = row
        for index, item in enumerate(objects):
            zebra = ZEBRA_FILL if index % 2 else None
            _span(ws, row, 1, 2, item["name"], fill=zebra, border=THIN,
                  align=Alignment(horizontal="left", vertical="center", wrap_text=True))
            _span(ws, row, 3, 3, item["rows"], fill=zebra, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            _span(ws, row, 4, 4, item["errors"], fill=BAD_FILL if item["errors"] else zebra,
                  font=BAD_FONT if item["errors"] else None, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            _span(ws, row, 5, 5, item["warnings"],
                  fill=WARN_FILL if item["warnings"] else zebra,
                  font=WARN_FONT if item["warnings"] else None, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            status, fill, font = _status(item["errors"], item["warnings"])
            _span(ws, row, 6, LAST_COL, status, fill=fill, font=font, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            row += 1
        _fit_rows(ws, first_data, row - 1, SUMMARY_WIDTHS)
        row += 2
        ws.row_dimensions[row - 1].height = 8

    # ── разбивка по правилам ───────────────────────────────────────────
    row = _band(ws, row, "Разбивка по правилам")
    rule_spans = [(1, 3, "Правило"), (4, 4, "Ошибок"), (5, 5, "Предупр."),
                  (6, LAST_COL, "Что это значит")]
    for first, last, title in rule_spans:
        _span(ws, row, first, last, title, fill=HEADER_FILL, font=HEADER_FONT,
              border=THIN, align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[row].height = 22
    row += 1

    by_rule_err = Counter(i.rule for i in errors)
    by_rule_warn = Counter(i.rule for i in warnings)
    rules_sorted = sorted(set(by_rule_err) | set(by_rule_warn),
                          key=lambda r: (-by_rule_err.get(r, 0), -by_rule_warn.get(r, 0), r))
    if not rules_sorted:
        status, fill, font = "OK", GOOD_FILL, GOOD_FONT
        _span(ws, row, 1, LAST_COL, "Замечаний нет: все записи прошли проверку",
              fill=fill, font=font, border=THIN,
              align=Alignment(horizontal="left", vertical="center"))
        ws.row_dimensions[row].height = 20
        row += 1
    else:
        first_data = row
        for index, rule in enumerate(rules_sorted):
            zebra = ZEBRA_FILL if index % 2 else None
            err_count = by_rule_err.get(rule, 0)
            warn_count = by_rule_warn.get(rule, 0)
            _span(ws, row, 1, 3, RULE_LABEL.get(rule, rule), fill=zebra, border=THIN,
                  align=Alignment(horizontal="left", vertical="center", wrap_text=True))
            _span(ws, row, 4, 4, err_count, fill=BAD_FILL if err_count else zebra,
                  font=BAD_FONT if err_count else None, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            _span(ws, row, 5, 5, warn_count, fill=WARN_FILL if warn_count else zebra,
                  font=WARN_FONT if warn_count else None, border=THIN,
                  align=Alignment(horizontal="center", vertical="center"))
            _span(ws, row, 6, LAST_COL, RULE_DESC.get(rule, ""), fill=zebra, border=THIN,
                  align=Alignment(horizontal="left", vertical="center", wrap_text=True))
            row += 1
        _fit_rows(ws, first_data, row - 1, SUMMARY_WIDTHS)
        _span(ws, row, 1, 3, "Итого", fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN)
        _span(ws, row, 4, 4, len(errors), fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 5, 5, len(warnings), fill=TOTAL_FILL, font=TOTAL_FONT, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 6, LAST_COL, "", fill=TOTAL_FILL, border=THIN)
        ws.row_dimensions[row].height = 18
        row += 1
    row += 1
    ws.row_dimensions[row - 1].height = 8

    # ── легенда ────────────────────────────────────────────────────────
    row = _band(ws, row, "Как читать отчёт")
    legend = [
        ("Красное", "ошибка: с такой пачкой загрузка не пройдёт или данные уйдут неверные",
         BAD_FILL, BAD_FONT),
        ("Жёлтое", "предупреждение: посмотреть и решить (например, истёк срок типа)",
         WARN_FILL, WARN_FONT),
        ("Зелёное", "всё в порядке", GOOD_FILL, GOOD_FONT),
    ]
    for label, text, fill, font in legend:
        _span(ws, row, 1, 1, label, fill=fill, font=font, border=THIN,
              align=Alignment(horizontal="center", vertical="center"))
        _span(ws, row, 2, LAST_COL, text, border=THIN,
              align=Alignment(horizontal="left", vertical="center", wrap_text=True))
        ws.row_dimensions[row].height = 20
        row += 1

    if reference_note:
        row += 1
        _span(ws, row, 1, LAST_COL, reference_note, font=MUTED,
              align=Alignment(horizontal="left", vertical="center"))
    _setup_print(ws, title_rows=None)

    # ───────────────────────────── лист «Замечания» ─────────────────────────────
    ws2 = wb.create_sheet("Замечания")
    ws2.sheet_properties.tabColor = "5B9BD5"
    _widths(ws2, ISSUES_WIDTHS)

    _span(ws2, 1, 1, 7, "Замечания по пачке", fill=SECTION_FILL, font=SECTION_FONT,
          align=Alignment(horizontal="center", vertical="center"))
    ws2.row_dimensions[1].height = 30

    _span(ws2, 2, 1, 7, f"Сформировано: {stamp}  ·  metroCheck", font=MUTED,
          align=Alignment(horizontal="right", vertical="center"))
    ws2.row_dimensions[2].height = 18

    # полоса счёта
    counts = f"Ошибок: {len(errors)}   ·   Предупреждений: {len(warnings)}"
    fill = BAD_FILL if errors else (WARN_FILL if warnings else GOOD_FILL)
    font = BAD_FONT if errors else (WARN_FONT if warnings else GOOD_FONT)
    _span(ws2, 3, 1, 7, counts, fill=fill, font=font,
          align=Alignment(horizontal="center", vertical="center"))
    ws2.row_dimensions[3].height = 24
    ws2.row_dimensions[4].height = 8

    headers2 = ["Файл", "Стр.", "Колонка", "Уровень", "Правило", "Что не так", "Что делать"]
    for col, title in enumerate(headers2, 1):
        _write(ws2, 5, col, title, fill=HEADER_FILL, font=HEADER_FONT, border=THIN,
               align=Alignment(horizontal="center", vertical="center"))
    ws2.row_dimensions[5].height = 22

    ordered = sorted(issues, key=lambda i: (i.file, i.row, i.level != ERROR))
    row = 6
    if not ordered:
        _span(ws2, row, 1, 7, "Замечаний нет: все записи прошли проверку",
              fill=GOOD_FILL, font=GOOD_FONT, border=THIN,
              align=Alignment(horizontal="left", vertical="center"))
        ws2.row_dimensions[row].height = 20
        row += 1
    else:
        first_data = row
        for index, issue in enumerate(ordered):
            is_error = issue.level == ERROR
            is_info = issue.level == INFO
            zebra = ZEBRA_FILL if index % 2 else None
            _write(ws2, row, 1, issue.file, fill=zebra, border=THIN)
            _write(ws2, row, 2, issue.row if issue.row else "—", fill=zebra, border=THIN,
                   align=Alignment(horizontal="center", vertical="center"))
            _write(ws2, row, 3, issue.column or "—", fill=zebra, border=THIN,
                   align=Alignment(horizontal="center", vertical="center"))
            if is_error:
                level_text, level_fill, level_font = "ошибка", BAD_FILL, BAD_FONT
            elif is_info:
                level_text, level_fill, level_font = "информация", INFO_FILL, INFO_FONT
            else:
                level_text, level_fill, level_font = "предупреждение", WARN_FILL, WARN_FONT
            _write(ws2, row, 4, level_text, fill=level_fill, font=level_font, border=THIN,
                   align=Alignment(horizontal="center", vertical="center", wrap_text=True))
            _write(ws2, row, 5, RULE_LABEL.get(issue.rule, issue.rule),
                   fill=zebra, border=THIN)
            _write(ws2, row, 6, issue.message, fill=zebra, border=THIN)
            _write(ws2, row, 7, issue.hint or "", fill=zebra, border=THIN)
            row += 1
        _fit_rows(ws2, first_data, row - 1, ISSUES_WIDTHS)

    ws2.freeze_panes = "A6"
    ws2.auto_filter.ref = f"A5:G{max(row - 1, 6)}"
    _setup_print(ws2, title_rows="5:5")

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

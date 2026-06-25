"""ReportService — генерация детализированных Excel отчетов с тремя источниками."""

import json
import os
import re
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.check_result_repository import CheckResultRepository
from app.repositories.check_run_repository import CheckRunRepository
from app.repositories.protocol_data_repository import ProtocolDataRepository


class ReportService:
    """Service for generating comprehensive Excel reports with three data sources."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cal_repo = CalibrationRepository(db)
        self.result_repo = CheckResultRepository(db)
        self.run_repo = CheckRunRepository(db)
        self.proto_repo = ProtocolDataRepository(db)

    @staticmethod
    def _combine_name_type(name: str, type_: str) -> str:
        if not type_:
            return name or ""
        if not name:
            return type_
        if type_.startswith(name):
            return type_
        return f"{name} {type_}"

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison: lowercase, remove extra spaces."""
        if not text:
            return ""
        text = text.lower().strip()
        text = text.rstrip(".,;:")
        return text

    @staticmethod
    def _extract_range_from_text(text: str) -> str:
        """Extract measurement range from protocol text."""
        if not text:
            return ""
        # Pattern: find "Диапазон измерений" then "от X до Y" within 300 chars
        # Handles multi-line PDF layout (e.g., "Диапазон измерений в рабочих\n3\nот 4 до 400 м³/ч\nусловиях:")
        match = re.search(
            r'Диапазон\s+измерений.{0,300}?от\s+([\d.,]+)\s+до\s+([\d.,]+)\s+([^\n]{1,30})',
            text, re.IGNORECASE | re.DOTALL
        )
        if match:
            return f"({match.group(1)}-{match.group(2)}) {match.group(3).strip()}"
        # Fallback: standalone "от X до Y"
        match = re.search(
            r'от\s+([\d.,]+)\s+до\s+([\d.,]+)\s+([^\n]{1,30})',
            text, re.IGNORECASE
        )
        if match:
            return f"({match.group(1)}-{match.group(2)}) {match.group(3).strip()}"
        return ""

    async def generate_interim_report(self, year: int, month: int, output_dir: str = "/reports", job_id: int | None = None) -> dict[str, Any]:
        """Generate interim Excel report with full comparison layout."""
        calibrations = await self.cal_repo.get_by_month(year, month)
        protocols = await self.proto_repo.get_by_month(year, month)

        wb = Workbook()
        ws_summary = wb.active
        ws_summary.title = "0. Сводка"
        self._fill_summary_sheet(ws_summary, calibrations, protocols, year, month)

        ws_public = wb.create_sheet("1. ARSHIN Public API")
        self._fill_public_sheet(ws_public, calibrations)

        ws_lk = wb.create_sheet("2. ARSHIN LK")
        self._fill_lk_sheet(ws_lk, calibrations)

        ws_proto = wb.create_sheet("3. Протоколы")
        self._fill_protocol_sheet(ws_proto, protocols)

        ws_compare = wb.create_sheet("4. Сравнение")
        self._fill_comparison_sheet(ws_compare, calibrations, protocols)

        os.makedirs(output_dir, exist_ok=True)
        job_suffix = f"_job{job_id}" if job_id else ""
        filename = f"report_{year}_{month:02d}{job_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = os.path.join(output_dir, filename)
        wb.save(file_path)

        return {
            "file_path": file_path,
            "filename": filename,
            "year": year,
            "month": month,
            "total_calibrations": len(calibrations),
            "total_protocols": len(protocols),
            "is_interim": True,
        }

    def _fill_summary_sheet(
        self,
        ws,
        calibrations: list,
        protocols: list,
        year: int,
        month: int,
    ) -> None:
        """Fill summary sheet with overall stats, per-owner breakdown, performed checks and protocol uniqueness."""
        from collections import defaultdict
        from openpyxl.utils import get_column_letter

        def norm_owner(val: str | None) -> str:
            if not val:
                return "Владелец не определён"
            return str(val).strip()

        def fmt_num(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return str(val)

        def _dates_within(a: date | None, b: date | None, days: int = 1) -> bool:
            if not a or not b:
                return False
            return abs((a - b).days) <= days

        # Build calibrations lookup by serial number
        cal_by_serial: dict[str, list] = defaultdict(list)
        for c in calibrations:
            if c.mi_number:
                cal_by_serial[c.mi_number.strip()].append(c)

        # Match protocols to calibrations
        matched_serials: set[str] = set()
        matched_protocols: list = []
        extra_protocols: list = []
        for proto in protocols:
            serial = (proto.serial_number or "").strip()
            cal_list = cal_by_serial.get(serial, [])
            if cal_list:
                matched_serials.add(serial)
                matched_protocols.append((proto, cal_list))
            else:
                extra_protocols.append(proto)

        missing_cals = [c for c in calibrations if c.mi_number and c.mi_number.strip() not in matched_serials]

        # Errors/warnings per matched pair
        error_count = 0
        warning_count = 0
        per_owner: dict[str, dict[str, int]] = defaultdict(lambda: {
            "protocols": 0, "matched": 0, "missing": 0, "extra": 0,
            "errors": 0, "warnings": 0,
        })

        for proto, cal_list in matched_protocols:
            owner = norm_owner(proto.owner)
            per_owner[owner]["protocols"] += 1
            per_owner[owner]["matched"] += 1

            # Determine date status
            date_status = "no_arshin"
            best_cal = None
            if proto.verification_date:
                proto_date = proto.verification_date
                green = [c for c in cal_list if _dates_within(c.verification_date, proto_date)]
                if green:
                    date_status = "green"
                    best_cal = green[0]
                else:
                    yellow = [c for c in cal_list if _dates_within(c.valid_date, proto_date)]
                    if yellow:
                        date_status = "yellow"
                        best_cal = yellow[0]
                    else:
                        date_status = "red"
                        best_cal = max(
                            [c for c in cal_list if c.verification_date],
                            key=lambda c: c.verification_date,
                            default=cal_list[0],
                        )
            else:
                date_status = "green"
                best_cal = cal_list[0]

            cal = best_cal
            pair_errors = 0
            pair_warnings = 0

            if date_status == "red":
                pair_errors += 1
            elif date_status == "yellow":
                pair_warnings += 1

            # Verifier check (only if both sides have data)
            if cal and cal.verifier and proto.verifier:
                norm_proto = re.sub(r"([А-ЯA-Z])\.\s+([А-ЯA-Z])\.", r"\1.\2.", proto.verifier)
                norm_cal = re.sub(r"([А-ЯA-Z])\.\s+([А-ЯA-Z])\.", r"\1.\2.", cal.verifier)
                if norm_proto != norm_cal:
                    pair_errors += 1

            # Conditions check
            lk_conditions = {}
            if cal and cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            for field, threshold in (("temperature", 2.0), ("humidity", 10.0), ("pressure", 3.0)):
                proto_val = getattr(proto, field, None)
                cal_val = lk_conditions.get(field)
                if proto_val is not None and cal_val is not None:
                    try:
                        if abs(float(proto_val) - float(cal_val)) > threshold:
                            pair_errors += 1
                    except (ValueError, TypeError):
                        pass

            if pair_errors:
                error_count += pair_errors
                per_owner[owner]["errors"] += pair_errors
            if pair_warnings:
                warning_count += pair_warnings
                per_owner[owner]["warnings"] += pair_warnings

        # Extra protocols attribution
        for proto in extra_protocols:
            owner = norm_owner(proto.owner)
            per_owner[owner]["protocols"] += 1
            per_owner[owner]["extra"] += 1

        # Missing protocols attribution: we don't know owner, put into 'Владелец не определён'
        for _cal in missing_cals:
            per_owner["Владелец не определён"]["missing"] += 1

        # Protocol number uniqueness
        proto_by_number: dict[str, list] = defaultdict(list)
        for proto in protocols:
            num = (proto.protocol_number or "").strip()
            if num:
                proto_by_number[num].append(proto)
        duplicate_numbers = {num: items for num, items in proto_by_number.items() if len(items) > 1}

        # --- Styling helpers ---
        header_fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        section_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        section_font = Font(bold=True, color="FFFFFF", size=12)
        good_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        good_font = Font(color="006100", bold=True)
        warn_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        warn_font = Font(color="9C5700", bold=True)
        bad_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        bad_font = Font(color="9C0006", bold=True)
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        def write_cell(r: int, c: int, value, *, fill=None, font=None, alignment=None):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = thin_border
            if fill:
                cell.fill = fill
            if font:
                cell.font = font
            if alignment:
                cell.alignment = alignment
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            return cell

        def set_section_title(r: int, text: str, colspan: int = 8):
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=colspan)
            write_cell(r, 1, text, fill=section_fill, font=section_font,
                       alignment=Alignment(horizontal="left", vertical="center"))
            ws.row_dimensions[r].height = 24

        def write_colored_value(r: int, c: int, value, kind: str):
            if kind == "bad":
                write_cell(r, c, value, fill=bad_fill, font=bad_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            elif kind == "warn":
                write_cell(r, c, value, fill=warn_fill, font=warn_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            elif kind == "good":
                write_cell(r, c, value, fill=good_fill, font=good_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            else:
                write_cell(r, c, value, alignment=Alignment(horizontal="center", vertical="center"))

        row = 1

        # Title
        set_section_title(row, f"Сводка проверки протоколов за {month:02d}.{year}", colspan=8)
        row += 2

        # Section 1: General summary
        set_section_title(row, "1. Общая сводка")
        row += 1

        summary_items = [
            ("Всего поверок в АРШИН", len(calibrations), "plain"),
            ("Всего протоколов в папке", len(protocols), "plain"),
            ("Сопоставлено (совпадает серийник)", len(matched_protocols), "good"),
            ("Отсутствуют протоколы (есть в АРШИН, нет файла)", len(missing_cals), "bad"),
            ("Лишние протоколы (есть файл, нет в АРШИН)", len(extra_protocols), "warn"),
            ("Ошибки сопоставления", error_count, "bad"),
            ("Предупреждения", warning_count, "warn"),
            ("Дублирующихся номеров протоколов", len(duplicate_numbers), "bad"),
        ]
        for label, value, kind in summary_items:
            write_cell(row, 1, label)
            write_colored_value(row, 2, value, kind if value else "plain")
            row += 1
        row += 1

        # Section 2: Per owner breakdown
        set_section_title(row, "2. Разбивка по Заказчикам (владельцам)")
        row += 1

        owner_headers = [
            "Заказчик", "Протоколов", "Сопоставлено",
            "Отсутствует", "Лишние", "Ошибки", "Предупреждения", "Статус",
        ]
        for col_idx, h in enumerate(owner_headers, 1):
            write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                       alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 22
        row += 1

        # Sort owners: real owners first, undefined last
        sorted_owners = sorted(
            per_owner.items(),
            key=lambda x: (x[0] == "Владелец не определён", x[0]),
        )
        for owner, stats in sorted_owners:
            write_cell(row, 1, owner)
            write_cell(row, 2, stats["protocols"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 3, stats["matched"], alignment=Alignment(horizontal="center", vertical="center"))
            write_colored_value(row, 4, stats["missing"], "bad" if stats["missing"] else "plain")
            write_colored_value(row, 5, stats["extra"], "warn" if stats["extra"] else "plain")
            write_colored_value(row, 6, stats["errors"], "bad" if stats["errors"] else "plain")
            write_colored_value(row, 7, stats["warnings"], "warn" if stats["warnings"] else "plain")
            if stats["errors"] or stats["missing"]:
                status = "Требует внимания"
                status_kind = "bad"
            elif stats["warnings"] or stats["extra"]:
                status = "Есть замечания"
                status_kind = "warn"
            else:
                status = "OK"
                status_kind = "good"
            write_colored_value(row, 8, status, status_kind)
            row += 1
        row += 1

        # Section 3: Performed checks
        set_section_title(row, "3. Выполненные проверки")
        row += 1

        check_headers = ["№", "Проверка", "Описание", "Статус"]
        for col_idx, h in enumerate(check_headers, 1):
            write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                       alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 22
        row += 1

        performed_checks = [
            ("Наличие протокола", "Для каждой поверки из АРШИН ищется файл протокола по заводскому номеру."),
            ("Сопоставление с АРШИН", "Для каждого файла протокола проверяется наличие записи в АРШИН по серийному номеру."),
            ("Дата поверки", "Сравнивается дата поверки в протоколе с датой поверки/действия до в АРШИН (±1 день)."),
            ("ФИО поверителя", "Сравнивается ФИО поверителя в АРШИН (ЛК) и в протоколе."),
            ("Условия окружающей среды", "Сравниваются температура (±2°C), влажность (±10%) и давление (±3 кПа) в АРШИН (ЛК) и в протоколе."),
            ("Уникальность номера протокола", "Проверяется отсутствие дублей номеров протоколов среди загруженных файлов."),
        ]
        for idx, (check_name, check_desc) in enumerate(performed_checks, 1):
            write_cell(row, 1, idx, alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 2, check_name)
            write_cell(row, 3, check_desc)
            if check_name == "Уникальность номера протокола" and duplicate_numbers:
                write_colored_value(row, 4, "Найдены дубли", "bad")
            else:
                write_colored_value(row, 4, "Выполнена", "good")
            row += 1
        row += 1

        # Section 3a: Errors/warnings legend
        set_section_title(row, "3a. Расшифровка ошибок и предупреждений")
        row += 1

        legend_headers = ["Тип", "Что фиксируется"]
        for col_idx, h in enumerate(legend_headers, 1):
            write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                       alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 22
        row += 1

        legend_items = [
            (
                "Ошибка",
                "Критичное расхождение: дата поверки не совпадает ни с датой поверки, ни с датой действия до; ФИО поверителя различается; условия окружающей среды (t, φ, P) расходятся более чем на допустимый порог.",
            ),
            (
                "Предупреждение",
                "Некритичное замечание: дата в протоколе совпадает с датой действия до в АРШИН, но не с датой поверки (возможная путаница дат).",
            ),
            (
                "Отсутствует протокол",
                "Есть запись в АРШИН, но не найден файл протокола по серийному номеру.",
            ),
            (
                "Лишний протокол",
                "Есть файл протокола, но нет соответствующей записи в АРШИН по серийному номеру.",
            ),
        ]
        for label, desc in legend_items:
            write_cell(row, 1, label)
            write_cell(row, 2, desc)
            row += 1
        row += 1

        # Section 4: Protocol number uniqueness details
        set_section_title(row, "4. Дубли номеров протоколов")
        row += 1

        if duplicate_numbers:
            dup_headers = ["Номер протокола", "Количество файлов", "Список файлов"]
            for col_idx, h in enumerate(dup_headers, 1):
                write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            ws.row_dimensions[row].height = 22
            row += 1
            for num, items in sorted(duplicate_numbers.items()):
                write_cell(row, 1, num)
                write_cell(row, 2, len(items), alignment=Alignment(horizontal="center", vertical="center"))
                file_list = ", ".join(
                    f"{p.protocol_file.relative_path if p.protocol_file else '—'}"
                    for p in items
                )
                write_cell(row, 3, file_list)
                row += 1
        else:
            write_cell(row, 1, "Дубли не найдены", fill=good_fill, font=good_font)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            row += 1

        # Auto-fit columns (remove wrap_text so words don't break)
        self._auto_fit_columns(ws)
        # Disable wrap text on all cells in summary sheet
        for row_cells in ws.iter_rows():
            for cell in row_cells:
                cell.alignment = Alignment(
                    horizontal=cell.alignment.horizontal or "left",
                    vertical=cell.alignment.vertical or "center",
                    wrap_text=False,
                )

    def _fill_public_sheet(self, ws, calibrations) -> None:
        headers = ["№", "VRI ID", "№ОТ", "Наименование", "Обозначение", "Мод.", "Зав№",
                   "Дата", "Действует до", "№ док-та", "Результат"]
        self._write_headers(ws, headers, "4472C4")

        for idx, cal in enumerate(calibrations, 1):
            if cal.result:
                result_text = cal.result
            elif cal.applicability is True:
                result_text = "пригоден"
            elif cal.applicability is False:
                result_text = "непригоден"
            else:
                result_text = ""
            row = [idx, cal.vri_id, cal.mit_number, cal.mit_title, cal.mit_notation,
                   cal.mi_modification, cal.mi_number,
                   cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                   cal.valid_date.strftime("%d.%m.%Y") if cal.valid_date else "",
                   cal.result_docnum, result_text]
            self._write_data_row(ws, row, idx, "DDEBF7")
        self._auto_fit_columns(ws)

    def _fill_lk_sheet(self, ws, calibrations) -> None:
        headers = ["№", "VRI ID", "Поверитель", "t, °C", "φ, %", "P, кПа"]
        self._write_headers(ws, headers, "70AD47")
        for idx, cal in enumerate(calibrations, 1):
            conditions = {}
            if cal.conditions:
                try:
                    conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass
            has_lk = bool(cal.verifier or cal.conditions)
            row = [idx, cal.vri_id,
                   cal.verifier or ("Н/Д" if not has_lk else ""),
                   conditions.get("temperature", ""),
                   conditions.get("humidity", ""),
                   conditions.get("pressure", "")]
            self._write_data_row(ws, row, idx, "E2EFDA")
        self._auto_fit_columns(ws)

    def _fill_protocol_sheet(self, ws, protocols) -> None:
        headers = ["№", "№ протокола", "Наименование", "Зав№",
                   "№ОТ", "Методика", "Год", "Владелец", "Дата",
                   "Поверитель", "t, °C", "φ, %", "P, кПа"]
        self._write_headers(ws, headers, "ED7D31")

        def fmt_num(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return str(val)

        for idx, proto in enumerate(protocols, 1):
            full_name = self._combine_name_type(proto.device_name, proto.device_type)
            row = [idx, proto.protocol_number or "", full_name,
                   proto.serial_number or "",
                   proto.mit_number or "", proto.verification_method or "",
                   proto.manufacture_year or "", proto.owner or "",
                   proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else "",
                   proto.verifier or "", fmt_num(proto.temperature),
                   fmt_num(proto.humidity), fmt_num(proto.pressure)]
            self._write_data_row(ws, row, idx, "FCE4D6")
        self._auto_fit_columns(ws)

    def _fill_comparison_sheet(self, ws, calibrations, protocols) -> None:
        # Build calibrations lookup by serial number (multiple records possible)
        cal_by_serial: dict[str, list] = {}
        for c in calibrations:
            if c.mi_number:
                serial = c.mi_number.strip()
                cal_by_serial.setdefault(serial, []).append(c)

        # Build set of protocol serials that have a match
        matched_cal_serials: set[str] = set()

        compare_headers = ["Статус", "Расхождения"]
        public_headers = ["№", "VRI ID", "№ОТ", "Наименование", "Обозначение", "Мод.", "Зав№",
                          "Дата", "Действует до", "№ док-та"]
        lk_headers = ["Поверитель", "t", "φ", "P"]
        proto_headers = ["№ протокола", "Наименование", "Зав№",
                         "№ОТ", "Методика", "Год", "Владелец", "Дата",
                         "Поверитель", "t", "φ", "P"]
        all_headers = compare_headers + public_headers + lk_headers + proto_headers

        group_titles = [
            ("Сравнение", "5B9BD5", len(compare_headers)),
            ("Публичный АРШИН", "4472C4", len(public_headers)),
            ("ЛК АРШИН", "70AD47", len(lk_headers)),
            ("Протокол", "ED7D31", len(proto_headers)),
        ]

        from openpyxl.utils import get_column_letter

        col_start = 1
        for title, color, span in group_titles:
            col_end = col_start + span - 1
            if span > 1:
                ws.merge_cells(start_row=1, start_column=col_start, end_row=1, end_column=col_end)
            cell = ws.cell(row=1, column=col_start, value=title)
            cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                               top=Side(style='thin'), bottom=Side(style='thin'))
            col_start = col_end + 1
        ws.row_dimensions[1].height = 25

        compare_offset = 0
        public_offset = len(compare_headers)
        lk_offset = public_offset + len(public_headers)
        proto_offset = lk_offset + len(lk_headers)

        header_fills = {
            "5B9BD5": list(range(compare_offset, public_offset)),
            "4472C4": list(range(public_offset, lk_offset)),
            "70AD47": list(range(lk_offset, proto_offset)),
            "ED7D31": list(range(proto_offset, proto_offset + len(proto_headers))),
        }

        for col_idx, header in enumerate(all_headers, 1):
            cell = ws.cell(row=2, column=col_idx, value=header)
            cell.font = Font(bold=True, color="FFFFFF", size=9)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                               top=Side(style='thin'), bottom=Side(style='thin'))
            for color, cols in header_fills.items():
                if col_idx - 1 in cols:
                    cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
                    break
        ws.row_dimensions[2].height = 30
        last_col = get_column_letter(len(all_headers))
        ws.auto_filter.ref = f"A2:{last_col}2"

        STATUS_COL = 1
        COMMENTS_COL = 2

        def fmt_num(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return str(val)

        def _dates_within(a: date | None, b: date | None, days: int = 1) -> bool:
            if not a or not b:
                return False
            return abs((a - b).days) <= days

        row_num = 3  # Start data after header rows (row 1 = groups, row 2 = column names)
        display_num = 1

        # FIRST PASS: iterate by protocols (all files in folder order), find matching calibration(s)
        for proto in protocols:
            serial = (proto.serial_number or "").strip()
            cal_list = cal_by_serial.get(serial, [])
            if cal_list:
                matched_cal_serials.add(serial)

            # Determine date status against ALL calibrations for this serial
            date_status = "no_arshin"  # green / yellow / red / no_arshin
            best_cal = None
            if cal_list and proto.verification_date:
                proto_date = proto.verification_date
                # Check green: matches any verification_date
                green_cals = [c for c in cal_list if _dates_within(c.verification_date, proto_date)]
                if green_cals:
                    date_status = "green"
                    best_cal = green_cals[0]
                else:
                    # Check yellow: matches any valid_date
                    yellow_cals = [c for c in cal_list if _dates_within(c.valid_date, proto_date)]
                    if yellow_cals:
                        date_status = "yellow"
                        best_cal = yellow_cals[0]
                    else:
                        date_status = "red"
                        # Pick latest verification_date for display
                        best_cal = max(
                            [c for c in cal_list if c.verification_date],
                            key=lambda c: c.verification_date,
                            default=cal_list[0],
                        )
            elif cal_list:
                date_status = "green"
                best_cal = cal_list[0]
            else:
                date_status = "no_arshin"

            cal = best_cal
            lk_conditions = {}
            if cal and cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            full_name = self._combine_name_type(proto.device_name, proto.device_type)

            row_data = [
                # compare columns (status + comments) filled later
                "",
                "",
                # public headers
                display_num,
                cal.vri_id if cal else "",
                cal.mit_number if cal else "",
                cal.mit_title if cal else "",
                cal.mit_notation if cal else "",
                cal.mi_modification if cal else "",
                cal.mi_number if cal else "",
                cal.verification_date.strftime("%d.%m.%Y") if cal and cal.verification_date else "",
                cal.valid_date.strftime("%d.%m.%Y") if cal and cal.valid_date else "",
                cal.result_docnum if cal else "",
                # lk headers
                cal.verifier or "" if cal else "",
                fmt_num(lk_conditions.get("temperature")) if cal else "",
                fmt_num(lk_conditions.get("humidity")) if cal else "",
                fmt_num(lk_conditions.get("pressure")) if cal else "",
                # proto headers
                proto.protocol_number or "",
                full_name,
                proto.serial_number or "",
                proto.mit_number or "",
                (proto.verification_method if proto.verification_method else "—"),
                proto.manufacture_year or "",
                proto.owner or "",
                proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else "",
                proto.verifier or "",
                fmt_num(proto.temperature),
                fmt_num(proto.humidity),
                fmt_num(proto.pressure),
            ]

            mismatches = []

            if not cal_list:
                mismatches.append("НЕТ В АРШИН")
            else:
                if len(cal_list) > 1:
                    mismatches.append(f"Записей в АРШИН: {len(cal_list)}")

                if date_status == "yellow":
                    proto_date_str = proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else ""
                    valid_strs = [c.valid_date.strftime("%d.%m.%Y") for c in cal_list if c.valid_date]
                    mismatches.append(f"Дата протокола ({proto_date_str}) = действует до в АРШИН ({', '.join(valid_strs)})")
                elif date_status == "red":
                    proto_date_str = proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else ""
                    verif_strs = [c.verification_date.strftime("%d.%m.%Y") for c in cal_list if c.verification_date]
                    mismatches.append(f"Дата: АРШИН {', '.join(verif_strs)} vs протокол {proto_date_str}")

                # Check verifier against best_cal
                if cal and proto.verifier and cal.verifier:
                    norm_proto_verifier = re.sub(r'([А-ЯA-Z])\.\s+([А-ЯA-Z])\.', r'\1.\2.', proto.verifier)
                    norm_cal_verifier = re.sub(r'([А-ЯA-Z])\.\s+([А-ЯA-Z])\.', r'\1.\2.', cal.verifier)
                    if norm_proto_verifier != norm_cal_verifier:
                        mismatches.append(f"Поверитель: {cal.verifier} vs {proto.verifier}")

                if proto.serial_number and serial:
                    if proto.serial_number.strip() != serial:
                        mismatches.append(f"Серийник: {serial} vs {proto.serial_number}")

            # Status symbol and color
            if date_status == "green" and not mismatches:
                status = "✓"
                status_color = "C6EFCE"
                status_font_color = "006100"
            elif date_status == "green" and mismatches or date_status == "yellow":
                status = "⚠"
                status_color = "FFEB9C"
                status_font_color = "9C5700"
            else:
                status = "❌"
                status_color = "FFC7CE"
                status_font_color = "9C0006"

            row_data[STATUS_COL - 1] = status
            comments = "; ".join(mismatches) if mismatches else ""
            row_data[COMMENTS_COL - 1] = comments

            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=value)
                cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                   top=Side(style='thin'), bottom=Side(style='thin'))
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                if col_idx == STATUS_COL:
                    cell.fill = PatternFill(start_color=status_color, end_color=status_color, fill_type="solid")
                    cell.font = Font(bold=True, color=status_font_color, size=12)
                elif col_idx == COMMENTS_COL and mismatches:
                    if date_status == "yellow":
                        cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
                        cell.font = Font(color="9C5700", size=9)
                    else:
                        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                        cell.font = Font(color="9C0006", size=9)
            row_num += 1
            display_num += 1

        # SECOND PASS: ARSHIN entries without a matching protocol
        for cal in calibrations:
            cal_serial = (cal.mi_number or "").strip()
            if cal_serial and cal_serial not in matched_cal_serials:
                lk_conditions = {}
                if cal.conditions:
                    try:
                        lk_conditions = json.loads(cal.conditions)
                    except json.JSONDecodeError:
                        pass
                row_data = [
                    "❌",
                    "НЕТ ПРОТОКОЛА",
                    display_num,
                    cal.vri_id or "",
                    cal.mit_number or "",
                    cal.mit_title or "",
                    cal.mit_notation or "",
                    cal.mi_modification or "",
                    cal_serial,
                    cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                    cal.valid_date.strftime("%d.%m.%Y") if cal.valid_date else "",
                    cal.result_docnum or "",
                    cal.verifier or "",
                    fmt_num(lk_conditions.get("temperature")),
                    fmt_num(lk_conditions.get("humidity")),
                    fmt_num(lk_conditions.get("pressure")),
                    # proto columns — empty
                    "", "", "", "", "", "", "", "", "", "", "",
                ]
                for col_idx, value in enumerate(row_data, 1):
                    cell = ws.cell(row=row_num, column=col_idx, value=value)
                    cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                       top=Side(style='thin'), bottom=Side(style='thin'))
                    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                    if col_idx == STATUS_COL:
                        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                        cell.font = Font(bold=True, color="9C0006", size=12)
                    elif col_idx == COMMENTS_COL:
                        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                        cell.font = Font(color="9C0006", size=9)
                row_num += 1
                display_num += 1

        self._auto_fit_columns(ws)

    def _write_headers(self, ws, headers, color) -> None:
        fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        font = Font(bold=True, color="FFFFFF", size=10)
        border = Border(left=Side(style='thin'), right=Side(style='thin'),
                       top=Side(style='thin'), bottom=Side(style='thin'))
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = border
        ws.row_dimensions[1].height = 25
        from openpyxl.utils import get_column_letter
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A1:{last_col}1"

    def _write_data_row(self, ws, row_data, row_idx, color) -> None:
        fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'),
                       top=Side(style='thin'), bottom=Side(style='thin'))
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx + 1, column=col_idx, value=value)
            cell.fill = fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def _set_column_widths(self, ws, widths) -> None:
        from openpyxl.utils import get_column_letter
        for idx, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(idx)].width = width

    def _auto_fit_columns(self, ws) -> None:
        from openpyxl.utils import get_column_letter
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

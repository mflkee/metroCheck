"""ReportService — генерация детализированных Excel отчетов с тремя источниками."""

import json
import os
import re
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
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
    def _normalize_serial(serial: str) -> str:
        """Normalize serial number for comparison (handle homoglyphs, garbage)."""
        if not serial:
            return ""
        replacements = {
            "А": "A", "В": "B", "С": "C", "Е": "E",
            "Н": "H", "К": "K", "М": "M", "О": "O",
            "Р": "P", "Т": "T", "Х": "X",
            "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
        }
        normalized = serial
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        normalized = re.sub(r'[^A-Za-z0-9]', '', normalized)
        normalized = normalized.lstrip('0')
        return normalized.upper().strip()

    @staticmethod
    def _extract_range_from_text(text: str) -> str:
        """Extract measurement range from protocol text."""
        if not text:
            return ""
        match = re.search(
            r'Диапазон\s+измерений.{0,300}?от\s+([\d.,]+)\s+до\s+([\d.,]+)\s+([^\n]{1,30})',
            text, re.IGNORECASE | re.DOTALL
        )
        if match:
            return f"({match.group(1)}-{match.group(2)}) {match.group(3).strip()}"
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
        """Fill summary dashboard sheet with KPIs, charts, per-owner breakdown, performed checks and duplicates."""
        from collections import defaultdict

        def norm_owner(val: str | None) -> str:
            if not val:
                return "Владелец не определён"
            owner = str(val).strip()
            # Strip INN/KPP and trailing digits/spaces
            import re as _re
            owner = _re.split(r"\s*[Ии][Нн][Нн]\s*/?\s*[Кк][Пп][Пп]?", owner)[0].strip()
            owner = _re.split(r"\s*[Ии][Нн][Нн]", owner)[0].strip()
            owner = _re.sub(r"\s+\d[\d\s]*$", "", owner).strip()
            return owner or "Владелец не определён"

        def _dates_within(a: date | None, b: date | None, days: int = 1) -> bool:
            if not a or not b:
                return False
            return abs((a - b).days) <= days

        def write_cell(r: int, c: int, value, *, fill=None, font=None, alignment=None, border=True):
            cell = ws.cell(row=r, column=c, value=value)
            if border:
                cell.border = thin_border
            if fill:
                cell.fill = fill
            if font:
                cell.font = font
            cell.alignment = alignment or Alignment(horizontal="left", vertical="center", wrap_text=False)
            return cell

        def set_col_widths(widths: dict[int, int]):
            for col, width in widths.items():
                ws.column_dimensions[get_column_letter(col)].width = width

        # Colors
        header_fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        section_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        section_font = Font(bold=True, color="FFFFFF", size=12)
        good_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        good_font = Font(color="006100", bold=True)
        warn_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        warn_font = Font(color="9C5700", bold=True)
        bad_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        bad_font = Font(color="9C0006", bold=True)
        kpi_label_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        kpi_label_font = Font(color="305496", bold=True, size=9)
        kpi_value_font = Font(color="305496", bold=True, size=16)
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        # Build calibrations lookup by (serial, mit_number) pair (original + normalized serial)
        cal_by_pair: dict[tuple[str, str], list] = defaultdict(list)
        cal_by_serial: dict[str, list] = defaultdict(list)
        cal_by_norm_serial: dict[str, list] = defaultdict(list)
        for c in calibrations:
            if c.mi_number:
                serial = c.mi_number.strip()
                mit = (c.mit_number or "").strip()
                cal_by_serial[serial].append(c)
                norm = self._normalize_serial(serial)
                if norm:
                    cal_by_norm_serial[norm].append(c)
                    if mit:
                        cal_by_pair[(norm, mit)].append(c)

        def _find_cal_list(proto) -> list:
            """Find matching calibrations for a protocol by serial+mit_number, falling back to serial only."""
            serial = (proto.serial_number or "").strip()
            mit = (proto.mit_number or "").strip()
            norm_serial = self._normalize_serial(serial)
            if norm_serial and mit:
                pair_list = cal_by_pair.get((norm_serial, mit), [])
                if pair_list:
                    return pair_list
            # Fallback to serial-only match
            cal_list = cal_by_serial.get(serial, [])
            if not cal_list and norm_serial:
                cal_list = cal_by_norm_serial.get(norm_serial, [])
            return cal_list

        # Match protocols to calibrations
        matched_serials: set[str] = set()
        matched_protocols: list = []
        extra_protocols: list = []
        serial_mismatch_count = 0
        for proto in protocols:
            serial = (proto.serial_number or "").strip()
            norm_serial = self._normalize_serial(serial)
            cal_list = _find_cal_list(proto)
            if cal_list:
                matched_serials.add(serial)
                matched_protocols.append((proto, cal_list))
            else:
                extra_protocols.append(proto)

            # Check serial from filename vs protocol
            file_name_serial = ""
            if proto.protocol_file and proto.protocol_file.file_name:
                file_name_serial = self._extract_serial_from_filename(proto.protocol_file.file_name)
            if file_name_serial and serial and self._normalize_serial(file_name_serial) != norm_serial:
                serial_mismatch_count += 1

        missing_cals = []
        for c in calibrations:
            if not c.mi_number:
                continue
            cal_serial = c.mi_number.strip()
            cal_norm = self._normalize_serial(cal_serial)
            cal_mit = (c.mit_number or "").strip()
            # A calibration is missing if no protocol matched it by pair or by serial
            pair_matched = bool(cal_mit) and any(
                self._normalize_serial((p.serial_number or "").strip()) == cal_norm
                and (p.mit_number or "").strip() == cal_mit
                for p in protocols
            )
            serial_matched = any(
                (p.serial_number or "").strip() == cal_serial
                or self._normalize_serial((p.serial_number or "").strip()) == cal_norm
                for p in protocols
            )
            if not pair_matched and not serial_matched:
                missing_cals.append(c)

        # Errors/warnings per matched pair
        error_count = 0
        warning_count = 0
        per_owner: dict[str, dict[str, int]] = defaultdict(lambda: {
            "protocols": 0, "matched": 0, "missing": 0, "extra": 0,
            "errors": 0, "warnings": 0,
        })

        for proto, cal_list in matched_protocols:
            owner = norm_owner(proto.owner)
            serial = (proto.serial_number or "").strip()
            per_owner[owner]["protocols"] += 1
            per_owner[owner]["matched"] += 1

            date_status = "no_arshin"
            best_cal = None
            if proto.verification_date:
                proto_date = proto.verification_date
                # Exact match required
                exact = [c for c in cal_list if c.verification_date == proto_date]
                if exact:
                    date_status = "green"
                    best_cal = exact[0]
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

            if cal and cal.verifier and proto.verifier:
                norm_proto = re.sub(r"([А-ЯA-Z])\.\s+([А-ЯA-Z])\.", r"\1.\2.", proto.verifier)
                norm_cal = re.sub(r"([А-ЯA-Z])\.\s+([А-ЯA-Z])\.", r"\1.\2.", cal.verifier)
                if norm_proto != norm_cal:
                    pair_errors += 1

            lk_conditions = {}
            if cal and cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            # Exact match for conditions
            for field in ("temperature", "humidity", "pressure"):
                proto_val = getattr(proto, field, None)
                cal_val = lk_conditions.get(field)
                if proto_val is not None and cal_val is not None:
                    try:
                        if float(proto_val) != float(cal_val):
                            pair_errors += 1
                    except (ValueError, TypeError):
                        pass

            # Check serial from filename vs protocol
            file_name_serial = ""
            if proto.protocol_file and proto.protocol_file.file_name:
                file_name_serial = self._extract_serial_from_filename(proto.protocol_file.file_name)
            if file_name_serial and serial and self._normalize_serial(file_name_serial) != self._normalize_serial(serial):
                pair_warnings += 1

            if pair_errors:
                error_count += pair_errors
                per_owner[owner]["errors"] += pair_errors
            if pair_warnings:
                warning_count += pair_warnings
                per_owner[owner]["warnings"] += pair_warnings

        for proto in extra_protocols:
            owner = norm_owner(proto.owner)
            per_owner[owner]["protocols"] += 1
            per_owner[owner]["extra"] += 1

        for _cal in missing_cals:
            per_owner["Владелец не определён"]["missing"] += 1

        # Protocol number uniqueness
        proto_by_number: dict[str, list] = defaultdict(list)
        for proto in protocols:
            num = (proto.protocol_number or "").strip()
            if num:
                proto_by_number[num].append(proto)
        duplicate_numbers = {num: items for num, items in proto_by_number.items() if len(items) > 1}

        # Determine owner statuses
        sorted_owners = sorted(
            per_owner.items(),
            key=lambda x: (x[0] == "Владелец не определён", x[0]),
        )
        owner_statuses = {}
        status_groups = {"OK": 0, "Есть замечания": 0, "Требует внимания": 0}
        for owner, stats in sorted_owners:
            if stats["errors"] or stats["missing"]:
                status = "Требует внимания"
                status_groups["Требует внимания"] += 1
            elif stats["warnings"] or stats["extra"]:
                status = "Есть замечания"
                status_groups["Есть замечания"] += 1
            else:
                status = "OK"
                status_groups["OK"] += 1
            owner_statuses[owner] = status

        # --- Layout ---
        set_col_widths({1: 43.87, 2: 60, 3: 38, 4: 15.04, 5: 13.03, 6: 13, 7: 16, 8: 13})

        row = 1

        # Title
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        write_cell(row, 1, f"Сводка проверки протоколов за {month:02d}.{year}",
                   fill=section_fill, font=section_font,
                   alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 30
        row += 2

        # KPI row
        kpi_items = [
            ("Всего поверок АРШИН", len(calibrations), "plain"),
            ("Всего протоколов", len(protocols), "plain"),
            ("Сопоставлено", len(matched_protocols), "good"),
            ("Нет протокола", len(missing_cals), "bad"),
            ("Нет в Аршине", len(extra_protocols), "warn"),
            ("Ошибки", error_count, "bad"),
            ("Предупреждения", warning_count, "warn"),
            ("Дублей номеров", len(duplicate_numbers), "bad"),
        ]
        for col_idx, (label, value, kind) in enumerate(kpi_items, 1):
            write_cell(row, col_idx, label, fill=kpi_label_fill, font=kpi_label_font,
                       alignment=Alignment(horizontal="center", vertical="center", wrap_text=False))
            ws.row_dimensions[row].height = 30
            value_fill = good_fill if kind == "good" else (warn_fill if kind == "warn" else (bad_fill if kind == "bad" else None))
            value_font = good_font if kind == "good" else (warn_font if kind == "warn" else (bad_font if kind == "bad" else Font(color="305496", bold=True, size=11)))
            write_cell(row + 1, col_idx, value, fill=value_fill, font=value_font,
                       alignment=Alignment(horizontal="center", vertical="center"))
            ws.row_dimensions[row + 1].height = 34.5
        row += 3

        # Section: Per owner breakdown
        section_row = row
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        write_cell(row, 1, "Разбивка по Заказчикам", fill=section_fill, font=section_font,
                   alignment=Alignment(horizontal="left", vertical="center"))
        ws.row_dimensions[row].height = 24
        row += 1

        owner_headers = ["Заказчик", "Протоколов", "Сопоставлено", "Нет протокола", "Нет в Аршине", "Ошибки", "Предупр.", "Статус"]
        for col_idx, h in enumerate(owner_headers, 1):
            write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                       alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 21.75
        row += 1

        owner_table_start = row
        for owner, stats in sorted_owners:
            write_cell(row, 1, owner)
            write_cell(row, 2, stats["protocols"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 3, stats["matched"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 4, stats["missing"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 5, stats["extra"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 6, stats["errors"], alignment=Alignment(horizontal="center", vertical="center"))
            write_cell(row, 7, stats["warnings"], alignment=Alignment(horizontal="center", vertical="center"))
            status = owner_statuses[owner]
            if status == "OK":
                write_cell(row, 8, status, fill=good_fill, font=good_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            elif status == "Есть замечания":
                write_cell(row, 8, "Замечания", fill=warn_fill, font=warn_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            else:
                write_cell(row, 8, "Внимание", fill=bad_fill, font=bad_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            ws.row_dimensions[row].height = 15.75
            row += 1
        owner_table_end = row - 1
        row += 2

        # Section: Performed checks
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        write_cell(row, 1, "Выполненные проверки", fill=section_fill, font=section_font,
                   alignment=Alignment(horizontal="left", vertical="center"))
        ws.row_dimensions[row].height = 24
        row += 1

        check_headers = ["Проверка", "Описание"]
        for col_idx, h in enumerate(check_headers, 1):
            if col_idx == 1:
                write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            else:
                ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
                write_cell(row, 2, h, fill=header_fill, font=header_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 21.75
        row += 1

        performed_checks = [
            ("Наличие протокола", "Поверка АРШИН ↔ файл протокола. Поиск по заводскому номеру."),
            ("Сопоставление с АРШИН", "Файл протокола ↔ запись АРШИН. Поиск по заводскому номеру."),
            ("Дата поверки", "Дата в протоколе ↔ verification_date в АРШИН. Точное совпадение."),
            ("Дата действия до", "Дата в протоколе ↔ valid_date в АРШИН. Предупреждение, если совпадает."),
            ("ФИО поверителя", "Поверитель в ЛК АРШИН ↔ в протоколе. Точное совпадение после нормализации."),
            ("Условия окружающей среды", "t, φ, P в ЛК АРШИН ↔ в протоколе. Точное совпадение."),
            ("Уникальность номера протокола", "Номера протоколов между собой. Не должно повторяться."),
            ("Соответствие номеров", "Заводской номер в имени файла ↔ в протоколе. Доп. предупреждение при расхождении."),
        ]
        for check_name, desc in performed_checks:
            write_cell(row, 1, check_name)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
            write_cell(row, 2, desc, alignment=Alignment(horizontal="left", vertical="center", wrap_text=True))
            ws.row_dimensions[row].height = 15
            row += 1
        row += 1

        # Section: Legend
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        write_cell(row, 1, "Расшифровка ошибок и предупреждений", fill=section_fill, font=section_font,
                   alignment=Alignment(horizontal="left", vertical="center"))
        ws.row_dimensions[row].height = 24
        row += 1

        legend_headers = ["Тип", "Описание"]
        for col_idx, h in enumerate(legend_headers, 1):
            if col_idx == 1:
                write_cell(row, col_idx, h, fill=header_fill, font=header_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
            else:
                ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
                write_cell(row, 2, h, fill=header_fill, font=header_font,
                           alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[row].height = 21.75
        row += 1

        legend_items = [
            ("Ошибка", "Дата поверки не совпадает с verification_date в АРШИН; ФИО поверителя различается; условия окружающей среды не совпадают точно."),
            ("Предупреждение", "Дата в протоколе совпадает с valid_date в АРШИН, но не с verification_date (возможная путаница дат); заводской номер в имени файла отличается от номера в протоколе (доп. проверка)."),
            ("Отсутствует протокол", "Запись есть в АРШИН, файл протокола не найден по заводскому номеру."),
            ("Лишний протокол", "Файл протокола есть, записи в АРШИН по заводскому номеру нет."),
        ]
        for label, desc in legend_items:
            if label == "Ошибка":
                write_cell(row, 1, label, fill=bad_fill, font=bad_font)
            elif label == "Предупреждение":
                write_cell(row, 1, label, fill=warn_fill, font=warn_font)
            else:
                write_cell(row, 1, label)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
            write_cell(row, 2, desc, alignment=Alignment(horizontal="left", vertical="center", wrap_text=True))
            ws.row_dimensions[row].height = 15
            row += 1
        row += 1

        # Section: Duplicates
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        write_cell(row, 1, "Дубли номеров протоколов", fill=section_fill, font=section_font,
                   alignment=Alignment(horizontal="left", vertical="center"))
        ws.row_dimensions[row].height = 24
        row += 1

        if duplicate_numbers:
            dup_headers = ["Номер протокола", "Количество файлов", "Список файлов"]
            for col_idx, h in enumerate(dup_headers, 1):
                if col_idx == 1:
                    write_cell(row, 1, h, fill=header_fill, font=header_font,
                               alignment=Alignment(horizontal="center", vertical="center"))
                elif col_idx == 2:
                    write_cell(row, 2, h, fill=header_fill, font=header_font,
                               alignment=Alignment(horizontal="center", vertical="center"))
                else:
                    ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
                    write_cell(row, 3, h, fill=header_fill, font=header_font,
                               alignment=Alignment(horizontal="center", vertical="center"))
            ws.row_dimensions[row].height = 21.75
            row += 1
            for num, items in sorted(duplicate_numbers.items()):
                write_cell(row, 1, num)
                write_cell(row, 2, len(items), alignment=Alignment(horizontal="center", vertical="center"))
                file_list = ", ".join(
                    f"{p.protocol_file.relative_path if p.protocol_file else '—'}"
                    for p in items
                )
                ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
                write_cell(row, 3, file_list, alignment=Alignment(horizontal="left", vertical="center", wrap_text=True))
                ws.row_dimensions[row].height = 15
                row += 1
        else:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
            write_cell(row, 1, "Дубли не найдены", fill=good_fill, font=good_font,
                       alignment=Alignment(horizontal="left", vertical="center"))
            ws.row_dimensions[row].height = 15
            row += 1

        # Keep fixed widths from the manually tuned report
        ws.column_dimensions[get_column_letter(8)].width = max(ws.column_dimensions[get_column_letter(8)].width, 13)

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
        # Build calibrations lookup by (serial, mit_number) pair and by serial
        cal_by_pair: dict[tuple[str, str], list] = defaultdict(list)
        cal_by_serial: dict[str, list] = defaultdict(list)
        cal_by_norm_serial: dict[str, list] = defaultdict(list)
        for c in calibrations:
            if c.mi_number:
                serial = c.mi_number.strip()
                mit = (c.mit_number or "").strip()
                cal_by_serial.setdefault(serial, []).append(c)
                norm = self._normalize_serial(serial)
                if norm:
                    cal_by_norm_serial.setdefault(norm, []).append(c)
                    if mit:
                        cal_by_pair[(norm, mit)].append(c)

        def _find_cal_list(proto) -> list:
            """Find matching calibrations by serial+mit_number, falling back to serial only."""
            serial = (proto.serial_number or "").strip()
            mit = (proto.mit_number or "").strip()
            norm_serial = self._normalize_serial(serial)
            if norm_serial and mit:
                pair_list = cal_by_pair.get((norm_serial, mit), [])
                if pair_list:
                    return pair_list
            cal_list = cal_by_serial.get(serial, [])
            if not cal_list and norm_serial:
                cal_list = cal_by_norm_serial.get(norm_serial, [])
            return cal_list

        # Build set of protocol serials that have a match
        matched_cal_serials: set[str] = set()

        compare_headers = ["Статус", "Расхождения"]
        public_headers = ["№", "VRI ID", "№ОТ", "Наименование", "Обозначение", "Мод.", "Зав№",
                          "Дата", "Действует до", "№ док-та"]
        lk_headers = ["Поверитель", "t", "φ", "P"]
        proto_headers = ["№ протокола", "Наименование", "Зав№ из протокола",
                         "№ОТ", "Методика", "Год", "Владелец", "Дата",
                         "Поверитель", "t", "φ", "P"]
        all_headers = compare_headers + public_headers + lk_headers + proto_headers

        group_titles = [
            ("Сравнение", "5B9BD5", len(compare_headers)),
            ("Публичный АРШИН", "4472C4", len(public_headers)),
            ("ЛК АРШИН", "70AD47", len(lk_headers)),
            ("Протокол", "ED7D31", len(proto_headers)),
        ]

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

        row_num = 3
        display_num = 1

        # FIRST PASS: iterate by protocols (all files in folder order), find matching calibration(s)
        for proto in protocols:
            serial = (proto.serial_number or "").strip()
            norm_serial = self._normalize_serial(serial)
            mit = (proto.mit_number or "").strip()
            cal_list = _find_cal_list(proto)
            if cal_list:
                matched_cal_serials.add(serial)

            # Determine date status against ALL calibrations for this serial
            date_status = "no_arshin"
            best_cal = None
            if cal_list and proto.verification_date:
                proto_date = proto.verification_date
                # Exact match required
                exact_cals = [c for c in cal_list if c.verification_date == proto_date]
                if exact_cals:
                    date_status = "green"
                    best_cal = exact_cals[0]
                else:
                    yellow_cals = [c for c in cal_list if _dates_within(c.valid_date, proto_date)]
                    if yellow_cals:
                        date_status = "yellow"
                        best_cal = yellow_cals[0]
                    else:
                        date_status = "red"
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

            file_name_serial = ""
            if proto.protocol_file and proto.protocol_file.file_name:
                file_name_serial = self._extract_serial_from_filename(proto.protocol_file.file_name)

            row_data = [
                "",
                "",
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
                cal.verifier or "" if cal else "",
                fmt_num(lk_conditions.get("temperature")) if cal else "",
                fmt_num(lk_conditions.get("humidity")) if cal else "",
                fmt_num(lk_conditions.get("pressure")) if cal else "",
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
                # Multiple records warning only when they are truly for the same (serial, mit_number)
                if len(cal_list) > 1:
                    vri_ids = [c.vri_id for c in cal_list if c.vri_id]
                    vri_part = f" ({', '.join(vri_ids)})" if vri_ids else ""
                    mismatches.append(f"Записей в АРШИН: {len(cal_list)}{vri_part}")

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

                # Check conditions exact match
                for field in ("temperature", "humidity", "pressure"):
                    proto_val = getattr(proto, field, None)
                    cal_val = lk_conditions.get(field)
                    if proto_val is not None and cal_val is not None:
                        try:
                            if float(proto_val) != float(cal_val):
                                mismatches.append(f"{field}: {cal_val} vs {proto_val}")
                        except (ValueError, TypeError):
                            pass

            # Check serial from filename vs protocol (warning context only)
            if file_name_serial and serial and self._normalize_serial(file_name_serial) != self._normalize_serial(serial):
                mismatches.append(f"Зав№ в имени файла ({file_name_serial}) ≠ зав№ протокола ({serial})")

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
            cal_norm = self._normalize_serial(cal_serial)
            cal_mit = (cal.mit_number or "").strip()
            # Skip if a protocol matched this calibration by pair or by serial
            pair_matched = bool(cal_mit) and any(
                self._normalize_serial((p.serial_number or "").strip()) == cal_norm
                and (p.mit_number or "").strip() == cal_mit
                for p in protocols
            )
            serial_matched = any(
                (p.serial_number or "").strip() == cal_serial
                or self._normalize_serial((p.serial_number or "").strip()) == cal_norm
                for p in protocols
            )
            if not cal_serial or pair_matched or serial_matched:
                continue
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
                "", "", "", "", "", "", "", "", "", "",
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

    def _extract_serial_from_filename(self, file_name: str) -> str:
        """Extract serial number from protocol filename.

        Expected filename patterns:
            2025-10-06 № 009922 (МПИ-2).pdf  -> 009922
            2025.10.29 - 971041 (МПИ-2).pdf  -> 971041
            2025-10-01 № 735323116А16.pdf    -> 735323116А16
        """
        import re
        base = re.sub(r"\.pdf$", "", file_name, flags=re.IGNORECASE).strip()
        # Remove trailing parenthesized groups like (МПИ-2)
        base = re.sub(r"\s*\([^()]+\)\s*$", "", base)
        # Pattern: optional date prefix, then '№' or '-' followed by serial
        match = re.search(r"(?:№|[-–—])\s*([A-Za-zА-Яа-я0-9\-]+)$", base)
        if match:
            return match.group(1).strip()
        # Fallback: last whitespace-separated token
        tokens = base.split()
        if tokens:
            return tokens[-1].strip()
        return ""

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

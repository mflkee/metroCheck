"""ReportService — генерация детализированных Excel отчетов с тремя источниками."""

import json
import os
import re
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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

    async def generate_interim_report(self, year: int, month: int, output_dir: str = "/reports") -> dict[str, Any]:
        """Generate interim Excel report with full comparison layout."""
        calibrations = await self.cal_repo.get_by_month(year, month)
        protocols = await self.proto_repo.get_by_month(year, month)

        wb = Workbook()
        ws_public = wb.active
        ws_public.title = "1. ARSHIN Public API"
        self._fill_public_sheet(ws_public, calibrations)

        ws_lk = wb.create_sheet("2. ARSHIN LK")
        self._fill_lk_sheet(ws_lk, calibrations)

        ws_proto = wb.create_sheet("3. Протоколы")
        self._fill_protocol_sheet(ws_proto, protocols)

        ws_compare = wb.create_sheet("4. Сравнение")
        self._fill_comparison_sheet(ws_compare, calibrations, protocols)

        os.makedirs(output_dir, exist_ok=True)
        filename = f"report_{year}_{month:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
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

    def _fill_public_sheet(self, ws, calibrations) -> None:
        headers = ["№", "VRI ID", "MIT", "Наименование", "Обозначение", "Мод.", "Серийник",
                   "Дата", "Действует до", "№ док-та", "Результат", "Диапазон"]
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
                   cal.result_docnum, result_text, ""]
            self._write_data_row(ws, row, idx, "DDEBF7")
        self._set_column_widths(ws, [4, 14, 11, 22, 16, 14, 13, 12, 12, 20, 10, 18])

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
        self._set_column_widths(ws, [4, 14, 16, 8, 8, 9])

    def _fill_protocol_sheet(self, ws, protocols) -> None:
        headers = ["№", "№ протокола", "Наименование", "Тип", "Серийник",
                   "MIT", "Методика", "Год", "Владелец", "Дата",
                   "Поверитель", "t, °C", "φ, %", "P, кПа", "Диапазон", "Результат"]
        self._write_headers(ws, headers, "ED7D31")

        def fmt_num(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return str(val)

        for idx, proto in enumerate(protocols, 1):
            # Extract range from raw text
            proto_range = self._extract_range_from_text(proto.raw_text or "")
            row = [idx, proto.protocol_number or "", proto.device_name or "",
                   proto.device_type or "", proto.serial_number or "",
                   proto.mit_number or "", proto.verification_method or "",
                   proto.manufacture_year or "", proto.owner or "",
                   proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else "",
                   proto.verifier or "", fmt_num(proto.temperature),
                   fmt_num(proto.humidity), fmt_num(proto.pressure),
                   proto_range, proto.result or ""]
            self._write_data_row(ws, row, idx, "FCE4D6")
        self._set_column_widths(ws, [4, 15, 20, 14, 13, 11, 18, 6, 18, 12, 16, 8, 8, 9, 18, 10])

    def _fill_comparison_sheet(self, ws, calibrations, protocols) -> None:
        proto_by_serial = {}
        for p in protocols:
            if p.serial_number:
                proto_by_serial[p.serial_number.strip()] = p

        compare_headers = ["Статус", "Расхождения"]
        public_headers = ["№", "VRI ID", "MIT", "Наименование", "Обозначение", "Мод.", "Серийник",
                          "Дата", "Действует до", "№ док-та", "Результат", "Диапазон"]
        lk_headers = ["Поверитель", "t", "φ", "P"]
        proto_headers = ["№ протокола", "Наименование", "Тип", "Серийник",
                         "MIT", "Методика", "Год", "Владелец", "Дата",
                         "Поверитель", "t", "φ", "P", "Диапазон", "Результат"]
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

        for idx, cal in enumerate(calibrations, 1):
            serial = (cal.mi_number or "").strip()
            proto = proto_by_serial.get(serial)
            lk_conditions = {}
            if cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass
            if cal.result:
                result_text = cal.result
            elif cal.applicability is True:
                result_text = "пригоден"
            elif cal.applicability is False:
                result_text = "непригоден"
            else:
                result_text = ""

            def fmt_num(val):
                if val is None:
                    return ""
                try:
                    return f"{float(val):.1f}"
                except (ValueError, TypeError):
                    return str(val)

            # Extract protocol range
            proto_range = self._extract_range_from_text(proto.raw_text or "") if proto else ""
            # Extract ARSHIN range from conditions or empty
            arshin_range = lk_conditions.get("range", "") if cal.conditions else ""

            row_data = [
                # compare columns (status + comments) filled later
                "",
                "",
                # public headers
                idx, cal.vri_id, cal.mit_number, cal.mit_title, cal.mit_notation,
                cal.mi_modification, cal.mi_number,
                cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                cal.valid_date.strftime("%d.%m.%Y") if cal.valid_date else "",
                cal.result_docnum, result_text, arshin_range or "—",
                # lk headers
                cal.verifier or "", fmt_num(lk_conditions.get("temperature")),
                fmt_num(lk_conditions.get("humidity")), fmt_num(lk_conditions.get("pressure")),
                # proto headers
                proto.protocol_number if proto else "НЕТ ПРОТОКОЛА",
                proto.device_name if proto else "",
                proto.device_type if proto else "",
                proto.serial_number if proto else "",
                proto.mit_number if proto else "",
                proto.verification_method if proto else "",
                proto.manufacture_year if proto else "",
                proto.owner if proto else "",
                proto.verification_date.strftime("%d.%m.%Y") if proto and proto.verification_date else "",
                proto.verifier if proto else "",
                fmt_num(proto.temperature) if proto else "",
                fmt_num(proto.humidity) if proto else "",
                fmt_num(proto.pressure) if proto else "",
                proto_range or "—",
                proto.result if proto else "",
            ]

            mismatches = []
            info_notes = []

            if proto and proto.verification_date and cal.verification_date:
                proto_date = proto.verification_date.strftime("%d.%m.%Y")
                cal_date = cal.verification_date.strftime("%d.%m.%Y")
                if proto_date != cal_date:
                    mismatches.append(f"Дата: {cal_date} vs {proto_date}")

            if proto and proto.device_name and cal.mit_title:
                norm_proto = self._normalize_text(proto.device_name)
                norm_cal = self._normalize_text(cal.mit_title)
                if norm_proto not in norm_cal and norm_cal not in norm_proto:
                    proto_words = {w for w in norm_proto.split() if len(w) >= 3}
                    cal_words = {w for w in norm_cal.split() if len(w) >= 3}
                    if len(proto_words & cal_words) < 1:
                        mismatches.append(f"Наименование: {cal.mit_title} vs {proto.device_name}")

            # Methodology — ARSHIN has no direct field, show as info note if present
            if proto and proto.verification_method:
                info_notes.append(f"Методика: {proto.verification_method}")

            if proto and proto.verifier and cal.verifier:
                if proto.verifier != cal.verifier:
                    mismatches.append(f"Поверитель: {cal.verifier} vs {proto.verifier}")

            if proto and proto.result and cal.result:
                if proto.result != cal.result:
                    mismatches.append(f"Результат: {cal.result} vs {proto.result}")

            if proto and proto.serial_number and serial:
                if proto.serial_number.strip() != serial:
                    mismatches.append(f"Серийник: {serial} vs {proto.serial_number}")

            # Compare ranges (soft check)
            if proto and proto_range and arshin_range:
                if arshin_range not in ('—', ''):
                    if proto_range.lower() != arshin_range.lower():
                        mismatches.append(f"Диапазон: {arshin_range} vs {proto_range}")
            elif proto and proto_range and (not arshin_range or arshin_range in ('—', '')):
                info_notes.append(f"Диапазон в АРШИН отсутствует (в протоколе: {proto_range})")

            if not proto:
                mismatches.append("ПРОТОКОЛ ОТСУТСТВУЕТ")

            if mismatches:
                status = "❌"
                status_color = "FFC7CE"
                status_font_color = "9C0006"
            elif info_notes:
                status = "?"
                status_color = "FFF2CC"
                status_font_color = "806000"
            else:
                status = "✓"
                status_color = "C6EFCE"
                status_font_color = "006100"

            row_data[STATUS_COL - 1] = status
            comments = "; ".join(mismatches) if mismatches else ""
            if info_notes:
                if comments:
                    comments += " | " + "; ".join(info_notes)
                else:
                    comments = "; ".join(info_notes)
            row_data[COMMENTS_COL - 1] = comments

            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=idx + 2, column=col_idx, value=value)
                cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                   top=Side(style='thin'), bottom=Side(style='thin'))
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                if col_idx == STATUS_COL:
                    cell.fill = PatternFill(start_color=status_color, end_color=status_color, fill_type="solid")
                    cell.font = Font(bold=True, color=status_font_color, size=12)
                elif col_idx == COMMENTS_COL and (mismatches or info_notes):
                    if mismatches:
                        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                        cell.font = Font(color="9C0006", size=9)
                    else:
                        cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                        cell.font = Font(color="806000", size=9)

        widths = [
            5, 38,  # Статус, Расхождения
            4, 14, 11, 22, 16, 14, 13, 12, 12, 20, 10, 16,
            16, 7, 7, 8,
            14, 20, 14, 13, 11, 18, 6, 18, 12, 16, 7, 7, 8, 16, 10,
        ]
        self._set_column_widths(ws, widths)
        for row in range(3, len(calibrations) + 3):
            ws.row_dimensions[row].height = 35

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

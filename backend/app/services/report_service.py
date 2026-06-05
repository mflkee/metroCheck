"""ReportService — генерация детализированных Excel отчетов с тремя источниками."""

import json
import os
import re
from datetime import datetime
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
            full_name = (proto.device_name or "") + (" " + proto.device_type if proto.device_type else "")
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
        # Build calibrations lookup by serial number
        cal_by_serial = {}
        for c in calibrations:
            if c.mi_number:
                cal_by_serial[c.mi_number.strip()] = c

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

        row_num = 2

        # FIRST PASS: iterate by protocols (all files in folder order), find matching calibration
        for proto in protocols:
            serial = (proto.serial_number or "").strip()
            cal = cal_by_serial.get(serial)
            if cal:
                matched_cal_serials.add(serial)
            lk_conditions = {}
            if cal and cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            full_name = (proto.device_name or "") + (" " + proto.device_type if proto.device_type else "")

            row_data = [
                # compare columns (status + comments) filled later
                "",
                "",
                # public headers
                row_num - 1,
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

            if not cal:
                mismatches.append("НЕТ В АРШИН")

            if cal and proto.verification_date and cal.verification_date:
                proto_date = proto.verification_date.strftime("%d.%m.%Y")
                cal_date = cal.verification_date.strftime("%d.%m.%Y")
                if proto_date != cal_date:
                    mismatches.append(f"Дата: {cal_date} vs {proto_date}")

            if cal and proto.verifier and cal.verifier:
                norm_proto_verifier = re.sub(r'([А-ЯA-Z])\.\s+([А-ЯA-Z])\.', r'\1.\2.', proto.verifier)
                norm_cal_verifier = re.sub(r'([А-ЯA-Z])\.\s+([А-ЯA-Z])\.', r'\1.\2.', cal.verifier)
                if norm_proto_verifier != norm_cal_verifier:
                    mismatches.append(f"Поверитель: {cal.verifier} vs {proto.verifier}")

            if cal and proto.serial_number and serial:
                if proto.serial_number.strip() != serial:
                    mismatches.append(f"Серийник: {serial} vs {proto.serial_number}")

            if mismatches:
                status = "❌"
                status_color = "FFC7CE"
                status_font_color = "9C0006"
            else:
                status = "✓"
                status_color = "C6EFCE"
                status_font_color = "006100"

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
                    cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                    cell.font = Font(color="9C0006", size=9)
            row_num += 1

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
                    row_num - 1,
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

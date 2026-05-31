"""ReportService — генерация детализированных Excel отчетов с тремя источниками."""

import json
import os
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

    async def generate_interim_report(self, year: int, month: int, output_dir: str = "/reports") -> dict[str, Any]:
        """Generate interim Excel report with full comparison layout.

        Uses the same 3-group format as final report, but LK columns are empty.
        This ensures consistent report format regardless of token availability.
        """
        calibrations = await self.cal_repo.get_by_month(year, month)
        protocols = await self.proto_repo.get_by_month(year, month)

        wb = Workbook()

        # Sheet 1: ARSHIN Public API
        ws_public = wb.active
        ws_public.title = "1. ARSHIN Public API"
        self._fill_public_sheet(ws_public, calibrations)

        # Sheet 2: ARSHIN LK (will be empty if no token)
        ws_lk = wb.create_sheet("2. ARSHIN LK")
        self._fill_lk_sheet(ws_lk, calibrations)

        # Sheet 3: Протоколы
        ws_proto = wb.create_sheet("3. Протоколы")
        self._fill_protocol_sheet(ws_proto, protocols)

        # Sheet 4: Сравнение (full layout, LK columns will be empty)
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

    async def generate_report(self, run_id: int, output_dir: str = "/reports") -> dict[str, Any]:
        """Generate comprehensive Excel report for a check run.

        Sheets:
        1. ARSHIN Public API — все поля из публичного API
        2. ARSHIN LK — данные из личного кабинета
        3. Протоколы — данные из PDF протоколов
        4. Сравнение — полная сводная таблица со сравнением
        """
        run = await self.run_repo.get_by_id(run_id)
        if not run:
            return {"error": "Check run not found"}

        calibrations = await self.cal_repo.get_by_month(run.year, run.month)
        protocols = await self.proto_repo.get_by_month(run.year, run.month)

        wb = Workbook()

        # Sheet 1: ARSHIN Public API
        ws_public = wb.active
        ws_public.title = "1. ARSHIN Public API"
        self._fill_public_sheet(ws_public, calibrations)

        # Sheet 2: LK ARSHIN
        ws_lk = wb.create_sheet("2. ARSHIN LK")
        self._fill_lk_sheet(ws_lk, calibrations)

        # Sheet 3: Протоколы
        ws_proto = wb.create_sheet("3. Протоколы")
        self._fill_protocol_sheet(ws_proto, protocols)

        # Sheet 4: Сравнение
        ws_compare = wb.create_sheet("4. Сравнение")
        self._fill_comparison_sheet(ws_compare, calibrations, protocols)

        os.makedirs(output_dir, exist_ok=True)
        filename = f"report_{run.year}_{run.month:02d}_{run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = os.path.join(output_dir, filename)
        wb.save(file_path)

        return {
            "file_path": file_path,
            "filename": filename,
            "run_id": run_id,
            "total_calibrations": len(calibrations),
            "total_protocols": len(protocols),
        }

    def _fill_public_sheet(self, ws, calibrations) -> None:
        """Fill ARSHIN Public API sheet."""
        headers = [
            "№", "VRI ID", "Организация", "MIT номер", "Наименование типа",
            "Обозначение типа", "Модификация", "Серийный номер",
            "Дата поверки", "Действует до", "№ документа", "Результат"
        ]
        self._write_headers(ws, headers, "4472C4")

        for idx, cal in enumerate(calibrations, 1):
            # Map applicability boolean to text result
            if cal.result:
                result_text = cal.result
            elif cal.applicability is True:
                result_text = "пригоден"
            elif cal.applicability is False:
                result_text = "непригоден"
            else:
                result_text = ""
            
            row = [
                idx, cal.vri_id, cal.org_title, cal.mit_number, cal.mit_title,
                cal.mit_notation, cal.mi_modification, cal.mi_number,
                cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                cal.valid_date.strftime("%d.%m.%Y") if cal.valid_date else "",
                cal.result_docnum, result_text
            ]
            self._write_data_row(ws, row, idx, "DDEBF7")

        self._set_column_widths(ws, [5, 15, 20, 12, 25, 20, 15, 15, 12, 12, 25, 12])

    def _fill_lk_sheet(self, ws, calibrations) -> None:
        """Fill LK ARSHIN sheet — only fields we actually get from LK API.
        
        Matching: LK data is fetched by result_docnum (№ документа) from Public API.
        VRI ID shown as reference key to match with Sheet 1."""
        headers = [
            "№", "VRI ID (ссылка)", "Поверитель (ЛК)", "Температура (ЛК)", "Влажность (ЛК)", "Давление (ЛК)"
        ]
        self._write_headers(ws, headers, "70AD47")

        for idx, cal in enumerate(calibrations, 1):
            conditions = {}
            if cal.conditions:
                try:
                    conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            has_lk_data = bool(cal.verifier or cal.conditions)

            row = [
                idx,
                cal.vri_id,  # Reference to Public API record
                cal.verifier or ("НЕТ ДАННЫХ ЛК" if not has_lk_data else ""),
                conditions.get("temperature", ""),
                conditions.get("humidity", ""),
                conditions.get("pressure", "")
            ]
            self._write_data_row(ws, row, idx, "E2EFDA")

        self._set_column_widths(ws, [5, 18, 20, 14, 14, 14])

    def _fill_protocol_sheet(self, ws, protocols) -> None:
        """Fill Protocols sheet."""
        headers = [
            "№", "№ протокола", "Наименование", "Тип", "Серийный номер",
            "MIT номер", "Год выпуска", "Владелец", "Дата поверки",
            "Поверитель", "Температура, °C", "Влажность, %", "Давление, кПа", "Результат"
        ]
        self._write_headers(ws, headers, "ED7D31")

        def fmt_num(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return str(val)

        for idx, proto in enumerate(protocols, 1):
            row = [
                idx, proto.protocol_number or "", proto.device_name or "",
                proto.device_type or "", proto.serial_number or "",
                proto.mit_number or "", proto.manufacture_year or "",
                proto.owner or "",
                proto.verification_date.strftime("%d.%m.%Y") if proto.verification_date else "",
                proto.verifier or "", fmt_num(proto.temperature),
                fmt_num(proto.humidity), fmt_num(proto.pressure),
                proto.result or ""
            ]
            self._write_data_row(ws, row, idx, "FCE4D6")

        self._set_column_widths(ws, [5, 20, 20, 15, 15, 12, 12, 20, 12, 20, 10, 10, 10, 12])

    def _fill_interim_comparison_sheet(self, ws, calibrations, protocols) -> None:
        """Fill interim comparison sheet (Public API vs Protocols only, no LK data)."""
        proto_by_serial = {}
        for p in protocols:
            if p.serial_number:
                proto_by_serial[p.serial_number.strip()] = p

        headers = [
            "№", "VRI ID", "MIT номер", "Наименование типа", "Серийный номер",
            "Дата поверки (АРШИН)", "Результат (АРШИН)",
            "№ протокола", "Дата поверки (прот)", "Результат (прот)",
            "Поверитель (прот)", "Температура", "Влажность", "Давление",
            "Статус", "Примечание"
        ]
        self._write_headers(ws, headers, "4472C4")

        for idx, cal in enumerate(calibrations, 1):
            serial = (cal.mi_number or "").strip()
            proto = proto_by_serial.get(serial)

            row_data = [
                idx, cal.vri_id, cal.mit_number, cal.mit_title, cal.mi_number,
                cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                cal.result or "",
                proto.protocol_number if proto else "НЕТ ПРОТОКОЛА",
                proto.verification_date.strftime("%d.%m.%Y") if proto and proto.verification_date else "",
                proto.result if proto else "",
                proto.verifier if proto else "",
                proto.temperature if proto else "",
                proto.humidity if proto else "",
                proto.pressure if proto else "",
            ]

            # Determine status
            if not proto:
                status = "❌ Нет протокола"
                status_color = "FFC7CE"
                note = "Протокол не найден"
            else:
                mismatches = []
                if cal.verification_date and proto.verification_date:
                    if cal.verification_date != proto.verification_date:
                        mismatches.append("Дата")
                if cal.result and proto.result and cal.result != proto.result:
                    mismatches.append("Результат")
                if mismatches:
                    status = "⚠ Расхождения"
                    status_color = "FFEB9C"
                    note = ", ".join(mismatches)
                else:
                    status = "✓ Соответствует"
                    status_color = "C6EFCE"
                    note = ""

            row_data.extend([status, note])

            # Write row
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=idx + 1, column=col_idx, value=value)
                cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                   top=Side(style='thin'), bottom=Side(style='thin'))
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

                # Highlight status column
                if col_idx == len(row_data) - 1:
                    cell.fill = PatternFill(start_color=status_color, end_color=status_color, fill_type="solid")
                    cell.font = Font(bold=True, size=10)

            # Highlight note column if there are issues
            if "✓" not in status:
                note_cell = ws.cell(row=idx + 1, column=len(row_data))
                note_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                note_cell.font = Font(color="9C0006", size=9)

        self._set_column_widths(ws, [5, 12, 10, 20, 12, 12, 10, 18, 12, 10, 15, 10, 10, 10, 15, 25])

    def _fill_comparison_sheet(self, ws, calibrations, protocols) -> None:
        """Fill comprehensive comparison sheet with grouped headers.
        Layout: Group headers (row 1) | Column headers (row 2) | Data"""

        # Map protocols by serial number for lookup
        proto_by_serial = {}
        for p in protocols:
            if p.serial_number:
                proto_by_serial[p.serial_number.strip()] = p

        # Build comprehensive headers
        # Section 1: ARSHIN Public
        public_headers = [
            "№", "VRI ID", "MIT номер", "Наименование типа", "Обозначение типа",
            "Модификация", "Серийный номер", "Дата поверки", "Действует до",
            "№ документа", "Результат"
        ]

        # Section 2: LK
        lk_headers = [
            "Поверитель", "Температура, °C", "Влажность, %", "Давление, кПа"
        ]

        # Section 3: Protocol
        proto_headers = [
            "№ протокола", "Наименование", "Тип", "Серийный номер",
            "MIT номер", "Год выпуска", "Владелец", "Дата поверки",
            "Поверитель", "Температура, °C", "Влажность, %", "Давление, кПа", "Результат"
        ]

        # Section 4: Comparison
        compare_headers = ["Статус сравнения", "Расхождения"]

        all_headers = public_headers + lk_headers + proto_headers + compare_headers

        # Group titles
        group_titles = [
            ("Публичный интерфейс АРШИН", "4472C4", len(public_headers)),
            ("Личный кабинет АРШИН", "70AD47", len(lk_headers)),
            ("Протокол", "ED7D31", len(proto_headers)),
            ("Результат сравнения", "5B9BD5", len(compare_headers))
        ]

        from openpyxl.utils import get_column_letter

        # Write group headers (row 1)
        col_start = 1
        for title, color, span in group_titles:
            col_end = col_start + span - 1
            if span > 1:
                ws.merge_cells(start_row=1, start_column=col_start, end_row=1, end_column=col_end)
            
            cell = ws.cell(row=1, column=col_start, value=title)
            cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF", size=12)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                               top=Side(style='thin'), bottom=Side(style='thin'))
            
            col_start = col_end + 1

        ws.row_dimensions[1].height = 30

        # Write column headers (row 2)
        header_fills = {
            "4472C4": list(range(len(public_headers))),
            "70AD47": list(range(len(public_headers), len(public_headers) + len(lk_headers))),
            "ED7D31": list(range(len(public_headers) + len(lk_headers),
                                 len(public_headers) + len(lk_headers) + len(proto_headers))),
            "5B9BD5": list(range(len(public_headers) + len(lk_headers) + len(proto_headers),
                                 len(all_headers)))
        }

        for col_idx, header in enumerate(all_headers, 1):
            cell = ws.cell(row=2, column=col_idx, value=header)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                               top=Side(style='thin'), bottom=Side(style='thin'))

            for color, cols in header_fills.items():
                if col_idx - 1 in cols:
                    cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
                    break

        ws.row_dimensions[2].height = 40
        
        # Add AutoFilter
        last_col = get_column_letter(len(all_headers))
        ws.auto_filter.ref = f"A2:{last_col}2"

        # Write data rows (starting from row 3)
        for idx, cal in enumerate(calibrations, 1):
            serial = (cal.mi_number or "").strip()
            proto = proto_by_serial.get(serial)

            # Parse LK conditions
            lk_conditions = {}
            if cal.conditions:
                try:
                    lk_conditions = json.loads(cal.conditions)
                except json.JSONDecodeError:
                    pass

            # Map applicability to text result
            if cal.result:
                result_text = cal.result
            elif cal.applicability is True:
                result_text = "пригоден"
            elif cal.applicability is False:
                result_text = "непригоден"
            else:
                result_text = ""

            # Format numbers with 1 decimal
            def fmt_num(val):
                if val is None:
                    return ""
                try:
                    return f"{float(val):.1f}"
                except (ValueError, TypeError):
                    return str(val)

            # Build row data
            row_data = [
                # Public section
                idx, cal.vri_id, cal.mit_number, cal.mit_title, cal.mit_notation,
                cal.mi_modification, cal.mi_number,
                cal.verification_date.strftime("%d.%m.%Y") if cal.verification_date else "",
                cal.valid_date.strftime("%d.%m.%Y") if cal.valid_date else "",
                cal.result_docnum, result_text,

                # LK section
                cal.verifier or "",
                fmt_num(lk_conditions.get("temperature")),
                fmt_num(lk_conditions.get("humidity")),
                fmt_num(lk_conditions.get("pressure")),

                # Protocol section
                proto.protocol_number if proto else "НЕТ ПРОТОКОЛА",
                proto.device_name if proto else "",
                proto.device_type if proto else "",
                proto.serial_number if proto else "",
                proto.mit_number if proto else "",
                proto.manufacture_year if proto else "",
                proto.owner if proto else "",
                proto.verification_date.strftime("%d.%m.%Y") if proto and proto.verification_date else "",
                proto.verifier if proto else "",
                fmt_num(proto.temperature) if proto else "",
                fmt_num(proto.humidity) if proto else "",
                fmt_num(proto.pressure) if proto else "",
                proto.result if proto else "",
            ]

            # Compare and highlight mismatches
            mismatches = []

            # Compare dates
            if proto and proto.verification_date and cal.verification_date:
                proto_date = proto.verification_date.strftime("%d.%m.%Y")
                cal_date = cal.verification_date.strftime("%d.%m.%Y")
                if proto_date != cal_date:
                    mismatches.append(f"Дата: {cal_date} vs {proto_date}")

            # Compare verifiers (LK vs Protocol)
            if proto and proto.verifier and cal.verifier:
                if proto.verifier != cal.verifier:
                    mismatches.append(f"Поверитель: {cal.verifier} vs {proto.verifier}")

            # Compare results
            if proto and proto.result and cal.result:
                if proto.result != cal.result:
                    mismatches.append(f"Результат: {cal.result} vs {proto.result}")

            # Compare serial numbers
            if proto and proto.serial_number and serial:
                if proto.serial_number.strip() != serial:
                    mismatches.append(f"Серийник: {serial} vs {proto.serial_number}")

            # Check if protocol missing
            if not proto:
                mismatches.append("ПРОТОКОЛ ОТСУТСТВУЕТ")

            # Determine status
            if mismatches:
                status = "❌ Несоответствия"
                status_color = "FFC7CE"
                status_font_color = "9C0006"
            else:
                status = "✓ Соответствует"
                status_color = "C6EFCE"
                status_font_color = "006100"

            row_data.append(status)
            row_data.append("; ".join(mismatches) if mismatches else "")

            # Write row
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=idx + 2, column=col_idx, value=value)
                cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                   top=Side(style='thin'), bottom=Side(style='thin'))
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

                # Highlight status column
                if col_idx == len(row_data) - 1:
                    cell.fill = PatternFill(start_color=status_color, end_color=status_color, fill_type="solid")
                    cell.font = Font(bold=True, color=status_font_color, size=10)

                # Highlight mismatch column
                elif col_idx == len(row_data) and mismatches:
                    cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                    cell.font = Font(color="9C0006", size=9)

        # Set column widths
        widths = [
            5, 15, 12, 30, 20, 18, 15, 14, 14, 25, 12,
            20, 16, 14, 14,
            20, 25, 18, 15, 12, 12, 25, 14, 20, 16, 14, 14, 12,
            18, 40
        ]
        self._set_column_widths(ws, widths)
        
        # Set row height for data rows
        for row in range(3, len(calibrations) + 3):
            ws.row_dimensions[row].height = 45

    def _write_headers(self, ws, headers, color) -> None:
        """Write colored headers with AutoFilter."""
        fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(left=Side(style='thin'), right=Side(style='thin'),
                       top=Side(style='thin'), bottom=Side(style='thin'))

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = border

        ws.row_dimensions[1].height = 30
        
        # Add AutoFilter for filtering capability
        from openpyxl.utils import get_column_letter
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A1:{last_col}1"

    def _write_data_row(self, ws, row_data, row_idx, color) -> None:
        """Write data row with colored background."""
        fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'),
                       top=Side(style='thin'), bottom=Side(style='thin'))

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx + 1, column=col_idx, value=value)
            cell.fill = fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def _set_column_widths(self, ws, widths) -> None:
        """Set column widths."""
        from openpyxl.utils import get_column_letter
        for idx, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(idx)].width = width

"""ReportService — генерация Excel отчетов."""

import os
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.check_result_repository import CheckResultRepository
from app.repositories.check_run_repository import CheckRunRepository


class ReportService:
    """Service for generating Excel reports."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.result_repo = CheckResultRepository(db)
        self.run_repo = CheckRunRepository(db)

    async def generate_report(self, run_id: int, output_dir: str = "/tmp/reports") -> dict[str, Any]:
        """Generate Excel report for a check run.

        Returns:
            dict with file_path, download_url
        """
        run = await self.run_repo.get_by_id(run_id)
        if not run:
            return {"error": "Check run not found"}

        results = await self.result_repo.get_by_run_id(run_id)
        errors = [r for r in results if r.status in ("error", "missing")]
        warnings = [r for r in results if r.status == "warning"]
        ok_results = [r for r in results if r.status == "ok"]

        # Create workbook
        wb = Workbook()

        # Sheet 1: Summary
        ws_summary = wb.active
        ws_summary.title = "Сводка"
        self._fill_summary(ws_summary, run, len(results), len(errors), len(warnings), len(ok_results))

        # Sheet 2: Errors
        ws_errors = wb.create_sheet("Ошибки")
        self._fill_errors(ws_errors, errors)

        # Sheet 3: Warnings
        ws_warnings = wb.create_sheet("Предупреждения")
        self._fill_warnings(ws_warnings, warnings)

        # Sheet 4: All results
        ws_all = wb.create_sheet("Все результаты")
        self._fill_all_results(ws_all, results)

        # Save
        os.makedirs(output_dir, exist_ok=True)
        filename = f"report_{run.year}_{run.month:02d}_{run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = os.path.join(output_dir, filename)
        wb.save(file_path)

        return {
            "file_path": file_path,
            "filename": filename,
            "run_id": run_id,
            "total": len(results),
            "errors": len(errors),
            "warnings": len(warnings),
            "ok": len(ok_results),
        }

    def _fill_summary(
        self,
        ws,
        run,
        total: int,
        errors: int,
        warnings: int,
        ok: int,
    ) -> None:
        """Fill summary sheet."""
        headers = ["Параметр", "Значение"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF")

        data = [
            ["Период", f"{run.month:02d}.{run.year}"],
            ["Дата проверки", run.started_at.strftime("%d.%m.%Y %H:%M")],
            ["Статус", run.status],
            ["Всего проверок", total],
            ["Ошибок", errors],
            ["Предупреждений", warnings],
            ["Успешно", ok],
            ["Поверок в АРШИНе", run.total_calibrations],
            ["Протоколов найдено", run.total_protocols],
        ]

        for row in data:
            ws.append(row)

        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 20

    def _fill_errors(self, ws, errors) -> None:
        """Fill errors sheet."""
        headers = ["Тип проверки", "Статус", "Комментарий", "ID поверки", "ID протокола"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="FF6B6B", end_color="FF6B6B", fill_type="solid")

        for err in errors:
            ws.append([
                err.check_type,
                err.status,
                err.comment or "",
                err.calibration_id or "",
                err.protocol_data_id or "",
            ])

        for col in ["A", "B", "C", "D", "E"]:
            ws.column_dimensions[col].width = 20
        ws.column_dimensions["C"].width = 50

    def _fill_warnings(self, ws, warnings) -> None:
        """Fill warnings sheet."""
        headers = ["Тип проверки", "Статус", "Комментарий", "ID поверки", "ID протокола"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="FFD93D", end_color="FFD93D", fill_type="solid")

        for warn in warnings:
            ws.append([
                warn.check_type,
                warn.status,
                warn.comment or "",
                warn.calibration_id or "",
                warn.protocol_data_id or "",
            ])

        for col in ["A", "B", "C", "D", "E"]:
            ws.column_dimensions[col].width = 20
        ws.column_dimensions["C"].width = 50

    def _fill_all_results(self, ws, results) -> None:
        """Fill all results sheet."""
        headers = ["Тип проверки", "Статус", "Комментарий", "ID поверки", "ID протокола", "Дата"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF")

        for r in results:
            ws.append([
                r.check_type,
                r.status,
                r.comment or "",
                r.calibration_id or "",
                r.protocol_data_id or "",
                r.created_at.strftime("%d.%m.%Y %H:%M") if r.created_at else "",
            ])

        for col in ["A", "B", "C", "D", "E", "F"]:
            ws.column_dimensions[col].width = 20
        ws.column_dimensions["C"].width = 50

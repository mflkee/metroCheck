"""Report generation endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.dependencies.auth import get_current_user
from app.services.report_service import ReportService

router = APIRouter()


@router.post("/generate/{run_id}")
async def generate_report(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate Excel report for a check run."""
    service = ReportService(db)
    result = await service.generate_report(run_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/download/{run_id}")
async def download_report(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download generated report for a check run."""
    import os
    from app.repositories.check_run_repository import CheckRunRepository

    run_repo = CheckRunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Check run not found")

    # Find the latest report file for this run
    reports_dir = "/tmp/reports"
    if not os.path.exists(reports_dir):
        raise HTTPException(status_code=404, detail="No reports found")

    files = [f for f in os.listdir(reports_dir) if f.startswith(f"report_{run.year}_{run.month:02d}_{run.id}_")]
    if not files:
        raise HTTPException(status_code=404, detail="Report not generated yet")

    latest_file = sorted(files)[-1]
    file_path = os.path.join(reports_dir, latest_file)

    return FileResponse(
        file_path,
        filename=latest_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

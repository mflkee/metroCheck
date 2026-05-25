"""Protocol file management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.protocol_scanner import ProtocolScanner

router = APIRouter()


class ScanRequest(BaseModel):
    year: int
    month: int
    path: str | None = None


class ProtocolDataSaveRequest(BaseModel):
    protocol_id: int
    data: dict
    model_used: str
    confidence: float
    cost: float


@router.post("/scan")
async def scan_protocols(
    payload: ScanRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan protocol folder for PDF files."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    base_path = payload.path or settings.MKAIR_PROTOCOLS_PATH or "/protocols"
    scanner = ProtocolScanner(db, base_path)
    result = await scanner.scan(payload.year, payload.month)
    return result


@router.post("/{protocol_id}/extract")
async def extract_text(
    protocol_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Extract text from a protocol PDF."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    base_path = settings.MKAIR_PROTOCOLS_PATH or "/protocols"
    scanner = ProtocolScanner(db, base_path)
    result = await scanner.extract_text(protocol_id)
    return result


@router.get("/list")
async def list_protocols(
    year: int,
    month: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List scanned protocols for a given month."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.repositories.protocol_file_repository import ProtocolFileRepository
    repo = ProtocolFileRepository(db)
    protocols = await repo.get_by_month(year, month)
    return {
        "year": year,
        "month": month,
        "count": len(protocols),
        "protocols": [
            {
                "id": p.id,
                "file_name": p.file_name,
                "relative_path": p.relative_path,
                "status": p.status,
                "size_bytes": p.size_bytes,
            }
            for p in protocols
        ],
    }


@router.post("/data")
async def save_protocol_data(
    payload: ProtocolDataSaveRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save extracted protocol data."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.repositories.protocol_data_repository import ProtocolDataRepository
    repo = ProtocolDataRepository(db)

    # Parse date if present
    from datetime import datetime
    verification_date = None
    if payload.data.get("verification_date"):
        try:
            verification_date = datetime.strptime(
                payload.data["verification_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            pass

    data = await repo.create(
        protocol_file_id=payload.protocol_id,
        protocol_number=payload.data.get("protocol_number"),
        device_name=payload.data.get("device_name"),
        device_type=payload.data.get("device_type"),
        serial_number=payload.data.get("serial_number"),
        mit_number=payload.data.get("mit_number"),
        manufacture_year=payload.data.get("manufacture_year"),
        owner=payload.data.get("owner"),
        verification_date=verification_date,
        verifier=payload.data.get("verifier"),
        temperature=payload.data.get("temperature"),
        humidity=payload.data.get("humidity"),
        pressure=payload.data.get("pressure"),
        pressure_units=payload.data.get("pressure_units"),
        result=payload.data.get("result"),
        verification_method=payload.data.get("verification_method"),
        model_used=payload.model_used,
        confidence=payload.confidence,
        cost=payload.cost,
    )
    return {"id": data.id, "status": "saved"}

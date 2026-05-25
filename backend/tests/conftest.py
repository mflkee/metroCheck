"""Shared test fixtures for check_service tests."""

from unittest.mock import AsyncMock, MagicMock
from datetime import date

import pytest

from app.models.calibration import Calibration
from app.models.protocol_data import ProtocolData
from tests.fixtures.arshin_data import SAMPLE_CALIBRATIONS_VRI, SAMPLE_PROTOCOL_EXTRACTIONS


def _make_calibration(vri_item: dict, year: int = 2025, month: int = 12) -> Calibration:
    """Build an in-memory Calibration instance from VRI data."""
    from datetime import datetime

    def parse_date(value: str | None) -> date | None:
        if not value:
            return None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        return None

    cal = Calibration(
        vri_id=vri_item["vri_id"],
        org_title=vri_item.get("org_title", 'ООО "МКАИР"'),
        mit_number=vri_item.get("mit_number"),
        mit_title=vri_item.get("mit_title"),
        mi_number=(vri_item.get("mi_number") or "").strip(),
        verification_date=parse_date(vri_item.get("verification_date")),
        valid_date=parse_date(vri_item.get("valid_date")),
        result_docnum=vri_item.get("result_docnum"),
        result="suitable" if vri_item.get("applicability") else "unsuitable",
        year=year,
        month=month,
    )
    # Assign IDs sequentially
    cal.id = SAMPLE_CALIBRATIONS_VRI.index(vri_item) + 1
    return cal


def _make_protocol_data(extraction: dict, proto_id: int = 1) -> ProtocolData:
    """Build an in-memory ProtocolData instance from extraction data."""
    proto = ProtocolData(
        protocol_file_id=proto_id,
        protocol_number=extraction.get("protocol_number"),
        device_name=extraction.get("device_name"),
        device_type=extraction.get("device_type"),
        serial_number=extraction.get("serial_number"),
        mit_number=extraction.get("mit_number"),
        manufacture_year=extraction.get("manufacture_year"),
        owner=extraction.get("owner"),
        verification_date=extraction.get("verification_date"),
        verifier=extraction.get("verifier"),
        temperature=extraction.get("temperature"),
        humidity=extraction.get("humidity"),
        pressure=extraction.get("pressure"),
        pressure_units=extraction.get("pressure_units"),
        result=extraction.get("result"),
        verification_method=extraction.get("verification_method"),
        raw_text="",
        model_used="test",
        confidence=1.0,
        cost=0.0,
        attempts=1,
        status="success",
    )
    proto.id = proto_id
    return proto


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_calibrations():
    """Return 3 Calibration instances matching the test protocols."""
    return [_make_calibration(item) for item in SAMPLE_CALIBRATIONS_VRI[1:4]]


@pytest.fixture
def sample_protocols():
    """Return 3 ProtocolData instances from AI extraction."""
    return [
        _make_protocol_data(SAMPLE_PROTOCOL_EXTRACTIONS[0], 1),
        _make_protocol_data(SAMPLE_PROTOCOL_EXTRACTIONS[1], 2),
        _make_protocol_data(SAMPLE_PROTOCOL_EXTRACTIONS[2], 3),
    ]


@pytest.fixture
def sample_calibration_with_verifier():
    """Return a calibration with LK data (verifier + conditions)."""
    cal = _make_calibration(SAMPLE_CALIBRATIONS_VRI[1])
    cal.verifier = "Чупин А.А."
    cal.conditions = '{"temperature": "20,1°С", "humidity": "30,0", "pressure": "100,9 кПа"}'
    return cal


@pytest.fixture
def mock_cal_repo(sample_calibrations):
    """Create a mock CalibrationRepository."""
    repo = MagicMock()
    repo.get_by_month = AsyncMock(return_value=sample_calibrations)
    repo.get_by_serial = AsyncMock(return_value=sample_calibrations[0])
    return repo


@pytest.fixture
def mock_data_repo(sample_protocols):
    """Create a mock ProtocolDataRepository."""
    repo = MagicMock()
    repo.get_by_month = AsyncMock(return_value=sample_protocols)
    repo.get_by_serial = AsyncMock(side_effect=lambda s: next(
        (p for p in sample_protocols if p.serial_number == s), None
    ))
    return repo


@pytest.fixture
def mock_proto_file_repo():
    """Create a mock ProtocolFileRepository."""
    repo = MagicMock()
    return repo

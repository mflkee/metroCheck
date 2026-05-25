"""Tests for CheckService business logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.check_service import CheckService
from tests.fixtures.arshin_data import (
    SAMPLE_CALIBRATIONS_VRI,
    SAMPLE_PROTOCOL_EXTRACTIONS,
)


class TestNormalizeSerial:
    """Test homoglyph normalization of serial numbers."""

    def test_cyrillic_to_latin(self):
        service = CheckService(None)
        assert service._normalize_serial("С2065928") == "C2065928"

    def test_mixed_cyrillic_latin(self):
        service = CheckService(None)
        assert service._normalize_serial("АВСЕКМ") == "ABCEKM"

    def test_already_normalized(self):
        service = CheckService(None)
        assert service._normalize_serial("ABC123") == "ABC123"

    def test_empty_string(self):
        service = CheckService(None)
        assert service._normalize_serial("") == ""

    def test_all_homoglyphs(self):
        service = CheckService(None)
        original = "АВСЕКМНОРТХ"
        expected = "ABCEKMHOPTX"
        assert service._normalize_serial(original) == expected

    def test_lowercase_homoglyphs(self):
        service = CheckService(None)
        assert service._normalize_serial("аеорс") == "AEOPC"


class TestCheckCompleteness:
    """Test completeness check — every calibration needs a protocol."""

    async def test_all_calibrations_have_protocols(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=sample_calibrations)
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(side_effect=lambda s: next(
            (p for p in sample_protocols if p.serial_number == s), None
        ))

        results = await service._check_completeness(1, 2025, 12)

        assert len(results) == len(sample_calibrations)
        assert all(r.status == "ok" for r in results)
        assert all(r.check_type == "completeness" for r in results)

    async def test_missing_protocol(self, mock_db, sample_calibrations):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=sample_calibrations)
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=None)

        results = await service._check_completeness(1, 2025, 12)

        assert len(results) == len(sample_calibrations)
        assert all(r.status == "missing" for r in results)
        assert all("No protocol found" in r.comment for r in results)

    async def test_partial_missing(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=sample_calibrations)
        service.data_repo = MagicMock()
        # Only first serial has matching protocol
        service.data_repo.get_by_serial = AsyncMock(side_effect=lambda s: (
            sample_protocols[0] if s == sample_protocols[0].serial_number else None
        ))

        results = await service._check_completeness(1, 2025, 12)

        ok_results = [r for r in results if r.status == "ok"]
        missing_results = [r for r in results if r.status == "missing"]
        assert len(ok_results) == 1
        assert len(missing_results) == len(sample_calibrations) - 1


class TestCheckProtocolsFound:
    """Test protocol found check — every protocol needs a calibration."""

    async def test_all_protocols_have_calibrations(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.data_repo = MagicMock()
        service.data_repo.get_by_month = AsyncMock(return_value=sample_protocols)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_serial = AsyncMock(side_effect=lambda s: (
            sample_calibrations[0]
        ))

        results = await service._check_protocols_found(1, 2025, 12)

        assert len(results) == len(sample_protocols)
        assert all(r.status == "ok" for r in results)

    async def test_protocol_without_serial(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        sample_protocols[0].serial_number = None
        service.data_repo = MagicMock()
        service.data_repo.get_by_month = AsyncMock(return_value=sample_protocols)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_serial = AsyncMock(return_value=sample_calibrations[0])

        results = await service._check_protocols_found(1, 2025, 12)

        warning_results = [r for r in results if r.status == "warning"]
        assert any("no serial number" in r.comment.lower() for r in warning_results)

    async def test_no_calibration_found(self, mock_db, sample_protocols):
        service = CheckService(mock_db)
        service.data_repo = MagicMock()
        service.data_repo.get_by_month = AsyncMock(return_value=sample_protocols)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_serial = AsyncMock(return_value=None)

        results = await service._check_protocols_found(1, 2025, 12)

        assert all(r.status == "warning" for r in results)
        assert all("No calibration found" in r.comment for r in results)


class TestCheckDataMatch:
    """Test data match check — compare ARSHIN vs protocol fields."""

    async def test_all_fields_match(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=sample_calibrations)
        service.data_repo = MagicMock()

        # Match calibrations with protocols by serial
        def get_by_serial(serial):
            for p in sample_protocols:
                if p.serial_number == serial:
                    return p
            return None

        service.data_repo.get_by_serial = AsyncMock(side_effect=get_by_serial)

        # Set verifier on calibrations to match protocols
        for cal, proto in zip(sample_calibrations, sample_protocols):
            cal.verifier = proto.verifier
            cal.verification_date = proto.verification_date

        results = await service._check_data_match(1, 2025, 12)

        ok_results = [r for r in results if r.status == "ok"]
        assert len(ok_results) == len(sample_calibrations)

    async def test_verifier_mismatch(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=[sample_calibrations[0]])
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=sample_protocols[0])

        sample_calibrations[0].verifier = "Иванов И.И."
        sample_calibrations[0].verification_date = sample_protocols[0].verification_date

        results = await service._check_data_match(1, 2025, 12)

        error_results = [r for r in results if r.status == "error"]
        assert len(error_results) == 1
        assert "Verifier mismatch" in error_results[0].comment

    async def test_date_mismatch(self, mock_db, sample_calibrations, sample_protocols):
        from datetime import date

        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=[sample_calibrations[0]])
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=sample_protocols[0])

        sample_calibrations[0].verifier = sample_protocols[0].verifier
        sample_calibrations[0].verification_date = date(2025, 11, 15)

        results = await service._check_data_match(1, 2025, 12)

        error_results = [r for r in results if r.status == "error"]
        assert len(error_results) == 1
        assert "Date mismatch" in error_results[0].comment

    async def test_temperature_out_of_range(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=[sample_calibrations[0]])
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=sample_protocols[0])

        sample_calibrations[0].verifier = sample_protocols[0].verifier
        sample_calibrations[0].verification_date = sample_protocols[0].verification_date
        sample_protocols[0].temperature = 999.0

        results = await service._check_data_match(1, 2025, 12)

        warning_results = [r for r in results if r.status == "warning"]
        assert len(warning_results) == 1
        assert "Temperature out of range" in warning_results[0].comment

    async def test_humidity_out_of_range(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=[sample_calibrations[0]])
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=sample_protocols[0])

        sample_calibrations[0].verifier = sample_protocols[0].verifier
        sample_calibrations[0].verification_date = sample_protocols[0].verification_date
        sample_protocols[0].humidity = 150.0

        results = await service._check_data_match(1, 2025, 12)

        warning_results = [r for r in results if r.status == "warning"]
        assert len(warning_results) == 1
        assert "Humidity out of range" in warning_results[0].comment

    async def test_case_insensitive_verifier(self, mock_db, sample_calibrations, sample_protocols):
        service = CheckService(mock_db)
        service.cal_repo = MagicMock()
        service.cal_repo.get_by_month = AsyncMock(return_value=[sample_calibrations[0]])
        service.data_repo = MagicMock()
        service.data_repo.get_by_serial = AsyncMock(return_value=sample_protocols[0])

        sample_calibrations[0].verifier = "чупин а.а."
        sample_calibrations[0].verification_date = sample_protocols[0].verification_date
        sample_protocols[0].verifier = "Чупин А.А."

        results = await service._check_data_match(1, 2025, 12)

        ok_results = [r for r in results if r.status == "ok"]
        assert len(ok_results) >= 1

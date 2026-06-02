"""CheckService — бизнес-логика проверок протоколов."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.check_result import CheckResult
from app.models.check_run import CheckRun
from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.protocol_data_repository import ProtocolDataRepository
from app.repositories.protocol_file_repository import ProtocolFileRepository


class CheckService:
    """Service for running checks on calibrations vs protocols."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cal_repo = CalibrationRepository(db)
        self.proto_repo = ProtocolFileRepository(db)
        self.data_repo = ProtocolDataRepository(db)

    async def run_checks(self, year: int, month: int) -> dict[str, Any]:
        """Run all checks for a given month.

        Steps:
        1. Completeness: all calibrations have protocols
        2. Protocol found: all protocols match a calibration
        3. Data match: compare verifier, date, temperature, humidity, pressure
        """
        # Create check run
        check_run = CheckRun(year=year, month=month, status="running")
        self.db.add(check_run)
        await self.db.commit()
        await self.db.refresh(check_run)

        try:
            results = []

            # 1. Completeness check
            completeness_results = await self._check_completeness(check_run.id, year, month)
            results.extend(completeness_results)

            # 2. Protocol found check
            found_results = await self._check_protocols_found(check_run.id, year, month)
            results.extend(found_results)

            # 3. Data match check
            match_results = await self._check_data_match(check_run.id, year, month)
            results.extend(match_results)

            # Update check run
            errors = sum(1 for r in results if r.status == "error")
            warnings = sum(1 for r in results if r.status == "warning")
            missing = sum(1 for r in results if r.status == "missing")

            check_run.status = "completed"
            check_run.errors_count = errors
            check_run.warnings_count = warnings
            check_run.total_calibrations = await self._count_calibrations(year, month)
            check_run.total_protocols = await self._count_protocols(year, month)

            import json
            check_run.summary_json = json.dumps({
                "errors": errors,
                "warnings": warnings,
                "missing": missing,
                "total_checks": len(results),
            })

            await self.db.commit()

            return {
                "run_id": check_run.id,
                "status": "completed",
                "errors": errors,
                "warnings": warnings,
                "missing": missing,
                "total": len(results),
            }

        except Exception as e:
            check_run.status = "failed"
            await self.db.commit()
            return {"run_id": check_run.id, "status": "failed", "error": str(e)}

    async def _check_completeness(self, run_id: int, year: int, month: int) -> list[CheckResult]:
        """Check that all calibrations have matching protocols."""
        from sqlalchemy import select
        from app.models.calibration import Calibration

        results = []
        calibrations = await self.cal_repo.get_by_month(year, month)

        for cal in calibrations:
            # Find protocol by serial number (with homoglyph normalization)
            serial = self._normalize_serial(cal.mi_number or "")
            protocol = await self.data_repo.get_by_serial(serial)

            if not protocol:
                result = CheckResult(
                    check_run_id=run_id,
                    calibration_id=cal.id,
                    check_type="completeness",
                    status="missing",
                    comment=f"No protocol found for serial number: {cal.mi_number}",
                )
                self.db.add(result)
                results.append(result)
            else:
                result = CheckResult(
                    check_run_id=run_id,
                    calibration_id=cal.id,
                    protocol_data_id=protocol.id,
                    check_type="completeness",
                    status="ok",
                    comment="Protocol found",
                )
                self.db.add(result)
                results.append(result)

        await self.db.commit()
        return results

    async def _check_protocols_found(self, run_id: int, year: int, month: int) -> list[CheckResult]:
        """Check that all protocols match a calibration."""
        results = []
        protocols = await self.data_repo.get_by_month(year, month)

        for proto in protocols:
            if not proto.serial_number:
                result = CheckResult(
                    check_run_id=run_id,
                    protocol_data_id=proto.id,
                    check_type="protocol_found",
                    status="warning",
                    comment="Protocol has no serial number extracted",
                )
                self.db.add(result)
                results.append(result)
                continue

            serial = self._normalize_serial(proto.serial_number)
            calibration = await self.cal_repo.get_by_serial(serial)

            if not calibration:
                result = CheckResult(
                    check_run_id=run_id,
                    protocol_data_id=proto.id,
                    check_type="protocol_found",
                    status="warning",
                    comment=f"No calibration found for serial: {proto.serial_number}",
                )
                self.db.add(result)
                results.append(result)
            else:
                result = CheckResult(
                    check_run_id=run_id,
                    calibration_id=calibration.id,
                    protocol_data_id=proto.id,
                    check_type="protocol_found",
                    status="ok",
                    comment="Calibration found",
                )
                self.db.add(result)
                results.append(result)

        await self.db.commit()
        return results

    async def _check_data_match(self, run_id: int, year: int, month: int) -> list[CheckResult]:
        """Check that calibration data matches protocol data."""
        from sqlalchemy import select
        from app.models.calibration import Calibration

        results = []
        calibrations = await self.cal_repo.get_by_month(year, month)

        for cal in calibrations:
            serial = self._normalize_serial(cal.mi_number or "")
            protocol = await self.data_repo.get_by_serial(serial)

            if not protocol:
                continue

            # Check verifier
            if cal.verifier and protocol.verifier:
                if cal.verifier.strip().lower() != protocol.verifier.strip().lower():
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="error",
                        comment=f"Verifier mismatch: ARSHIN='{cal.verifier}' vs Protocol='{protocol.verifier}'",
                    )
                    self.db.add(result)
                    results.append(result)

            # Check date
            if cal.verification_date and protocol.verification_date:
                if cal.verification_date != protocol.verification_date:
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="error",
                        comment=f"Date mismatch: ARSHIN={cal.verification_date} vs Protocol={protocol.verification_date}",
                    )
                    self.db.add(result)
                    results.append(result)

            # Check temperature against ARSHIN conditions (allow ±2°C)
            if protocol.temperature is not None:
                if protocol.temperature < -50 or protocol.temperature > 60:
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="warning",
                        comment=f"Temperature out of range: {protocol.temperature}°C",
                    )
                    self.db.add(result)
                    results.append(result)

                cal_temp = self._parse_condition(cal.conditions, "temperature")
                if cal_temp is not None and abs(protocol.temperature - cal_temp) > 2.0:
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="error",
                        comment=f"Temperature mismatch: ARSHIN={cal_temp}°C vs Protocol={protocol.temperature}°C",
                    )
                    self.db.add(result)
                    results.append(result)

            # Check humidity (must be 0-100%)
            if protocol.humidity is not None:
                if protocol.humidity < 0 or protocol.humidity > 100:
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="warning",
                        comment=f"Humidity out of range: {protocol.humidity}%",
                    )
                    self.db.add(result)
                    results.append(result)

            # Check pressure against ARSHIN conditions (allow ±3 kPa)
            if protocol.pressure is not None:
                cal_pressure = self._parse_condition(cal.conditions, "pressure")
                if cal_pressure is not None and abs(protocol.pressure - cal_pressure) > 3.0:
                    result = CheckResult(
                        check_run_id=run_id,
                        calibration_id=cal.id,
                        protocol_data_id=protocol.id,
                        check_type="data_match",
                        status="error",
                        comment=f"Pressure mismatch: ARSHIN={cal_pressure} kPa vs Protocol={protocol.pressure} kPa",
                    )
                    self.db.add(result)
                    results.append(result)

            # If no errors found for this pair
            existing_errors = [r for r in results if r.calibration_id == cal.id and r.protocol_data_id == protocol.id]
            if not existing_errors:
                result = CheckResult(
                    check_run_id=run_id,
                    calibration_id=cal.id,
                    protocol_data_id=protocol.id,
                    check_type="data_match",
                    status="ok",
                    comment="All fields match",
                )
                self.db.add(result)
                results.append(result)

        await self.db.commit()
        return results

    def _parse_condition(self, conditions_json: str | None, field: str) -> float | None:
        """Parse a numeric value from ARSHIN conditions JSON string.

        Handles formats like '20,1°С', '100,9 кПа', '30,0'.
        """
        if not conditions_json:
            return None
        try:
            import json
            cond = json.loads(conditions_json)
        except (json.JSONDecodeError, TypeError):
            return None

        field_map = {
            "temperature": ("conditionsTemperature", "conditions_temperature"),
            "pressure": ("conditionsPressure", "conditions_pressure"),
            "humidity": ("conditionsHymidity", "conditions_hymidity", "conditions_humidity"),
        }
        keys = field_map.get(field, ())
        raw = None
        for key in keys:
            raw = cond.get(key)
            if raw is not None:
                break
        if raw is None:
            return None

        import re
        raw = str(raw).replace(",", ".").replace(" ", "")
        nums = re.findall(r"[-]?\d+\.?\d*", raw)
        return float(nums[0]) if nums else None

    async def run_partial_checks(self, year: int, month: int) -> dict[str, Any]:
        """Run partial checks without LK data (public API + protocols only).
        
        Checks:
        1. All calibrations have protocols
        2. All protocols match a calibration  
        3. Basic data match (serial, date)
        """
        matched = 0
        mismatched = 0
        missing_protocols = 0

        calibrations = await self.cal_repo.get_by_month(year, month)
        protocols = await self.data_repo.get_by_month(year, month)

        # Check 1: completeness (calibration -> protocol)
        all_proto_serials = [self._normalize_serial(p.serial_number or "") for p in protocols if p.serial_number]
        
        for cal in calibrations:
            serial = self._normalize_serial(cal.mi_number or "")
            protocol = await self.data_repo.get_by_serial(serial)
            if protocol:
                matched += 1
            else:
                # Try fuzzy match (handles R vs P, I vs 1, etc.)
                fuzzy_serial = self._fuzzy_match_serial(serial, all_proto_serials)
                if fuzzy_serial:
                    protocol = await self.data_repo.get_by_serial(fuzzy_serial)
                    if protocol:
                        matched += 1
                        continue
                
                # Try MIT number + date as fallback
                if cal.mit_number:
                    import re
                    mit_clean = re.sub(r'[^A-Za-z0-9-]', '', cal.mit_number).strip()
                    if mit_clean:
                        protocol = await self.data_repo.get_by_mit_number(mit_clean, year, month)
                        if protocol:
                            matched += 1
                            continue
                missing_protocols += 1

        # Check 2: protocols found (protocol -> calibration)
        orphan_protocols = 0
        all_cal_serials = [self._normalize_serial(c.mi_number or "") for c in calibrations if c.mi_number]
        
        for proto in protocols:
            if not proto.serial_number:
                orphan_protocols += 1
                continue
            serial = self._normalize_serial(proto.serial_number)
            calibration = await self.cal_repo.get_by_serial(serial)
            if not calibration:
                # Try fuzzy match
                fuzzy_serial = self._fuzzy_match_serial(serial, all_cal_serials)
                if fuzzy_serial:
                    calibration = await self.cal_repo.get_by_serial(fuzzy_serial)
            if not calibration:
                orphan_protocols += 1

        return {
            "matched": matched,
            "mismatched": mismatched,
            "missing_protocols": missing_protocols,
            "orphan_protocols": orphan_protocols,
            "total_calibrations": len(calibrations),
            "total_protocols": len(protocols),
        }

    def _normalize_serial(self, serial: str) -> str:
        """Normalize serial number for comparison (handle homoglyphs, garbage)."""
        import re
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

    def _fuzzy_match_serial(self, serial: str, candidates: list[str]) -> str | None:
        """Fuzzy match serial number against candidates (1 char difference allowed)."""
        if not serial or len(serial) < 3:
            return None
        for candidate in candidates:
            if not candidate or len(candidate) < 3:
                continue
            # Exact match
            if serial == candidate:
                return candidate
            # Same length, 1 char difference (handles R vs P, I vs 1, etc.)
            if len(serial) == len(candidate):
                diff = sum(1 for a, b in zip(serial, candidate) if a != b)
                if diff == 1:
                    return candidate
            # One is prefix of another (e.g., R01194 vs Р01194 after normalization)
            if serial.startswith(candidate) or candidate.startswith(serial):
                return candidate
        return None

    async def _count_calibrations(self, year: int, month: int) -> int:
        from sqlalchemy import func, select
        from app.models.calibration import Calibration
        result = await self.db.execute(
            select(func.count()).select_from(Calibration)
            .where(Calibration.year == year)
            .where(Calibration.month == month)
        )
        return result.scalar() or 0

    async def _count_protocols(self, year: int, month: int) -> int:
        from sqlalchemy import func, select
        from app.models.protocol_file import ProtocolFile
        result = await self.db.execute(
            select(func.count()).select_from(ProtocolFile)
            .where(ProtocolFile.year == year)
            .where(ProtocolFile.month == month)
        )
        return result.scalar() or 0

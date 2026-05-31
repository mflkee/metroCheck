"""Job queue service — manages check execution queue with priorities."""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.arshin_client import ArshinClient
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.services.check_service import CheckService
from app.services.email_service import EmailService
from app.services.task_manager import get_task_manager

logger = logging.getLogger(__name__)


class JobQueueService:
    """Manages prioritized job queue for check runs.
    
    Workflow:
      1. Auto mode: waits for token, then checks previous month non-stop
      2. Manual mode: interrupts auto, runs immediately
      3. After completion: sends email report
      4. If token expires mid-check: waits and resumes
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = JobRepository(db)
        self.email = EmailService()
        self._current_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def enqueue_manual(
        self,
        year: int,
        month: int,
        triggered_by: str = "user",
    ) -> Job:
        """Add manual job with high priority. Cancels auto jobs."""
        pending_auto = await self.repo.list_by_status("pending")
        for job in pending_auto:
            if job.job_type == "auto":
                await self.repo.cancel_job(job.id)
        
        return await self.repo.create(
            year=year,
            month=month,
            job_type="manual",
            priority=10,
            triggered_by=triggered_by,
        )

    async def enqueue_auto(
        self,
        year: int,
        month: int,
        triggered_by: str = "cron",
    ) -> Job:
        """Add automatic job with low priority."""
        return await self.repo.create(
            year=year,
            month=month,
            job_type="auto",
            priority=0,
            triggered_by=triggered_by,
        )

    async def start_worker(self) -> None:
        """Start background worker that processes jobs."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                await self._process_next_job()
            except Exception as e:
                print(f"[JobQueue] Worker error: {e}")
                # Rollback on error to avoid "transaction aborted"
                try:
                    await self.db.rollback()
                except Exception:
                    pass
            await asyncio.sleep(5)

    def stop_worker(self) -> None:
        """Signal worker to stop."""
        self._stop_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def _process_next_job(self) -> None:
        """Pick and run the next highest priority job."""
        running = await self.repo.get_running()
        if running:
            return

        job = await self.repo.get_next_pending()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            result = await self._execute_job(job)
            job.status = "completed"
            job.result_json = json.dumps(result)
            job.progress = "Completed"
            job.progress_percent = 100
            job.processed_devices = job.total_devices
            job.completed_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Send email report
            await self._send_report(job, result)
            return
            
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.progress = "Cancelled"
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            raise
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.progress = f"Failed: {e}"
            job.completed_at = datetime.utcnow()
            try:
                await self.db.commit()
            except Exception:
                try:
                    await self.db.rollback()
                    await self.db.commit()
                except Exception:
                    pass

    async def _execute_job(self, job: Job) -> dict[str, Any]:
        """Execute a single check job with token-independent phases first.

        Phases:
        1. public_api    — Fetch calibrations from public API (no token)
        2. protocol_scan — Scan protocol folder (no token)
        3. protocol_ocr  — Extract text from protocols (no token)
        4. partial_check — Compare protocols with public API (no token)
        5. wait_token    — Wait for LK token (if missing)
        6. lk_api        — Fetch LK details + data2 (needs token)
        7. full_check    — Run full checks with all data
        8. report        — Generate and send report
        """
        tm = get_task_manager()
        task_id = await tm.create(f"job_{job.id}_{job.year}_{job.month}")
        
        from app.services.arshin_service import ArshinService
        from app.services.protocol_scanner import ProtocolScanner
        from app.services.check_service import CheckService
        from app.repositories.protocol_file_repository import ProtocolFileRepository
        
        arshin_service = ArshinService(self.db)
        scanner = ProtocolScanner(self.db, settings.METROCHECK_PROTOCOLS_PATH or "/protocols")
        proto_repo = ProtocolFileRepository(self.db)
        check_service = CheckService(self.db)
        
        stats: dict[str, Any] = {}
        
        # ── Phase 1: Public API ───────────────────────────────────────────
        await self._set_phase(job, "public_api", "Загрузка поверок из АРШИН (public API)...", 5, stats)
        
        cal_result = await arshin_service.fetch_and_save_calibrations(job.year, job.month)
        total_devices = cal_result.get('saved', 0)
        stats["public_api"] = {
            "total": cal_result.get('total', 0),
            "saved": cal_result.get('saved', 0),
            "errors": cal_result.get('errors', 0),
            "status": "completed",
        }
        await self._set_phase(job, "public_api", f"Загружено {cal_result['saved']} поверок", 20, stats, total_devices=total_devices)

        # ── Phase 2: Protocol Scan ────────────────────────────────────────
        await self._set_phase(job, "protocol_scan", "Сканирование папки протоколов...", 25, stats)
        
        scan_result = await scanner.scan(job.year, job.month)
        stats["protocol_scan"] = {
            "found": scan_result.get('found', 0),
            "saved": scan_result.get('saved', 0),
            "errors": scan_result.get('errors', 0),
            "status": "completed",
        }
        await self._set_phase(job, "protocol_scan", f"Найдено {scan_result.get('found', 0)} файлов", 30, stats)

        # ── Phase 3: Protocol OCR ─────────────────────────────────────────
        await self._set_phase(job, "protocol_ocr", "Извлечение текста из протоколов...", 35, stats)
        
        protocols = await proto_repo.get_by_month(job.year, job.month)
        extracted_count = 0
        ocr_errors = 0
        total = len(protocols)
        
        # Process protocols sequentially (avoid DB connection conflicts)
        for idx, proto in enumerate(protocols):
            try:
                await scanner.extract_text(proto.id)
                extracted_count += 1
            except Exception as e:
                ocr_errors += 1
                logger.warning("OCR failed for protocol %s: %s", proto.id, e)
            
            # Update progress every 5 files
            if idx % 5 == 0 or idx == total - 1:
                pct = 35 + int((idx + 1) / total * 15)
                await self._set_phase(job, "protocol_ocr", f"OCR: {idx + 1}/{total}...", min(pct, 50), stats)
        
        stats["protocol_ocr"] = {
            "total": total,
            "extracted": extracted_count,
            "errors": ocr_errors,
            "status": "completed",
        }
        await self._set_phase(job, "protocol_ocr", f"OCR завершено: {extracted_count}/{total}", 50, stats)

        # ── Phase 4: Extract basic data (fast regex) ───────────────────────
        await self._set_phase(job, "data_extract", "Извлечение данных из протоколов...", 50, stats)
        
        from app.repositories.protocol_data_repository import ProtocolDataRepository
        import re
        
        from app.models.protocol_data import ProtocolData
        
        extracted = 0
        extract_errors = 0
        
        # Re-fetch protocols to get updated status after OCR
        protocols = await proto_repo.get_by_month(job.year, job.month)
        
        # Get protocols that have been scanned but not yet have data
        scanned_protocols = [p for p in protocols if p.status == "scanned"]
        
        for idx, proto in enumerate(scanned_protocols):
            try:
                # Use raw_text from protocol_file (already extracted during OCR)
                text = proto.raw_text or ""
                if not text or len(text) < 50:
                    extract_errors += 1
                    continue
                
                # Extract all protocol data with regex (fast, no AI needed)
                extracted_data = self._extract_protocol_data(text)
                
                if extracted_data.get('serial_number'):
                    # Create protocol_data object with all extracted fields
                    data = ProtocolData(
                        protocol_file_id=proto.id,
                        protocol_number=extracted_data.get('protocol_number'),
                        device_name=extracted_data.get('device_name'),
                        device_type=extracted_data.get('device_type'),
                        serial_number=extracted_data.get('serial_number'),
                        mit_number=extracted_data.get('mit_number'),
                        manufacture_year=extracted_data.get('manufacture_year'),
                        owner=extracted_data.get('owner'),
                        verification_date=extracted_data.get('verification_date'),
                        verifier=extracted_data.get('verifier'),
                        temperature=extracted_data.get('temperature'),
                        humidity=extracted_data.get('humidity'),
                        pressure=extracted_data.get('pressure'),
                        result=extracted_data.get('result'),
                        verification_method=extracted_data.get('verification_method'),
                        raw_text=text[:10000],
                        status="manual_review",
                        model_used="regex",
                    )
                    self.db.add(data)
                    extracted += 1
                else:
                    extract_errors += 1
                    
            except Exception as e:
                extract_errors += 1
                logger.warning("Data extraction failed for protocol %s: %s", proto.id, e)
            
            # Update progress
            if idx % 2 == 0 or idx == len(scanned_protocols) - 1:
                pct = 50 + int((idx + 1) / max(len(scanned_protocols), 1) * 5)
                await self._set_phase(job, "data_extract", f"Обработано: {idx + 1}/{len(scanned_protocols)} протоколов...", min(pct, 55), stats)
        
        stats["data_extract"] = {
            "total": len(scanned_protocols),
            "extracted": extracted,
            "errors": extract_errors,
            "status": "completed",
        }
        await self._set_phase(job, "data_extract", f"Извлечено: {extracted}/{len(scanned_protocols)}", 55, stats)

        # ── Phase 5: Partial Checks (no token) ────────────────────────────
        await self._set_phase(job, "partial_check", "Частичная проверка (public API + протоколы)...", 55, stats)
        
        partial_result = await check_service.run_partial_checks(job.year, job.month)
        stats["partial_check"] = {
            "matched": partial_result.get('matched', 0),
            "mismatched": partial_result.get('mismatched', 0),
            "missing_protocols": partial_result.get('missing_protocols', 0),
            "status": "completed",
        }
        await self._set_phase(job, "partial_check", f"Частичная проверка: {partial_result.get('matched', 0)} совпадений", 57, stats)

        # ── Phase 5: Wait for token ───────────────────────────────────────
        client = ArshinClient()
        if not client.bearer_token:
            await self._set_phase(job, "wait_token", "Ожидание токена ЛК АРШИН...", 55, stats)
            await self._wait_for_token(job, client)
            stats["wait_token"] = {"status": "completed", "waited": True}
        else:
            stats["wait_token"] = {"status": "completed", "waited": False}

        # ── Phase 6: LK API ───────────────────────────────────────────────
        await self._set_phase(job, "lk_api", "Загрузка данных из ЛК АРШИН...", 60, stats)
        
        lk_result = await arshin_service.fetch_lk_details(job.year, job.month)
        stats["lk_details"] = {
            "total": lk_result.get('total', 0),
            "updated": lk_result.get('updated', 0),
            "errors": lk_result.get('errors', 0),
            "status": "completed",
        }
        await self._set_phase(job, "lk_api", f"ЛК детали: {lk_result['updated']} записей", 70, stats, processed_devices=total_devices // 3)

        await self._set_phase(job, "lk_api", "Загрузка расширенных данных...", 75, stats)
        
        data2_result = await arshin_service.fetch_lk_data2(job.year, job.month)
        stats["lk_data2"] = {
            "total": data2_result.get('total', 0),
            "updated": data2_result.get('updated', 0),
            "errors": data2_result.get('errors', 0),
            "status": "completed",
        }
        await self._set_phase(job, "lk_api", f"Расширенные данные: {data2_result['updated']} записей", 80, stats, processed_devices=total_devices * 2 // 3)

        # ── Phase 7: Full Checks ──────────────────────────────────────────
        await self._set_phase(job, "full_check", "Полная проверка с данными ЛК...", 85, stats)
        
        check_result = await check_service.run_checks(job.year, job.month)
        if check_result.get("run_id"):
            job.check_run_id = check_result["run_id"]
        
        stats["full_check"] = {
            "errors": check_result.get('errors', 0),
            "warnings": check_result.get('warnings', 0),
            "missing": check_result.get('missing', 0),
            "status": "completed",
        }
        await self._set_phase(job, "full_check", f"Проверка: {check_result.get('errors', 0)} ошибок, {check_result.get('warnings', 0)} предупр.", 95, stats, processed_devices=total_devices)

        # ── Phase 8: Report ───────────────────────────────────────────────
        await self._set_phase(job, "report", "Формирование отчета...", 98, stats)
        
        final_result = {
            "public_api": cal_result,
            "protocol_scan": scan_result,
            "protocol_ocr": {"extracted": extracted_count, "errors": ocr_errors},
            "partial_check": partial_result,
            "lk_details": lk_result,
            "lk_data2": data2_result,
            "full_check": check_result,
        }
        
        stats["report"] = {"status": "completed"}
        await self._set_phase(job, "report", "Готово!", 100, stats)
        
        return final_result

    async def _set_phase(
        self,
        job: Job,
        phase: str,
        progress: str,
        percent: int,
        stats: dict,
        total_devices: Optional[int] = None,
        processed_devices: Optional[int] = None,
    ) -> None:
        """Update job phase and stats."""
        stats_json = json.dumps(stats, ensure_ascii=False, default=str)
        await self.repo.update_status(
            job.id,
            status="running",
            progress=progress,
            progress_percent=percent,
            phase_stats=stats_json,
            current_phase=phase,
            total_devices=total_devices if total_devices is not None else job.total_devices,
            processed_devices=processed_devices if processed_devices is not None else job.processed_devices,
        )

    @staticmethod
    def _extract_protocol_data(text: str) -> dict:
        """Extract all relevant data from protocol text using regex."""
        import re
        
        result = {}
        
        # 1. Serial number - specific patterns first
        serial_patterns = [
            r'заводской\s+номер[:\s]+(\S+)',  # "Заводской номер: 21148561"
            r'серийный\s+номер[:\s]+(\S+)',  # "Серийный номер: 21148561"
            r'зав\.\s*№\s*(\S+)',  # "зав. № 21148561"
            r'№\s*(\d{3,})',  # "№ 21148561" (at least 3 digits)
        ]
        
        for pattern in serial_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                serial = match.group(1).strip()
                serial = re.sub(r'[.,;]$', '', serial)
                # Exclude common false positives
                false_positives = {'записи', 'аккредитации', 'аттестации', 'реестре', 'действительно'}
                if len(serial) >= 3 and serial.lower() not in false_positives:
                    result['serial_number'] = serial
                    break
        
        # 2. Protocol number
        proto_match = re.search(r'протокол\s+поверки\s+№\s*([\d/]+)', text, re.IGNORECASE)
        if proto_match:
            result['protocol_number'] = proto_match.group(1).strip()
        
        # 3. Device name
        device_name_match = re.search(r'наименование\s+средства\s+измерений[:\s]+([^\n]+)', text, re.IGNORECASE)
        if device_name_match:
            result['device_name'] = device_name_match.group(1).strip()
        
        # 3.5 Verification method (методика поверки)
        method_match = re.search(r'Методика\s+поверки\s+([МП]\s+[\d-]+)', text, re.IGNORECASE)
        if method_match:
            result['verification_method'] = method_match.group(1).strip()
        else:
            # Fallback: try to find any MP pattern
            mp_match = re.search(r'(?:^|\s)(МП\s+[\d-]+)', text, re.IGNORECASE)
            if mp_match:
                result['verification_method'] = mp_match.group(1).strip()
        
        # 4. Device type/modification
        type_match = re.search(r'тип[,:]?\s+модификация.*?[:\n]([^\n]+)', text, re.IGNORECASE)
        if type_match:
            result['device_type'] = type_match.group(1).strip()
        
        # 4. MIT number
        mit_match = re.search(r'номер\s+в\s+государственном\s+реестре\s+си[:\s]+(\S+)', text, re.IGNORECASE)
        if mit_match:
            result['mit_number'] = mit_match.group(1).strip()
        
        # 5. Verification date
        date_patterns = [
            r'протокол\s+поверки\s+№\s+\S+\s+от\s+(\d{2}\.\d{2}\.\d{4})',
            r'дата\s+поверки[:\s]+(\d{2}\.\d{2}\.\d{4})',
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, text, re.IGNORECASE)
            if date_match:
                try:
                    from datetime import datetime
                    result['verification_date'] = datetime.strptime(date_match.group(1), '%d.%m.%Y').date()
                    break
                except ValueError:
                    pass
        
        # 6. Manufacture year
        year_match = re.search(r'год\s+выпуска[:\s]+(\d{4})', text, re.IGNORECASE)
        if year_match:
            result['manufacture_year'] = int(year_match.group(1))
        
        # 7. Owner
        owner_match = re.search(r'владелец\s+средства\s+измерений[:\n]([^\n]+)', text, re.IGNORECASE)
        if owner_match:
            result['owner'] = owner_match.group(1).strip()
        
        # 8. Verifier (поверитель)
        # Handle cases with signature lines between label and name
        verifier_patterns = [
            # Pattern 1: Поверитель: Name (on same or next line)
            r'поверитель[:_\s]*\n?[_\s]*([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?)',
            # Pattern 2: Look for Ф.И.О label after Поверитель
            r'поверитель.*?Ф\.И\.О\s*\n?[_\s]*([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?)',
            # Pattern 3: Direct line after Поверитель (with underscores/signatures)
            r'поверитель[:\s]*\n[_\s]+\n?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?)',
            # Pattern 4: Simple pattern
            r'поверитель[:\s]+([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?)',
            # Pattern 5: Name with signature placeholder
            r'поверитель[:_\s]+([А-ЯЁ][а-яё]+)',
        ]
        for pattern in verifier_patterns:
            verifier_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if verifier_match:
                verifier = verifier_match.group(1).strip()
                # Clean up underscores and whitespace
                verifier = re.sub(r'[_\s]+$', '', verifier)
                if len(verifier) >= 3:
                    result['verifier'] = verifier
                    break
        
        # 9. Temperature
        temp_match = re.search(r'температура\s+окружающего\s+воздуха[^\d]*(\d+[.,]?\d*)', text, re.IGNORECASE)
        if temp_match:
            result['temperature'] = float(temp_match.group(1).replace(',', '.'))
        
        # 9. Humidity
        hum_match = re.search(r'относительная\s+влажность[^\d]*(\d+[.,]?\d*)', text, re.IGNORECASE)
        if hum_match:
            result['humidity'] = float(hum_match.group(1).replace(',', '.'))
        
        # 10. Pressure
        press_match = re.search(r'атмосферное\s+давление[^\d]*(\d+[.,]?\d*)', text, re.IGNORECASE)
        if press_match:
            result['pressure'] = float(press_match.group(1).replace(',', '.'))
        
        # 11. Result
        if 'пригоден' in text.lower() or 'соответствует' in text.lower():
            result['result'] = 'пригоден'
        elif 'непригоден' in text.lower():
            result['result'] = 'непригоден'
        
        return result

    async def _wait_for_token(self, job: Job, client: ArshinClient) -> None:
        """Wait for token and update job status."""
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Токен истёк! Ожидание нового токена от Зонова...",
            progress_percent=job.progress_percent,
        )
        job.waiting_for_token = True
        await self.db.commit()
        
        await client._request_new_token()
        
        job.waiting_for_token = False
        await self.db.commit()
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Токен получен, продолжение работы...",
            progress_percent=job.progress_percent,
        )

    async def _send_report(self, job: Job, result: dict[str, Any]) -> None:
        """Send email report after completion."""
        checks = result.get("checks", {})
        
        # Read report_email from scheduler state
        report_email = None
        try:
            import json
            state_file = os.environ.get("SCHEDULER_STATE", "/tmp/scheduler_state.json")
            if os.path.exists(state_file):
                with open(state_file) as f:
                    state = json.load(f)
                    report_email = state.get("report_email") or None
        except Exception:
            pass
        
        await self.email.send_check_report(
            year=job.year,
            month=job.month,
            total_devices=job.total_devices,
            errors=checks.get("errors", 0),
            warnings=checks.get("warnings", 0),
            missing=checks.get("missing", 0),
            check_run_id=job.check_run_id or 0,
            report_url=f"http://100.89.59.195:8002/api/v1/checks/results/{job.check_run_id}" if job.check_run_id else None,
            recipient_email=report_email,
        )
        
        job.email_sent = True
        await self.db.commit()

    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a pending or running job."""
        job = await self.repo.get_by_id(job_id)
        if not job:
            return False
        
        if job.status == "running" and self._current_task:
            self._current_task.cancel()
        
        return await self.repo.cancel_job(job_id)

    async def pause_job(self, job_id: int) -> bool:
        """Pause a pending job."""
        return await self.repo.pause_job(job_id)

    async def resume_job(self, job_id: int) -> bool:
        """Resume a paused job."""
        return await self.repo.resume_job(job_id)

    async def get_queue_status(self) -> dict[str, Any]:
        """Get current queue status with device progress."""
        running = await self.repo.get_running()
        pending = await self.repo.list_by_status("pending")
        paused = await self.repo.list_by_status("paused")
        recent = await self.repo.list_all(limit=10)
        
        return {
            "running": self._job_to_dict(running) if running else None,
            "pending": [self._job_to_dict(j) for j in pending],
            "paused": [self._job_to_dict(j) for j in paused],
            "recent": [self._job_to_dict(j) for j in recent],
        }

    @staticmethod
    def _job_to_dict(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "year": job.year,
            "month": job.month,
            "job_type": job.job_type,
            "status": job.status,
            "priority": job.priority,
            "progress": job.progress,
            "progress_percent": job.progress_percent,
            "total_devices": job.total_devices,
            "processed_devices": job.processed_devices,
            "current_device": job.current_device,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "triggered_by": job.triggered_by,
            "check_run_id": job.check_run_id,
            "error_message": job.error_message,
            "waiting_for_token": job.waiting_for_token,
            "email_sent": job.email_sent,
            "phase_stats": job.phase_stats,
            "current_phase": job.current_phase,
        }


_queue_service: Optional[JobQueueService] = None


def get_queue_service(db: AsyncSession) -> JobQueueService:
    return JobQueueService(db)

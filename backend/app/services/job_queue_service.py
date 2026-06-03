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
        
        # Clean up stale "running" jobs left over from a restart
        try:
            stale = await self.repo.list_by_status("running")
            for s in stale:
                s.status = "failed"
                s.error_message = "Backend restart — job was left in running state"
                s.progress = "Отменено после перезапуска"
                s.completed_at = datetime.utcnow()
                logger.warning("Marked stale running job #%d as failed", s.id)
            if stale:
                await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                pass
        
        while not self._stop_event.is_set():
            try:
                processed = await self._process_next_job()
                # Sleep between polls to avoid hammering the database
                if not processed:
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                logger.warning("Job cancelled, continuing...")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error("Worker error: %s", e)
                # Rollback on error to avoid "transaction aborted"
                try:
                    await self.db.rollback()
                except Exception:
                    pass
                # Recreate session if corrupted
                try:
                    await self.db.close()
                except Exception:
                    pass
                from app.core.database import AsyncSessionLocal
                from app.repositories.job_repository import JobRepository
                self.db = AsyncSessionLocal()
                self.repo = JobRepository(self.db)
                await asyncio.sleep(5)

    def stop_worker(self) -> None:
        """Signal worker to stop."""
        self._stop_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def _process_next_job(self) -> bool:
        """Pick and run the next highest priority job.

        Returns True if a job was processed, False otherwise.
        """
        running = await self.repo.get_running()
        if running:
            return False

        job = await self.repo.get_next_pending()
        if not job:
            return False

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        task = asyncio.create_task(self._execute_job(job))
        self._current_task = task

        try:
            result = await task
            self._current_task = None
            job.status = "completed"
            job.result_json = json.dumps(result)
            job.progress = "Completed"
            job.progress_percent = 100
            job.processed_devices = job.total_devices
            job.completed_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Send email report
            await self._send_report(job, result)
            return True
            
        except asyncio.CancelledError:
            self._current_task = None
            job.status = "cancelled"
            job.progress = "Cancelled"
            job.completed_at = datetime.utcnow()
            try:
                await self.db.commit()
            except Exception:
                # Session corrupted — recreate and re-save
                try:
                    await self.db.rollback()
                    await self.db.close()
                except Exception:
                    pass
                from app.core.database import AsyncSessionLocal
                from app.repositories.job_repository import JobRepository
                self.db = AsyncSessionLocal()
                self.repo = JobRepository(self.db)
                fresh_job = await self.repo.get_by_id(job.id)
                if fresh_job:
                    fresh_job.status = "cancelled"
                    fresh_job.progress = "Cancelled"
                    fresh_job.completed_at = datetime.utcnow()
                    await self.db.commit()
            raise
        except Exception as e:
            self._current_task = None
            try:
                await self.db.rollback()
            except Exception:
                pass
            
            # Recreate session in case it was corrupted by task cancellation
            # (greenlet_spawn error) — a single shared session is used for all jobs
            try:
                await self.db.close()
            except Exception:
                pass
            from app.core.database import AsyncSessionLocal
            from app.repositories.job_repository import JobRepository
            self.db = AsyncSessionLocal()
            self.repo = JobRepository(self.db)
            
            # Re-attach and update job in the new session
            fresh_job = await self.repo.get_by_id(job.id)
            if fresh_job:
                fresh_job.status = "failed"
                fresh_job.error_message = str(e)
                fresh_job.progress = f"Failed: {e}"
                fresh_job.completed_at = datetime.utcnow()
            else:
                # Fallback: re-add the detached object
                job.status = "failed"
                job.error_message = str(e)
                job.progress = f"Failed: {e}"
                job.completed_at = datetime.utcnow()
                self.db.add(job)
            
            try:
                await self.db.commit()
            except Exception:
                try:
                    await self.db.rollback()
                    await self.db.commit()
                except Exception:
                    pass
            return True

    async def _check_cancelled(self, job_id: int) -> None:
        """Check if job was cancelled externally and raise CancelledError."""
        job = await self.repo.get_by_id(job_id)
        if job and job.status == "cancelled":
            raise asyncio.CancelledError()

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
        
        await self._check_cancelled(job.id)
        
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
        await self._set_phase(job, "protocol_scan", "Подсчёт файлов...", 24, stats)
        await self._check_cancelled(job.id)
        
        async def _on_scan_progress(done: int, total: int) -> None:
            pct = min(25 + int(done / max(total, 1) * 5), 29)
            msg = f"Сканирование: {done}/{total} файлов..."
            await self._set_phase(job, "protocol_scan", msg, pct, stats)
        
        scan_result = await scanner.scan(job.year, job.month, progress_callback=_on_scan_progress)
        stats["protocol_scan"] = {
            "found": scan_result.get('found', 0),
            "saved": scan_result.get('saved', 0),
            "errors": scan_result.get('errors', 0),
            "status": "completed",
        }
        await self._set_phase(job, "protocol_scan", f"Найдено {scan_result.get('found', 0)} файлов", 30, stats)

        # ── Phase 3: Protocol OCR ─────────────────────────────────────────
        await self._set_phase(job, "protocol_ocr", "Извлечение текста из протоколов...", 35, stats)
        await self._check_cancelled(job.id)
        
        protocols = await proto_repo.get_by_month(job.year, job.month)
        extracted_count = 0
        ocr_errors = 0
        # Only process files that haven't been scanned yet
        needs_ocr = [p for p in protocols if p.status != "scanned"]
        total = len(needs_ocr)
        skipped = len(protocols) - total
        
        for idx, proto in enumerate(needs_ocr):
            try:
                await asyncio.wait_for(scanner.extract_text(proto.id), timeout=120.0)
                extracted_count += 1
            except asyncio.TimeoutError:
                ocr_errors += 1
                logger.warning("OCR timeout for protocol %s", proto.id)
            except Exception as e:
                ocr_errors += 1
                logger.warning("OCR failed for protocol %s: %s", proto.id, e)
            
            # Update progress every 5 files
            if idx % 5 == 0 or idx == total - 1:
                pct = 35 + int((idx + 1) / max(total, 1) * 15)
                await self._set_phase(job, "protocol_ocr", f"OCR: {idx + 1}/{total}...", min(pct, 50), stats)
        
        stats["protocol_ocr"] = {
            "total": total,
            "extracted": extracted_count,
            "errors": ocr_errors,
            "skipped": skipped,
            "status": "completed",
        }
        await self._set_phase(job, "protocol_ocr", f"OCR: {extracted_count}/{total} обработано", 50, stats)

        # ── Phase 4: Extract data via AI ────────────────────────────────
        await self._set_phase(job, "data_extract", "Извлечение данных из протоколов через AI...", 50, stats)
        await self._check_cancelled(job.id)

        from app.repositories.protocol_data_repository import ProtocolDataRepository
        from app.services.smart_extractor import get_smart_extractor

        from app.models.protocol_data import ProtocolData

        proto_data_repo = ProtocolDataRepository(self.db)
        extraction_service = get_smart_extractor()
        extracted = 0
        extract_errors = 0

        # Re-fetch protocols to get updated status after OCR
        protocols = await proto_repo.get_by_month(job.year, job.month)

        # Get protocols that have been scanned but not yet have data
        scanned_protocols = [p for p in protocols if p.status == "scanned"]
        logger.info("[DEBUG] data_extract: %d scanned protocols", len(scanned_protocols))

        for idx, proto in enumerate(scanned_protocols):
            try:
                text = proto.raw_text or ""
                if not text or len(text) < 50:
                    logger.info("[DEBUG] Protocol %s: text too short (%d), skipping", proto.id, len(text))
                    extract_errors += 1
                    continue

                logger.info("[DEBUG] Protocol %s: starting extraction", proto.id)
                # Use multi-pass extraction with validation
                ai_result = await extraction_service.extract(text)
                logger.info("[DEBUG] Protocol %s: extraction done, status=%s", proto.id, ai_result.get("status"))
                extracted_data = ai_result.get("content") or {}

                if extracted_data.get('serial_number'):
                    verification_date = None
                    vd = extracted_data.get('verification_date')
                    if vd:
                        try:
                            from datetime import datetime
                            verification_date = datetime.strptime(vd, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass

                    temperature = extracted_data.get('temperature')
                    if temperature is not None:
                        temperature = float(str(temperature).replace(',', '.').split()[0].replace('°C', '').replace('C', ''))

                    humidity = extracted_data.get('humidity')
                    if humidity is not None:
                        humidity = float(str(humidity).replace('%', '').replace(',', '.').split()[0])

                    pressure = extracted_data.get('pressure')
                    if pressure is not None:
                        pressure = float(str(pressure).replace(',', '.').split()[0])

                    manufacture_year = extracted_data.get('manufacture_year')
                    if manufacture_year is not None:
                        try:
                            manufacture_year = int(manufacture_year)
                        except (ValueError, TypeError):
                            manufacture_year = None

                    fields = dict(
                        protocol_number=extracted_data.get('protocol_number'),
                        device_name=extracted_data.get('device_name'),
                        device_type=extracted_data.get('device_type'),
                        serial_number=extracted_data.get('serial_number'),
                        mit_number=extracted_data.get('mit_number'),
                        manufacture_year=manufacture_year,
                        owner=extracted_data.get('owner'),
                        verification_date=verification_date,
                        verifier=extracted_data.get('verifier'),
                        temperature=temperature,
                        humidity=humidity,
                        pressure=pressure,
                        result=extracted_data.get('result'),
                        verification_method=extracted_data.get('verification_method'),
                        measurement_range=extracted_data.get('measurement_range'),
                        raw_text=text[:10000],
                        status=ai_result.get("status") or "manual_review",
                        model_used=ai_result.get("model") or "unknown",
                        confidence=ai_result.get("confidence") or 0.0,
                        cost=ai_result.get("cost") or 0.0,
                        attempts=ai_result.get("attempts") or 0,
                        pressure_units=extracted_data.get("pressure_units"),
                    )
                    existing = await proto_data_repo.get_by_protocol_file_id(proto.id)
                    if existing:
                        for key, value in fields.items():
                            setattr(existing, key, value)
                        extracted += 1
                    else:
                        data = ProtocolData(protocol_file_id=proto.id, **fields)
                        self.db.add(data)
                        extracted += 1
                else:
                    extract_errors += 1

            except Exception as e:
                extract_errors += 1
                logger.warning("AI extraction failed for protocol %s: %s", proto.id, e)

            logger.info("[DEBUG] Protocol %s: before _set_phase in loop", proto.id)
            if idx % 2 == 0 or idx == len(scanned_protocols) - 1:
                pct = 50 + int((idx + 1) / max(len(scanned_protocols), 1) * 5)
                await self._set_phase(job, "data_extract", f"AI: {idx + 1}/{len(scanned_protocols)} протоколов...", min(pct, 55), stats)
            logger.info("[DEBUG] Protocol %s: after _set_phase in loop", proto.id)

        logger.info("[DEBUG] data_extract loop done, extracted=%d, errors=%d", extracted, extract_errors)
        stats["data_extract"] = {
            "total": len(scanned_protocols),
            "extracted": extracted,
            "errors": extract_errors,
            "status": "completed",
        }
        logger.info("[DEBUG] Before final data_extract _set_phase")
        await self._set_phase(job, "data_extract", f"AI извлeчeно: {extracted}/{len(scanned_protocols)}", 55, stats)
        logger.info("[DEBUG] After final data_extract _set_phase")

        # ── Phase 5: Partial Checks (no token) ────────────────────────────
        logger.info("[DEBUG] Before partial_check _set_phase")
        await self._set_phase(job, "partial_check", "Частичная проверка (public API + протоколы)...", 55, stats)
        logger.info("[DEBUG] After partial_check _set_phase")
        await self._check_cancelled(job.id)
        
        logger.info("[DEBUG] Before run_partial_checks")
        partial_result = await check_service.run_partial_checks(job.year, job.month)
        logger.info("[DEBUG] After run_partial_checks: %s", partial_result)
        stats["partial_check"] = {
            "matched": partial_result.get('matched', 0),
            "mismatched": partial_result.get('mismatched', 0),
            "missing_protocols": partial_result.get('missing_protocols', 0),
            "status": "completed",
        }
        await self._set_phase(job, "partial_check", f"Частичная проверка: {partial_result.get('matched', 0)} совпадений", 57, stats)

        # ── Phase 5: Wait for token ───────────────────────────────────────
        await self._check_cancelled(job.id)
        client = ArshinClient()
        if not client.bearer_token:
            await self._set_phase(job, "wait_token", "Ожидание токена ЛК АРШИН...", 55, stats)
            await self._wait_for_token(job, client)
            stats["wait_token"] = {"status": "completed", "waited": True}
        else:
            stats["wait_token"] = {"status": "completed", "waited": False}

        # ── Phase 6: LK API ───────────────────────────────────────────────
        await self._set_phase(job, "lk_api", "Загрузка данных из ЛК АРШИН...", 60, stats)
        await self._check_cancelled(job.id)
        
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
        await self._check_cancelled(job.id)
        
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
        await self._check_cancelled(job.id)
        
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

    async def _wait_for_token(self, job: Job, client: ArshinClient) -> None:
        """Wait for token and update job status."""
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Токен ЛК Аршин истек",
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
            from app.repositories.email_repository import EmailRepository
            repo = EmailRepository(self.db)
            entries = await repo.get_all()
            if entries:
                report_email = ", ".join(e.email for e in entries)
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
            report_url=f"http://100.89.59.195:8081/" if job.check_run_id else None,
            recipient_email=report_email,
        )
        
        job.email_sent = True
        await self.db.commit()

    async def cancel_job(self, job_id: int, db: Optional[AsyncSession] = None) -> bool:
        """Cancel a pending or running job."""
        from app.repositories.job_repository import JobRepository
        repo = JobRepository(db or self.db)
        job = await repo.get_by_id(job_id)
        if not job:
            return False
        
        if job.status == "running":
            if self._current_task:
                self._current_task.cancel()
            job.status = "cancelled"
            job.progress = "Cancelled"
            job.completed_at = datetime.utcnow()
            await (db or self.db).commit()
            return True
        
        if job.status == "pending":
            return await repo.cancel_job(job_id)
        
        return False

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


_queue_service_instance: Optional[JobQueueService] = None


def get_queue_service(db: Optional[AsyncSession] = None) -> JobQueueService:
    global _queue_service_instance
    if _queue_service_instance is not None:
        return _queue_service_instance
    if db is None:
        raise RuntimeError("Queue service not initialized. Call init_queue_service(db) first.")
    _queue_service_instance = JobQueueService(db)
    return _queue_service_instance


def init_queue_service(db: AsyncSession) -> JobQueueService:
    global _queue_service_instance
    _queue_service_instance = JobQueueService(db)
    return _queue_service_instance

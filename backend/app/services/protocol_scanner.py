"""ProtocolScanner — сканирование PDF/JPG/PNG протоколов с OCR."""

import asyncio
import hashlib
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_file import ProtocolFile
from app.repositories.protocol_file_repository import ProtocolFileRepository

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_EXTENSIONS = {".pdf"} | IMAGE_EXTENSIONS


def _extract_text_process(file_path: str, queue: Any) -> None:
    """Top-level helper for multiprocessing — runs in a separate process."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in IMAGE_EXTENSIONS:
            with Image.open(file_path) as img:
                full_text = pytesseract.image_to_string(img, lang="rus+eng")
            pages = 1
        else:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            full_text = "\n".join(text_parts)
            pages = len(text_parts)
            if not full_text.strip():
                images = convert_from_path(file_path)
                pages = len(images)
                ocr_parts = [pytesseract.image_to_string(img, lang="rus+eng") for img in images]
                full_text = "\n".join(ocr_parts)
        queue.put({"text": full_text, "pages": pages, "error": None})
    except Exception as e:
        queue.put({"error": str(e), "text": "", "pages": 0})


class ProtocolScanner:
    """Scan protocol folders and extract text from PDFs and images (OCR)."""

    def __init__(self, db: AsyncSession, protocols_base_path: str) -> None:
        self.db = db
        self.base_path = protocols_base_path
        self.repo = ProtocolFileRepository(db)

    def _get_target_folder(self, year: int, month: int) -> str:
        """Build path: base/year/month."""
        return os.path.join(self.base_path, str(year), f"{month:02d}")

    def _calculate_sha256(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_creation_time(self, file_path: str) -> datetime | None:
        """Get file creation time."""
        try:
            stat = os.stat(file_path)
            if os.name == "nt":
                return datetime.fromtimestamp(stat.st_ctime)
            else:
                return datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime))
        except Exception:
            return None

    async def scan(
        self, year: int, month: int,
        progress_callback: Callable | None = None,
    ) -> dict[str, Any]:
        """Scan folder for protocol files (PDF/JPG/PNG) and save to DB.

        Args:
            year: year to scan
            month: month to scan
            progress_callback: async callable(done, total) for progress

        Returns:
            dict with found, saved, errors counts
        """
        target_folder = self._get_target_folder(year, month)

        if not os.path.exists(target_folder):
            return {
                "found": 0,
                "saved": 0,
                "errors": 0,
                "path": target_folder,
                "message": "Folder does not exist",
            }

        # Quick pre-scan to count total files
        total = 0
        for _root, _dirs, files in os.walk(target_folder):
            for file in files:
                if os.path.splitext(file)[1].lower() in SUPPORTED_EXTENSIONS:
                    total += 1

        found = 0
        saved = 0
        errors = 0

        for root, _dirs, files in os.walk(target_folder):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.base_path)
                found += 1

                try:
                    existing = await self.repo.get_by_path(relative_path)
                    if existing:
                        if progress_callback:
                            await progress_callback(found, total)
                        continue

                    size = os.path.getsize(file_path)
                    sha256 = self._calculate_sha256(file_path)
                    creation_time = self._get_creation_time(file_path)

                    protocol_file = ProtocolFile(
                        file_name=file,
                        file_path=file_path,
                        relative_path=relative_path,
                        year=year,
                        month=month,
                        size_bytes=size,
                        sha256_hash=sha256,
                    )
                    self.db.add(protocol_file)
                    await self.db.commit()
                    await self.db.refresh(protocol_file)
                    saved += 1

                except Exception:
                    errors += 1
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass

                if progress_callback:
                    await progress_callback(found, total)

        return {
            "found": found,
            "saved": saved,
            "errors": errors,
            "path": target_folder,
        }

    def extract_text_sync(self, file_path: str) -> dict[str, Any]:
        """Pure synchronous text extraction from file (no DB, no async)."""
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext in IMAGE_EXTENSIONS:
                with Image.open(file_path) as img:
                    full_text = pytesseract.image_to_string(img, lang="rus+eng")
                pages = 1
            else:
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                full_text = "\n".join(text_parts)
                pages = len(text_parts)
                if not full_text.strip():
                    images = convert_from_path(file_path)
                    pages = len(images)
                    ocr_parts = [pytesseract.image_to_string(img, lang="rus+eng") for img in images]
                    full_text = "\n".join(ocr_parts)

            return {
                "text": full_text,
                "pages": pages,
                "error": None,
            }

        except Exception as e:
            return {"error": str(e), "text": "", "pages": 0}

    async def extract_text(self, protocol_file_id: int, timeout: float = 30.0) -> dict[str, Any]:
        """Extract text from protocol file with real timeout via ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor

        # Shield DB operations so cancellation doesn't corrupt greenlet state
        protocol = await asyncio.shield(self.repo.get_by_id(protocol_file_id))
        if not protocol:
            return {"error": "Protocol not found"}

        # Skip OCR if text already extracted
        if protocol.raw_text and len(protocol.raw_text) > 50:
            protocol.status = "scanned"
            await asyncio.shield(self.db.commit())
            return {
                "protocol_id": protocol_file_id,
                "text": protocol.raw_text,
                "pages": 0,
            }

        # ThreadPool with multiple workers so one hung PDF doesn't block others
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=5) as executor:
            future = executor.submit(self.extract_text_sync, protocol.file_path)
            try:
                result = await asyncio.wait_for(
                    asyncio.wrap_future(future),
                    timeout=timeout,
                )
            except TimeoutError:
                # Cancel the future (thread will finish eventually but won't block)
                future.cancel()
                protocol.status = "error"
                protocol.raw_text = f"OCR timeout (>{int(timeout)}s)"
                await asyncio.shield(self.db.commit())
                return {
                    "protocol_id": protocol_file_id,
                    "error": f"OCR timeout (>{int(timeout)}s)",
                }

        if result.get("error"):
            protocol.status = "error"
        else:
            protocol.status = "scanned"
            protocol.raw_text = result["text"][:10000]

        await asyncio.shield(self.db.commit())

        return {
            "protocol_id": protocol_file_id,
            "text": result.get("text", ""),
            "pages": result.get("pages", 0),
            **({"error": result["error"]} if result.get("error") else {}),
        }

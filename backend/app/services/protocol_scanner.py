"""ProtocolScanner — сканирование PDF протоколов."""

import hashlib
import os
from datetime import datetime
from typing import Any

import pdfplumber
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_file import ProtocolFile
from app.repositories.protocol_file_repository import ProtocolFileRepository


class ProtocolScanner:
    """Scan protocol folders and extract text from PDFs."""

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

    async def scan(self, year: int, month: int) -> dict[str, Any]:
        """Scan folder for PDF protocols and save to DB.

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

        found = 0
        saved = 0
        errors = 0

        for root, _dirs, files in os.walk(target_folder):
            for file in files:
                if not file.lower().endswith(".pdf"):
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.base_path)
                found += 1

                try:
                    # Check if already exists by path
                    existing = await self.repo.get_by_path(relative_path)
                    if existing:
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

        return {
            "found": found,
            "saved": saved,
            "errors": errors,
            "path": target_folder,
        }

    async def extract_text(self, protocol_file_id: int) -> dict[str, Any]:
        """Extract text from PDF using pdfplumber."""
        protocol = await self.repo.get_by_id(protocol_file_id)
        if not protocol:
            return {"error": "Protocol not found"}

        try:
            text_parts = []
            with pdfplumber.open(protocol.file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            full_text = "\n".join(text_parts)

            # Update status
            protocol.status = "scanned"
            await self.db.commit()

            return {
                "protocol_id": protocol_file_id,
                "text": full_text,
                "pages": len(text_parts),
            }

        except Exception as e:
            protocol.status = "error"
            await self.db.commit()
            return {"error": str(e), "protocol_id": protocol_file_id}

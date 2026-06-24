"""ProtocolScanner — сканирование PDF/JPG/PNG протоколов с OCR."""

import asyncio
import hashlib
import logging
import multiprocessing
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol_file import ProtocolFile
from app.repositories.protocol_file_repository import ProtocolFileRepository

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_EXTENSIONS = {".pdf"} | IMAGE_EXTENSIONS

# Magic byte signatures for file type detection
_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [
        b"%PDF-",
    ],
    "image/jpeg": [
        b"\xff\xd8\xff",
    ],
    "image/png": [
        b"\x89PNG\r\n\x1a\n",
    ],
    "image/tiff": [
        b"\x49\x49\x2a\x00",  # Little-endian TIFF
        b"\x4d\x4d\x00\x2a",  # Big-endian TIFF
    ],
    "image/bmp": [
        b"BM",
    ],
    "image/webp": [
        b"RIFF",
    ],
}

# Minimum DPI thresholds for acceptable OCR quality
MIN_DPI = 150
RECOMMENDED_DPI = 300


def detect_file_type(file_path: str) -> str | None:
    """Detect file MIME type using magic bytes, not extension.

    Returns MIME type string (e.g. 'application/pdf', 'image/jpeg')
    or None if unrecognized.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(12)
    except OSError:
        return None

    for mime_type, signatures in _MAGIC_SIGNATURES.items():
        for sig in signatures:
            if header.startswith(sig):
                # WEBP needs extra check: RIFF prefix + WEBP identifier at offset 8
                if mime_type == "image/webp":
                    if len(header) >= 12 and header[8:12] == b"WEBP":
                        return mime_type
                    continue
                return mime_type

    # Fallback: check extension as last resort
    ext = os.path.splitext(file_path)[1].lower()
    ext_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    return ext_map.get(ext)


def preprocess_image(img: "Image.Image") -> "Image.Image":
    """Apply image preprocessing for better OCR results.

    Steps:
    1. Convert to grayscale
    2. Increase contrast (autocontrast)
    3. Apply sharpening filter
    """
    from PIL import Image, ImageFilter, ImageOps

    if img.mode != "L":
        img = img.convert("L")

    img = ImageOps.autocontrast(img, cutoff=2)

    img = img.filter(ImageFilter.SHARPEN)

    return img


def _check_rotation(img: "Image.Image") -> "Image.Image":
    """Detect and correct text orientation using Tesseract OSD.

    Only rotates if confidence is high enough (> 50%).
    """
    import pytesseract

    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        rotation = osd.get("orientation", 0)
        confidence = osd.get("orientation_conf", 0)

        if confidence > 5.0 and rotation != 0:
            logger.info("Auto-rotating image by %d degrees (confidence: %.0f%%)", rotation, confidence)
            if rotation == 90:
                img = img.rotate(-90, expand=True)
            elif rotation == 180:
                img = img.rotate(180, expand=True)
            elif rotation == 270:
                img = img.rotate(90, expand=True)
    except Exception as e:
        logger.debug("OSD rotation detection failed: %s", e)

    return img


def estimate_image_quality(img: "Image.Image") -> dict[str, Any]:
    """Estimate image quality metrics for OCR suitability.

    Returns dict with:
        - dpi: estimated DPI (horizontal, vertical)
        - width_px, height_px: pixel dimensions
        - is_acceptable: whether quality is sufficient for OCR
        - issues: list of quality issues found
    """
    from PIL.ExifTags import Base as ExifBase

    width, height = img.size
    dpi_h = dpi_v = 0
    issues = []

    # Try to get DPI from EXIF
    try:
        exif = img.getexif()
        if exif:
            for tag_id, value in exif.items():
                tag_name = ExifBase(tag_id).name if tag_id in ExifBase else None
                if tag_name == "XResolution":
                    dpi_h = int(float(value))
                elif tag_name == "YResolution":
                    dpi_v = int(float(value))
    except Exception:
        pass

    # If no EXIF DPI, try PIL info dict
    if not dpi_h:
        dpi_info = img.info.get("dpi", (0, 0))
        dpi_h = int(dpi_info[0]) if dpi_info[0] else 0
        dpi_v = int(dpi_info[1]) if dpi_info[1] else 0

    # Quality checks
    if dpi_h and dpi_h < MIN_DPI:
        issues.append(f"low_dpi_{dpi_h}")
    if width < 800 or height < 800:
        issues.append(f"low_resolution_{width}x{height}")
    if width > 8000 or height > 8000:
        issues.append("resolution_too_high_may_timeout")

    is_acceptable = len(issues) == 0 or all(
        i.startswith("low_dpi_") and int(i.split("_")[-1]) >= 100 for i in issues
    )

    return {
        "dpi": (dpi_h, dpi_v),
        "width_px": width,
        "height_px": height,
        "is_acceptable": is_acceptable,
        "issues": issues,
    }


def _extract_text_process(file_path: str, queue: Any) -> None:
    """Top-level helper for multiprocessing — runs in a separate process."""
    import pdfplumber
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image

    file_type = detect_file_type(file_path)

    try:
        if file_type and file_type.startswith("image/"):
            with Image.open(file_path) as img:
                quality = estimate_image_quality(img)
                img = _check_rotation(img)
                img = preprocess_image(img)
                full_text = pytesseract.image_to_string(img, lang="rus+eng")
            pages = 1

        elif file_type == "application/pdf":
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
                ocr_parts = []
                for img in images:
                    img = _check_rotation(img)
                    img = preprocess_image(img)
                    ocr_parts.append(pytesseract.image_to_string(img, lang="rus+eng"))
                full_text = "\n".join(ocr_parts)
        else:
            # Unknown file type — try as image anyway (Tesseract is forgiving)
            logger.warning("Unknown file type for %s, attempting OCR as image", file_path)
            with Image.open(file_path) as img:
                img = _check_rotation(img)
                img = preprocess_image(img)
                full_text = pytesseract.image_to_string(img, lang="rus+eng")
            pages = 1

        queue.put({"text": full_text, "pages": pages, "error": None})
    except Exception as e:
        logger.error("OCR failed for %s: %s", file_path, e)
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
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
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

                # Verify file type with magic bytes
                detected_type = detect_file_type(file_path)
                image_types = {"image/jpeg", "image/png", "image/tiff", "image/bmp"}
                if detected_type not in image_types and detected_type != "application/pdf":
                    logger.warning(
                        "File %s has extension %s but magic bytes indicate type=%s, skipping",
                        file, ext, detected_type,
                    )
                    errors += 1
                    continue

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

    async def extract_text(self, protocol_file_id: int, timeout: float = 120.0) -> dict[str, Any]:
        """Extract text from protocol file with timeout via separate process."""
        protocol = await asyncio.shield(self.repo.get_by_id(protocol_file_id))
        if not protocol:
            return {"error": "Protocol not found"}

        if protocol.raw_text and len(protocol.raw_text) > 50:
            protocol.status = "scanned"
            await asyncio.shield(self.db.commit())
            return {
                "protocol_id": protocol_file_id,
                "text": protocol.raw_text,
                "pages": 0,
            }

        queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_extract_text_process,
            args=(protocol.file_path, queue),
        )
        proc.start()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, queue.get, timeout,
            )
        except Exception:
            proc.terminate()
            proc.join(timeout=5)
            protocol.status = "error"
            protocol.raw_text = f"OCR timeout (>{int(timeout)}s)"
            await asyncio.shield(self.db.commit())
            return {
                "protocol_id": protocol_file_id,
                "error": f"OCR timeout (>{int(timeout)}s)",
            }
        else:
            proc.join(timeout=5)

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

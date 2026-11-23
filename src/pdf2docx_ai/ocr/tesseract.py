from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from pdf2docx_ai.document.models import BBox, OCRResult, OCRWord
from .base import OCREngine, OCRUnavailableError
from ..system import find_program

LANGUAGES = {"it": "ita", "en": "eng", "it+en": "ita+eng"}


class TesseractEngine(OCREngine):
    name = "tesseract"

    def __init__(self, settings=None):
        self.timeout = getattr(settings, "ocr_timeout", 180)
        self.language = getattr(settings, "language", "it")
        self.binary = find_program("tesseract")

    def health_check(self) -> dict:
        if not self.binary:
            return {"available": False, "engine": self.name, "reason": "Tesseract executable not found"}
        try:
            result = subprocess.run([self.binary, "--list-langs"], capture_output=True, encoding='utf-8', errors='replace', timeout=5)
            available = set(result.stdout.splitlines()[1:])
            wanted = set(LANGUAGES[self.language].split("+"))
            return {"available": result.returncode == 0 and wanted <= available,
                    "engine": self.name, "languages": sorted(available),
                    "reason": None if wanted <= available else "Requested language data is not installed"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "engine": self.name, "reason": str(exc)}

    def initialize(self):
        health = self.health_check()
        if not health["available"]:
            raise OCRUnavailableError(str(health.get("reason")))

    def recognize(self, image: Image.Image, region_type: str = "text", language: str = "it") -> OCRResult:
        self.initialize()
        if language not in LANGUAGES:
            raise ValueError("Unsupported OCR language")
        with tempfile.TemporaryDirectory(prefix="pdf2docx-tesseract-") as folder:
            image_path = Path(folder) / "crop.png"
            image.convert("RGB").save(image_path)
            try:
                result = subprocess.run([self.binary, str(image_path), "stdout", "-l", LANGUAGES[language],
                                         "--psm", "3", "tsv"], capture_output=True, encoding='utf-8', errors='replace', timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                raise OCRUnavailableError("Tesseract OCR timed out") from exc
        if result.returncode:
            raise OCRUnavailableError("Tesseract failed: " + result.stderr[-1500:])
        words, lines = [], {}
        for item in csv.DictReader(io.StringIO(result.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
            if not item.get("text", "").strip() or int(item["level"]) != 5:
                continue
            left, top, width, height = (int(item[k]) for k in ("left", "top", "width", "height"))
            line = ":".join(item[k] for k in ("block_num", "par_num", "line_num"))
            confidence = max(0, min(1, float(item["conf"]) / 100))
            words.append(OCRWord(text=item["text"], bbox=BBox(x0=left, y0=top, x1=left + width,
                                                            y1=top + height), confidence=confidence, line=line))
            lines.setdefault(line, []).append(item["text"])
        return OCRResult(text="\n".join(" ".join(parts) for parts in lines.values()), engine=self.name,
                         confidence=sum(w.confidence for w in words) / len(words) if words else None,
                         words=words, raw=result.stdout)

    def shutdown(self):
        pass


"""Apple Vision OCR through a small, repository-owned Swift bridge.

No claim is made about GPU/Neural Engine use: Vision chooses its own backend.
Language correction is disabled; boxes describe entire recognized lines.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image

from pdf2docx_ai.document.models import BBox, OCRResult, OCRWord
from .base import OCREngine, OCRUnavailableError

_COMPILE_LOCK = threading.Lock()


class AppleVisionEngine(OCREngine):
    name = "vision"

    def __init__(self, settings=None, build_dir: Path | None = None):
        self.timeout = getattr(settings, "ocr_timeout", 180)
        self.source = Path(__file__).with_suffix(".swift")
        # A local cache is explicit and can be removed independently of the OS.
        self.build_dir = Path(build_dir or Path.cwd() / ".pdf2docx-cache" / "vision")
        self.binary: Path | None = None

    def health_check(self) -> dict:
        available = platform.system() == "Darwin" and bool(shutil.which("xcrun")) and self.source.is_file()
        return {"available": available, "engine": self.name,
                "reason": "Vision requires macOS and existing Xcode Command Line Tools" if not available else None,
                "runtime": "Apple Vision", "inference_verified": False}

    def initialize(self) -> None:
        if self.binary and self.binary.is_file():
            return
        if not self.health_check()["available"]:
            raise OCRUnavailableError(self.health_check()["reason"])
        self.build_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        digest = hashlib.sha256(self.source.read_bytes() + platform.machine().encode()).hexdigest()[:16]
        binary = self.build_dir / f"vision-{digest}"
        with _COMPILE_LOCK:
            if not binary.is_file():
                temporary = binary.with_name(binary.name + f".{os.getpid()}.tmp")
                try:
                    result = subprocess.run(["xcrun", "swiftc", "-O", "-module-cache-path",
                                             str(self.build_dir / "modules"), str(self.source), "-o", str(temporary)],
                                            capture_output=True, text=True, timeout=self.timeout)
                    if result.returncode:
                        raise OCRUnavailableError("Swift Vision bridge could not compile: " + result.stderr[-2000:])
                    temporary.replace(binary)
                finally:
                    temporary.unlink(missing_ok=True)
        self.binary = binary

    def recognize(self, image: Image.Image, region_type: str = "text", language: str = "it") -> OCRResult:
        self.initialize()
        if language not in {"it", "en", "it+en"}:
            raise ValueError("Unsupported OCR language")
        with tempfile.TemporaryDirectory(prefix="pdf2docx-vision-") as folder:
            crop = Path(folder) / "crop.png"
            image.convert("RGB").save(crop)
            try:
                result = subprocess.run([str(self.binary), str(crop), language], capture_output=True,
                                        text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                raise OCRUnavailableError("Apple Vision OCR timed out") from exc
        if result.returncode:
            raise OCRUnavailableError("Apple Vision OCR failed: " + result.stderr[-1500:])
        try:
            records = json.loads(result.stdout)
            words = [OCRWord(text=item["text"], confidence=item["confidence"], line=item["line"],
                             bbox=BBox(x0=item["x0"], y0=item["y0"], x1=item["x1"], y1=item["y1"]))
                     for item in records]
        except (ValueError, KeyError, TypeError) as exc:
            raise OCRUnavailableError("Invalid Apple Vision response") from exc
        words.sort(key=lambda word: (round(word.bbox.y0 / 8), word.bbox.x0))
        warnings = ["Apple Vision returns line boxes; typography and table structure are inferred geometrically."]
        return OCRResult(text="\n".join(word.text for word in words), engine=self.name, words=words,
                         confidence=sum(w.confidence for w in words) / len(words) if words else None,
                         warnings=warnings)

    def shutdown(self) -> None:
        self.binary = None


"""Crop-level MiniCPM-OCR 1.0 adapter; layout is owned by the application.

Uses SDK prompt recipes and Ollama/llama.cpp payload dialects, without invoking
the SDK's page pipeline and consequently without duplicating layout detection.
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

from pdf2docx_ai.document.models import OCRResult
from .base import OCREngine, OCRUnavailableError
from .local_http import LocalHTTP, probe_model

PROMPTS = {"text": "Text Recognition:", "table": "Table Recognition:", "formula": "Formula Recognition:"}


class MiniCPMOCR10Engine(OCREngine):
    name = "minicpm"

    def __init__(self, settings):
        self.model = settings.minicpm_model
        self.transport = LocalHTTP(settings.minicpm_url, settings.ocr_timeout)
        self.runtime = None
        self._used_ollama = False

    def health_check(self) -> dict:
        return {"engine": self.name, **probe_model(self.transport, self.model), "inference_verified": False}

    def initialize(self):
        if self.runtime:
            return
        health = self.health_check()
        if not health["available"]:
            raise OCRUnavailableError("MiniCPM OCR unavailable: " + str(health.get("reason")))
        self.runtime = health["runtime"]

    def recognize(self, image: Image.Image, region_type: str = "text", language: str = "it") -> OCRResult:
        self.initialize()
        task = region_type if region_type in PROMPTS else "text"
        image = ImageOps.exif_transpose(image).convert("RGB")
        stream = io.BytesIO()
        # Match SDK lossless crop transport; runtime performs its own slicing.
        image.save(stream, format="PNG", compress_level=1)
        encoded = base64.b64encode(stream.getvalue()).decode("ascii")
        budget = {"text": 4096, "table": 8192, "formula": 2048}[task]
        prompt = PROMPTS[task]
        if self.runtime == "ollama":
            payload = {"model": self.model, "stream": False,
                       "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
                       "options": {"temperature": 0.01, "top_p": 0.001, "top_k": 1,
                                   "repeat_penalty": 1, "num_predict": budget, "num_ctx": 16384}}
            data = self.transport.json("POST", "/api/chat", payload)
            self._used_ollama = True
            text = (data.get("message") or {}).get("content")
            finish = data.get("done_reason")
        else:
            payload = {"model": self.model, "stream": False, "max_tokens": budget,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
                           {"type": "text", "text": prompt}]}], "temperature": 0.01,
                       "top_p": 0.001, "top_k": 1, "repeat_penalty": 1}
            data = self.transport.json("POST", "/v1/chat/completions", payload)
            try:
                text = data["choices"][0]["message"]["content"]
                finish = data["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError) as exc:
                raise OCRUnavailableError("Malformed MiniCPM response") from exc
        if finish == "length":
            raise OCRUnavailableError("MiniCPM output truncated; split the crop or increase runtime context")
        if not isinstance(text, str) or not text.strip():
            raise OCRUnavailableError("MiniCPM returned an empty/non-text result")
        warnings = ["MiniCPM output has region-level coordinates only; confidence is unavailable."]
        if language.startswith("it"):
            warnings.append("MiniCPM documents Chinese/English support; Italian quality needs separate validation.")
        return OCRResult(text=text, engine=self.name, raw=text,
                         format={"text": "text", "table": "html", "formula": "latex"}[task], warnings=warnings)

    def shutdown(self):
        if self._used_ollama:
            try:
                self.transport.json("POST", "/api/generate", {"model": self.model, "keep_alive": 0}, timeout=5)
            except OCRUnavailableError:
                pass
        self.transport.close()
        self.runtime = None
        self._used_ollama = False


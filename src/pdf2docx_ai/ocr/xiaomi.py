"""Xiaomi-OCR-0 adapter, using the upstream experimental Ollama protocol.

Preprocessing and non-thinking prompt recipe follow Xiaomi Corporation's
Apache-2.0 repository (see docs/ocr-backends.md). Transport is rewritten to
reject non-loopback URLs, redirects and proxy environment settings.
"""
from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageOps

from pdf2docx_ai.document.models import OCRResult
from .base import OCREngine, OCRUnavailableError
from .local_http import LocalHTTP, probe_model
from .postprocess import otsl_to_html

PROMPTS = {
    "text": "Extract the text in the image.",
    "table": "Parse the table in the image into OTSL.",
    "formula": "Identify the formula in the image and represent it using LATEX format.",
}


def prepare_image(image: Image.Image) -> tuple[bytes, int]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    width, height = image.size
    if min(width, height) < 1 or max(width, height) / min(width, height) > 200:
        raise ValueError("Image aspect ratio exceeds Xiaomi/Qwen3.5 bounds")
    quantum, minimum, maximum = 32, 65536, 16777216
    target_w = max(quantum, round(width / quantum) * quantum)
    target_h = max(quantum, round(height / quantum) * quantum)
    if target_w * target_h < minimum:
        scale = math.sqrt(minimum / (width * height))
        target_w = math.ceil(width * scale / quantum) * quantum
        target_h = math.ceil(height * scale / quantum) * quantum
    elif target_w * target_h > maximum:
        scale = math.sqrt(maximum / (width * height))
        target_w = max(quantum, math.floor(width * scale / quantum) * quantum)
        target_h = max(quantum, math.floor(height * scale / quantum) * quantum)
    image = image.resize((target_w, target_h), Image.Resampling.BICUBIC)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), target_w * target_h // (quantum * quantum)


class XiaomiOCR0Engine(OCREngine):
    name = "xiaomi"

    def __init__(self, settings):
        self.model = settings.xiaomi_model
        self.transport = LocalHTTP(settings.xiaomi_url, settings.ocr_timeout)
        self.runtime: str | None = None
        self._used_ollama = False

    def health_check(self) -> dict:
        return {"engine": self.name, **probe_model(self.transport, self.model),
                "inference_verified": False}

    def initialize(self):
        if self.runtime:
            return
        health = self.health_check()
        if not health["available"]:
            raise OCRUnavailableError(f"Xiaomi OCR unavailable: {health.get('reason')}")
        self.runtime = health["runtime"]

    def recognize(self, image: Image.Image, region_type: str = "text", language: str = "it") -> OCRResult:
        self.initialize()
        task = region_type if region_type in PROMPTS else "text"
        png, visual_tokens = prepare_image(image)
        encoded = base64.b64encode(png).decode("ascii")
        budget = {"text": 4096, "table": 4096, "formula": 2048}[task]
        prompt = PROMPTS[task]
        if visual_tokens + budget >= 32768:
            raise ValueError("Xiaomi image and output exceed local context budget")
        if self.runtime == "ollama":
            # Upstream template is deliberately raw and excludes thinking.
            rendered = "<|im_start|>user\n[img-0]" + prompt.strip()
            rendered += "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            payload = {"model": self.model, "prompt": rendered, "images": [encoded], "raw": True,
                       "stream": False, "truncate": False,
                       "options": {"temperature": 0, "repeat_penalty": 1, "seed": 0,
                                   "num_ctx": 32768, "num_predict": budget}}
            data = self.transport.json("POST", "/api/generate", payload)
            self._used_ollama = True
            text, finish = data.get("response"), data.get("done_reason")
        else:
            payload = {"model": self.model, "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
                {"type": "text", "text": prompt}]}], "max_tokens": budget,
                "temperature": 0, "top_p": 0.8, "presence_penalty": 0, "repetition_penalty": 1,
                "chat_template_kwargs": {"enable_thinking": False}, "stream": False}
            data = self.transport.json("POST", "/v1/chat/completions", payload)
            try:
                text = data["choices"][0]["message"]["content"]
                finish = data["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError) as exc:
                raise OCRUnavailableError("Malformed Xiaomi OpenAI response") from exc
        if finish == "length":
            raise OCRUnavailableError("Xiaomi output truncated; split the region or increase runtime context")
        if not isinstance(text, str) or not text.strip():
            raise OCRUnavailableError("Xiaomi returned an empty/non-text result")
        raw, output_format, warnings = text, "text", []
        if task == "table":
            try:
                text = otsl_to_html(text)
                output_format = "html"
            except ValueError as exc:
                warnings.append(str(exc))
        elif task == "formula":
            output_format = "latex"
        warnings.append("Xiaomi output has region-level coordinates only; confidence is unavailable.")
        if language.startswith("it"):
            warnings.append("Italian accuracy of this model/runtime has not been measured in this installation.")
        return OCRResult(text=text, engine=self.name, raw=raw, format=output_format, warnings=warnings)

    def shutdown(self):
        if self._used_ollama:
            try:
                self.transport.json("POST", "/api/generate", {"model": self.model, "keep_alive": 0}, timeout=5)
            except OCRUnavailableError:
                pass
        self.transport.close()
        self.runtime = None
        self._used_ollama = False


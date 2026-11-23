import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

from pdf2docx_ai.config import Settings
from pdf2docx_ai.layout.fallback import GeometricLayoutDetector
from pdf2docx_ai.layout.ppdoclayout import PPDocLayoutDetector
from pdf2docx_ai.ocr.base import OCRUnavailableError
from pdf2docx_ai.ocr.local_http import LocalHTTP, local_base_url
from pdf2docx_ai.ocr.minicpm import MiniCPMOCR10Engine
from pdf2docx_ai.ocr.postprocess import otsl_to_html
from pdf2docx_ai.ocr.selector import select_engine
from pdf2docx_ai.ocr.xiaomi import XiaomiOCR0Engine, prepare_image


@pytest.mark.parametrize("url", ["https://127.0.0.1:8000", "http://localhost:8000", "http://example.com",
                                 "http://192.168.1.1", "http://127.0.0.1.evil.test", "http://127.0.0.1:80/x",
                                 "http://user@127.0.0.1", "http://127.0.0.1?url=https://example.com"])
def test_remote_or_ambiguous_ocr_urls_are_refused(url):
    with pytest.raises(ValueError):
        local_base_url(url)


def test_ipv6_loopback_is_supported():
    assert local_base_url("http://[::1]:8000/v1") == "http://[::1]:8000"


def test_http_redirect_is_never_followed():
    transport = LocalHTTP("http://127.0.0.1:8000")
    seen = []
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com"})
    transport._client = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False)
    with pytest.raises(OCRUnavailableError):
        transport.json("POST", "/v1/chat/completions", {"private": "document"})
    assert seen == ["http://127.0.0.1:8000/v1/chat/completions"]
    transport.close()


def test_minicpm_model_is_required_and_distinct_task_prompts():
    engine = MiniCPMOCR10Engine(Settings())
    requests = []
    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(404)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "minicpm-ocr"}]})
        data = json.loads(request.content)
        requests.append(data)
        return httpx.Response(200, json={"choices": [{"message": {"content": "<table><tr><td>123</td></tr></table>"},
                                                     "finish_reason": "stop"}]})
    engine.transport._client = httpx.Client(transport=httpx.MockTransport(handle))
    result = engine.recognize(Image.new("RGB", (200, 100)), "table", "en")
    assert result.format == "html" and result.confidence is None
    assert requests[0]["messages"][0]["content"][1]["text"] == "Table Recognition:"
    assert "mm_processor_kwargs" not in requests[0]  # Runtime owns slicing for llama.cpp.
    engine.shutdown()


def test_minicpm_refuses_truncated_generation():
    engine = MiniCPMOCR10Engine(Settings())
    engine.runtime = "openai"
    engine.transport._client = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]})))
    with pytest.raises(OCRUnavailableError, match="truncated"):
        engine.recognize(Image.new("RGB", (100, 100)))
    engine.shutdown()


def test_configured_model_must_match_health_list():
    engine = MiniCPMOCR10Engine(Settings())
    engine.transport._client = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={"models": [{"name": "unrelated:latest"}]})))
    assert not engine.health_check()["available"]
    engine.shutdown()


def test_xiaomi_uses_raw_non_thinking_ollama_recipe_and_converts_otsl():
    engine = XiaomiOCR0Engine(Settings())
    seen = []
    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": engine.model}]})
        payload = json.loads(request.content)
        seen.append(payload)
        if payload.get("keep_alive") == 0:
            return httpx.Response(200, json={"done": True})
        return httpx.Response(200, json={"response": "<fcel>A<fcel>B<nl><fcel>1<fcel>2<nl>", "done_reason": "stop"})
    engine.transport._client = httpx.Client(transport=httpx.MockTransport(handle))
    result = engine.recognize(Image.new("RGB", (600, 300), "white"), "table", "it")
    assert result.format == "html" and "<td>2</td>" in result.text
    assert result.raw.startswith("<fcel>")
    assert seen[0]["raw"] is True and "</think>" in seen[0]["prompt"]
    decoded = Image.open(io.BytesIO(base64.b64decode(seen[0]["images"][0])))
    assert decoded.width % 32 == decoded.height % 32 == 0
    engine.shutdown()
    assert seen[-1]["keep_alive"] == 0


def test_xiaomi_preprocessing_grid_and_aspect_ratio():
    data, tokens = prepare_image(Image.new("RGB", (100, 20)))
    image = Image.open(io.BytesIO(data))
    assert image.width % 32 == image.height % 32 == 0
    assert image.width * image.height >= 65536
    assert tokens == image.width * image.height // 1024
    with pytest.raises(ValueError, match="aspect ratio"):
        prepare_image(Image.new("RGB", (2048, 1)))


def test_otsl_merge_and_bad_structure():
    html = otsl_to_html("<fcel>A<lcel><fcel>B<nl><ucel><xcel><fcel>C<nl>")
    assert 'rowspan="2" colspan="2"' in html
    with pytest.raises(ValueError, match="Non-rectangular"):
        otsl_to_html("<fcel>A<fcel>B<nl><fcel>C<nl>")
    assert "&lt;script&gt;" in otsl_to_html("<fcel><script><nl>")


def test_auto_selection_is_deterministic_and_lazy(monkeypatch):
    import pdf2docx_ai.ocr.selector as selector
    calls = []
    class Fake:
        def __init__(self, name): self.name = name
        def health_check(self):
            calls.append(self.name)
            return {"available": self.name in {"vision", "tesseract"}}
        def shutdown(self): pass
    monkeypatch.setattr(selector, "create_engine", lambda name, settings: Fake(name))
    assert select_engine(Settings()).name == "vision"
    assert calls == ["xiaomi", "minicpm", "vision"]


def test_geometric_layout_is_explicit_and_boxes_are_pixels():
    image = Image.new("RGB", (600, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 50, 250, 75), fill="black")
    draw.rectangle((50, 200, 300, 225), fill="black")
    regions = GeometricLayoutDetector().detect(image, page_number=7)
    assert len(regions) == 2
    assert all(r.page_number == 7 and r.metadata["semantic_classification"] is False for r in regions)
    assert all(0 <= r.bbox.x0 < r.bbox.x1 <= 600 for r in regions)


def test_ppdoclayout_will_not_download_missing_weights(tmp_path):
    detector = PPDocLayoutDetector(tmp_path)
    assert not detector.health_check()["available"]
    with pytest.raises(RuntimeError, match="Requires local"):
        detector.detect(Image.new("RGB", (100, 100)))


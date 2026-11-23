"""Opt-in real Apple Vision tests. No OCR mocks and no downloaded models.

Run from a normal macOS terminal:
    PDF2DOCX_REAL_OCR=1 .venv/bin/python -m pytest -m real_ocr -q
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

import pymupdf
import pytest
from docx import Document as WordDocument
from docx.oxml.ns import qn

from pdf2docx_ai.config import Settings
from pdf2docx_ai.document.models import Document
from pdf2docx_ai.pipeline import convert
from pdf2docx_ai.quality.validator import find_renderer

pytestmark = [
    pytest.mark.real_ocr,
    pytest.mark.skipif(os.environ.get("PDF2DOCX_REAL_OCR") != "1",
                       reason="Real local OCR is opt-in: set PDF2DOCX_REAL_OCR=1"),
    pytest.mark.skipif(platform.system() != "Darwin", reason="This test exercises Apple Vision on macOS"),
]


def _text(word):
    return "\n".join(node.text or "" for node in word.element.iter(qn("w:t")))


@pytest.mark.parametrize("language", ["it", "en"])
def test_real_scan_is_editable_searchable_and_measured(pdf_fixtures, tmp_path, language):
    source = pdf_fixtures[f"scan_{language}"]
    truth = source.with_suffix(".txt")
    settings = Settings(engine="vision", language=language, ground_truth=truth,
                        searchable_pdf=True, validate_visual=True, resume=False)
    result = convert(source, tmp_path / f"real-{language}.docx", settings)
    report = json.loads(Path(result.json_path).read_text())
    model = Document.model_validate_json(Path(result.model_path).read_text())
    word = WordDocument(result.output_path)
    expected = " ".join(truth.read_text().split())
    assert " ".join(_text(word).split()) == expected
    assert not word.inline_shapes  # Scan page was reconstructed as editable text.
    assert report["engine"] == "vision"
    assert report["text_accuracy"]["cer"] == 0
    assert report["text_accuracy"]["wer"] == 0
    assert report["performance"]["ocr_seconds"] > 0
    assert report["performance"]["cache_pages_reused"] == 0
    assert all(r.engine == "vision" for p in model.pages for r in p.regions if r.source == "ocr")
    assert any(r.source == "ocr" and r.bbox.area > 0 for p in model.pages for r in p.regions)
    with pymupdf.open(result.searchable_path) as pdf:
        assert len(pdf) == 1
        assert " ".join(pdf[0].get_text().split()) == expected
    assert Path(result.report_path).is_file()
    if find_renderer():
        assert report["visual"]["status"] == "measured"
        assert report["visual"]["page_count_difference"] == 0
        assert -1 <= report["visual"]["pages"][0]["ssim"] <= 1
    else:
        assert report["visual"]["status"] == "unavailable"


def test_real_mixed_pdf_uses_ocr_without_duplicating_native_text(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["mixed"], tmp_path / "real-mixed.docx",
                     Settings(engine="vision", language="it", searchable_pdf=True, resume=False))
    text = _text(WordDocument(result.output_path))
    assert text.count("Intestazione nativa 123") == 1
    assert text.count("Regione scannerizzata 456") == 1
    model = Document.model_validate_json(Path(result.model_path).read_text())
    assert any(r.source == "native" and r.text for p in model.pages for r in p.regions)
    assert any(r.source == "ocr" and r.engine == "vision" for p in model.pages for r in p.regions)
    assert result.performance["ocr_seconds"] > 0
    with pymupdf.open(result.searchable_path) as pdf:
        searchable = "\n".join(page.get_text() for page in pdf)
    assert searchable.count("Intestazione nativa 123") == 1
    assert searchable.count("Regione scannerizzata 456") == 1


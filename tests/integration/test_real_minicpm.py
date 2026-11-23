"""Opt-in inference through an already installed local MiniCPM server.

Never installs or downloads a model. Enable with PDF2DOCX_REAL_MINICPM=1.
"""
import json
import os
from pathlib import Path

import pytest
from docx import Document

from pdf2docx_ai.config import Settings
from pdf2docx_ai.pipeline import convert

pytestmark=[pytest.mark.real_ocr,pytest.mark.skipif(
    os.environ.get("PDF2DOCX_REAL_MINICPM")!="1",
    reason="Set PDF2DOCX_REAL_MINICPM=1 for an installed local MiniCPM server")]


@pytest.mark.parametrize("language",["en","it"])
def test_real_minicpm_produces_editable_text_and_measured_accuracy(pdf_fixtures,tmp_path,language):
    source=pdf_fixtures[f"scan_{language}"]
    result=convert(source,tmp_path/f"minicpm-{language}.docx",Settings(
        engine="minicpm",language=language,ground_truth=source.with_suffix(".txt"),resume=False))
    word=Document(result.output_path)
    text=" ".join(" ".join(p.text for p in word.paragraphs).split())
    expected=" ".join(source.with_suffix(".txt").read_text().split())
    assert text==expected
    assert not word.inline_shapes
    report=json.loads(Path(result.json_path).read_text())
    assert report["engine"]=="minicpm"
    assert report["performance"]["ocr_seconds"]>0
    assert report["performance"]["cache_pages_reused"]==0
    assert report["text_accuracy"]["cer"]==0
    assert report["text_accuracy"]["wer"]==0

from pathlib import Path

import pytest

from pdf2docx_ai.config import Settings
from pdf2docx_ai.pdf.inspector import inspect_pdf


@pytest.mark.parametrize("fixture,classification", [
    ("native", "native"), ("scan_it", "scanned"),
    ("scan_en", "scanned"), ("mixed", "mixed"),
])
def test_classification(pdf_fixtures, fixture, classification):
    assert inspect_pdf(pdf_fixtures[fixture])["pages"][0]["classification"] == classification


def test_rotated_crop_geometry(pdf_fixtures):
    page = inspect_pdf(pdf_fixtures["rotated_crop"])["pages"][0]
    assert page["rotation"] == 90
    assert page["width"] == 800
    assert page["height"] == 560
    assert list(page["cropbox"]) == [40, 50, 600, 850]


def test_multipage_and_variable_sizes(pdf_fixtures):
    result = inspect_pdf(pdf_fixtures["page_sizes"])
    assert result["page_count"] == 3
    assert result["variable_page_sizes"] is True


def test_inspector_detects_two_columns(pdf_fixtures):
    assert inspect_pdf(pdf_fixtures["columns"])["pages"][0]["columns"] == 2


def test_file_and_page_limits(pdf_fixtures):
    with pytest.raises(ValueError):
        inspect_pdf(pdf_fixtures["headers"], Settings(max_pages=1))


def test_encrypted_pdf_is_rejected(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Secret synthetic fixture")
    encrypted = tmp_path / "encrypted.pdf"
    doc.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
             owner_pw="owner-test-only", user_pw="user-test-only")
    doc.close()
    with pytest.raises(ValueError):
        inspect_pdf(encrypted)

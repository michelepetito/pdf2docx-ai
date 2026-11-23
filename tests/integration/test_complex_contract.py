"""Opt-in checks for the independent complex source corpus, not converter output.

Generate references first with scripts/generate_complex_corpus.py and run:
PDF2DOCX_COMPLEX=1 python -m pytest -m complex -q
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
import pymupdf
import pytest

ROOT=Path(__file__).parents[2]
MANIFEST=ROOT/"tests/fixtures/complex/generated/manifest.json"
IDS=("europass_fictitious","research_bulletin","administrative_report","invoice_complex",
     "field_inspection","mixed_orientation","typography_catalog","financial_statement",
     "project_newsletter","procurement_form")
pytestmark=[pytest.mark.complex,pytest.mark.skipif(os.environ.get("PDF2DOCX_COMPLEX")!="1",
            reason="Set PDF2DOCX_COMPLEX=1 after generating complex references")]


@pytest.fixture(scope="module")
def corpus():
    if not MANIFEST.is_file(): pytest.skip("Generate the complex corpus first")
    return json.loads(MANIFEST.read_text())


def test_complex_corpus_has_independent_fixed_development_and_holdout(corpus):
    documents=corpus["documents"]
    assert len(documents)==10
    assert {d["id"] for d in documents}==set(IDS)
    assert Counter(d["split"] for d in documents)=={"development":7,"holdout":3}
    assert {d["id"] for d in documents if d["split"]=="holdout"}=={
        "financial_statement","project_newsletter","procurement_form"}
    assert corpus["synthetic_only"] is True
    assert corpus["reference_uses_layout_tables"] is False
    assert corpus["reference_uses_textboxes"] is False


@pytest.mark.parametrize("identifier",IDS)
def test_reference_is_complex_readable_and_has_no_artificial_layout_containers(corpus,identifier):
    entry=next(d for d in corpus["documents"] if d["id"]==identifier)
    source=Path(entry["reference_docx"])
    assert source.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==entry["source_sha256"]
    reference=Document(source)
    assert not reference.element.xpath("//w:txbxContent")
    assert len(reference.tables)==entry["expected_tables"]
    assert len(reference.element.xpath("//pic:pic"))==entry["expected_images"]
    # Exact paragraph line height clips inline images in Word/LibreOffice.
    for paragraph in reference.paragraphs:
        if paragraph._p.xpath(".//wp:inline"):
            assert not paragraph._p.xpath("./w:pPr/w:spacing[@w:lineRule='exact']")
    with ZipFile(source) as archive:
        assert archive.testzip() is None
        assert not any("vbaProject" in name for name in archive.namelist())
    with pymupdf.open(entry["pdf"]) as pdf:
        assert len(pdf)==entry["pages"]>=2
        text="\n".join(p.get_text() for p in pdf)
        assert len(text)>2000
        assert all("LABORATORIO ESEMPIO" in p.get_text() for p in pdf)
        assert all("Pagina" in p.get_text() for p in pdf)
        assert all(p.rect.width>0 and p.rect.height>0 for p in pdf)
    assert Path(entry["ground_truth"]).is_file()
    assert Path(entry["reference_body_text"]).is_file()


def test_european_cv_has_photo_date_tabs_real_table_and_two_pages(corpus):
    entry=next(d for d in corpus["documents"] if d["id"]=="europass_fictitious")
    source=Document(entry["reference_docx"])
    assert entry["pages"]==2
    assert len(source.element.xpath("//wp:anchor"))==1
    assert len(source.element.xpath("//w:tab"))>=8
    assert len(source.tables)==1
    assert len(source.tables[0].rows)==4
    assert source.tables[0].cell(0,0).text=="Lingua"
    text="\n".join(p.text for p in source.paragraphs)
    assert "ELENA ESEMPIO" in text
    assert "example.invalid" in text
    assert "fittizi" in text
    with pymupdf.open(entry["pdf"]) as pdf:
        assert pdf[0].get_image_info()


def test_real_complex_tables_include_merged_headers_and_native_mixed_sections(corpus):
    entries={d["id"]:d for d in corpus["documents"]}
    invoice=Document(entries["invoice_complex"]["reference_docx"])
    procurement=Document(entries["procurement_form"]["reference_docx"])
    assert invoice.element.xpath("//w:gridSpan[@w:val='5']")
    assert procurement.element.xpath("//w:gridSpan[@w:val='2']")
    mixed=Document(entries["mixed_orientation"]["reference_docx"])
    assert {(round(s.page_width.pt),round(s.page_height.pt)) for s in mixed.sections}=={(595,842),(842,595)}
    newsletter=Document(entries["project_newsletter"]["reference_docx"])
    assert newsletter.element.xpath("//w:cols[@w:equalWidth='0']/w:col")

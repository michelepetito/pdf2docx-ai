"""End-to-end conversion tests; no model weights or remote services required."""
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document as WordDocument
from lxml import etree

from pdf2docx_ai.config import Settings
from pdf2docx_ai.document.models import BBox, Document, OCRResult, OCRWord
from pdf2docx_ai.pipeline import convert


def all_text(word):
    text = [p.text for p in word.paragraphs]
    text.extend(cell.text for table in word.tables for row in table.rows for cell in row.cells)
    for section in word.sections:
        text.extend(p.text for p in section.header.paragraphs)
        text.extend(p.text for p in section.footer.paragraphs)
    return "\n".join(text)


class ForbiddenOCR:
    def initialize(self):
        raise AssertionError("Native document must not initialize OCR")

    def recognize(self, image, region_type="text", language="it"):
        raise AssertionError("Native document must not run OCR")

    def health_check(self):
        return {"available": True}

    def shutdown(self):
        pass


class MockOCR:
    def __init__(self, text="Documento scannerizzato 12345"):
        self.text = text
        self.calls = 0
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def recognize(self, image, region_type="text", language="it"):
        self.calls += 1
        width, height = image.size
        return OCRResult(
            text=self.text, engine="mock", confidence=0.99,
            words=[OCRWord(text=self.text, bbox=BBox(
                x0=width * .08, y0=height * .1, x1=width * .8, y1=height * .14),
                line="1", confidence=.99)] if self.text else [],
        )

    def health_check(self):
        return {"available": True}

    def shutdown(self):
        self.initialized = False


def test_native_is_editable_and_preserves_styles(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["native"], tmp_path / "native.docx", Settings(), ocr_engine=ForbiddenOCR())
    word = WordDocument(result.output_path)
    text = all_text(word)
    assert "La città è più bella: perché c'è qualità." in text
    assert "The document contains editable text" in text
    assert text.count("Documento nativo italiano") == 1
    assert any(run.bold for p in word.paragraphs for run in p.runs)
    assert any(run.italic for p in word.paragraphs for run in p.runs)
    with ZipFile(result.output_path) as archive:
        assert archive.testzip() is None
        etree.fromstring(archive.read("word/document.xml"))
        assert not any(name.endswith("vbaProject.bin") for name in archive.namelist())
    model = Document.model_validate_json(Path(result.model_path).read_text())
    assert model.pages[0].regions
    assert all(region.bbox.width >= 0 for region in model.pages[0].regions)
    assert Path(result.report_path).is_file()
    report = json.loads(Path(result.json_path).read_text())
    assert isinstance(report, dict)


def test_scan_runs_ocr_and_retains_editable_text(pdf_fixtures, tmp_path):
    engine = MockOCR()
    result = convert(pdf_fixtures["scan_it"], tmp_path / "scan.docx", Settings(), ocr_engine=engine)
    assert engine.calls >= 1
    text = all_text(WordDocument(result.output_path))
    assert text.count(engine.text) == 1
    model = Document.model_validate_json(Path(result.model_path).read_text())
    assert any(region.source == "ocr" for region in model.pages[0].regions)


def test_mixed_does_not_duplicate_native_text(pdf_fixtures, tmp_path):
    engine = MockOCR("Regione scannerizzata 456")
    result = convert(pdf_fixtures["mixed"], tmp_path / "mixed.docx", Settings(), ocr_engine=engine)
    text = all_text(WordDocument(result.output_path))
    assert text.count("Intestazione nativa 123") == 1
    assert text.count("Regione scannerizzata 456") == 1
    assert engine.calls >= 1


def test_columns_read_left_then_right(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["columns"], tmp_path / "columns.docx", Settings())
    text = all_text(WordDocument(result.output_path))
    assert text.index("Sinistra 1:") < text.index("Sinistra 8:") < text.index("Destra 1:") < text.index("Destra 8:")
    model = Document.model_validate_json(Path(result.model_path).read_text())
    assert model.pages[0].columns == 2


def test_table_contains_native_word_cells(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["table"], tmp_path / "table.docx", Settings())
    word = WordDocument(result.output_path)
    assert word.tables
    table = word.tables[0]
    assert len(table.rows) == 3
    assert len(table.columns) == 3
    assert table.cell(0, 0).text == "Prodotto"
    assert table.cell(1, 0).text == "Matite"
    assert table.cell(2, 2).text == "9.00"
    # Cell text is not duplicated as extra paragraphs outside the table.
    assert sum(p.text.count("Matite") for p in word.paragraphs) == 0


def test_independent_image_is_preserved(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["image"], tmp_path / "image.docx", Settings(), ocr_engine=MockOCR(""))
    word = WordDocument(result.output_path)
    assert "Didascalia modificabile" in all_text(word)
    with ZipFile(result.output_path) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())


def test_merged_table_uses_word_grid_span(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["merged_table"], tmp_path / "merged.docx", Settings())
    word = WordDocument(result.output_path)
    assert word.tables
    assert word.tables[0].cell(0, 0).text == "Dati riuniti"
    with ZipFile(result.output_path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert root.xpath("boolean(//w:tbl//w:gridSpan[@w:val='2'])", namespaces=ns)


def test_lists_preserve_editable_content(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["lists"], tmp_path / "lists.docx", Settings())
    word = WordDocument(result.output_path)
    text = all_text(word)
    assert all(item in text for item in ("Primo elemento", "Secondo elemento", "Terzo elemento", "Primo punto"))
    assert any(p.style.name in ("List Number", "List Bullet") for p in word.paragraphs)


def test_headers_and_footers_are_word_parts(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["headers"], tmp_path / "headers.docx", Settings())
    word = WordDocument(result.output_path)
    assert "Rapporto aziendale" in "\n".join(p.text for s in word.sections for p in s.header.paragraphs)
    assert "Pagina" in "\n".join(p.text for s in word.sections for p in s.footer.paragraphs)
    body = "\n".join(p.text for p in word.paragraphs)
    for number in range(1, 4):
        assert f"Contenuto pagina {number}" in body


@pytest.mark.parametrize("name,expected_size", [
    ("landscape", (842, 595)),
    ("rotated_crop", (800, 560)),
])
def test_page_geometry_and_rotation(pdf_fixtures, tmp_path, name, expected_size):
    result = convert(pdf_fixtures[name], tmp_path / f"{name}.docx", Settings())
    section = WordDocument(result.output_path).sections[0]
    assert section.page_width.pt == pytest.approx(expected_size[0], abs=.1)
    assert section.page_height.pt == pytest.approx(expected_size[1], abs=.1)
    assert all_text(WordDocument(result.output_path)).strip()
    if name == "rotated_crop":
        model = Document.model_validate_json(Path(result.model_path).read_text())
        region = next(r for r in model.pages[0].regions if "Testo ruotato" in r.text)
        # Text at media (90, 140), crop origin (40, 50), displayed rotation90.
        # This also catches PyMuPDF1.26.7 find_tables changing the page cropbox.
        assert region.bbox.x0 == pytest.approx(705.216, abs=.1)
        assert region.bbox.y0 == pytest.approx(50, abs=.1)
        assert region.bbox.x1 == pytest.approx(727.2, abs=.1)


def test_mixed_page_sizes_produce_sections(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["page_sizes"], tmp_path / "sizes.docx", Settings())
    word = WordDocument(result.output_path)
    sizes = {(round(s.page_width.pt), round(s.page_height.pt)) for s in word.sections}
    assert {(595, 842), (842, 595), (420, 595)} <= sizes


def test_formula_is_not_silently_lost(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["formula"], tmp_path / "formula.docx", Settings())
    word = WordDocument(result.output_path)
    text = all_text(word)
    assert "Formula matematica" in text
    assert "E = mc" in text or len(word.inline_shapes) > 0


def test_visual_mode_has_distinct_output_and_raster_warning(pdf_fixtures, tmp_path):
    result = convert(pdf_fixtures["native"], tmp_path / "native.visual.docx", Settings(mode="visual"))
    with ZipFile(result.output_path) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())
    report_text = Path(result.report_path).read_text().lower()
    assert any(token in report_text for token in ("raster", "non edit", "non-edit", "not edit"))


def test_invalid_pdf_and_output_collision(tmp_path, pdf_fixtures):
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a PDF")
    with pytest.raises((ValueError, RuntimeError)):
        convert(invalid, tmp_path / "invalid.docx", Settings())
    existing = tmp_path / "existing.docx"
    existing.write_bytes(b"preserve me")
    with pytest.raises((ValueError, FileExistsError)):
        convert(pdf_fixtures["native"], existing, Settings())
    assert existing.read_bytes() == b"preserve me"


def test_page_limit_is_enforced(pdf_fixtures, tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        convert(pdf_fixtures["headers"], tmp_path / "limited.docx", Settings(max_pages=1))


def test_searchable_pdf_contains_recognized_text(pdf_fixtures, tmp_path):
    import pymupdf
    result = convert(pdf_fixtures["scan_it"], tmp_path / "searchable.docx",
                     Settings(searchable_pdf=True), ocr_engine=MockOCR())
    assert result.searchable_path
    with pymupdf.open(result.searchable_path) as pdf:
        assert "12345" in "".join(page.get_text() for page in pdf)

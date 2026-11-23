import json
from pathlib import Path

import pytest
from PIL import Image
from docx import Document as WordDocument
from typer.testing import CliRunner

from pdf2docx_ai.cli import app
from pdf2docx_ai.config import Settings
from pdf2docx_ai.document.geometry import PageTransform
from pdf2docx_ai.document.models import BBox,OCRResult
from pdf2docx_ai.pipeline import convert,compare
from pdf2docx_ai.quality.metrics import ssim,text_metrics


def test_coordinate_roundtrip_and_word_units():
    transform=PageTransform(600,800,1500,2000)
    original=BBox(x0=10,y0=20,x1=60,y1=90)
    assert transform.pixels_to_pdf(transform.pdf_to_pixels(original))==original
    assert transform.points_to_twips(72)==1440
    assert transform.points_to_emu(72)==914400
    with pytest.raises(ValueError): BBox(x0=0,y0=0,x1=float("nan"),y1=1)


def test_metrics_distinguish_visual_and_textual_error():
    white=Image.new("RGB",(32,32),"white")
    black=Image.new("RGB",(32,32),"black")
    assert ssim(white,white)==pytest.approx(1)
    assert ssim(white,black)<.01
    metrics=text_metrics("città","citta")
    assert metrics["cer"]==pytest.approx(.2)
    assert metrics["wer"]==1
    assert text_metrics("a  b\n","a b")["cer"]==0


def test_cli_json_is_a_single_parseable_object(pdf_fixtures,tmp_path):
    result=CliRunner().invoke(app,["convert",str(pdf_fixtures["native"]),"--output",str(tmp_path/"test.docx"),"--json"])
    assert result.exit_code==0,result.output
    assert Path(json.loads(result.stdout)["output_path"]).is_file()


def test_resume_uses_completed_checkpoints_and_keeps_engine_provenance(pdf_fixtures,tmp_path):
    class OCR:
        name="test-local"
        def initialize(self): pass
        def shutdown(self): pass
        def recognize(self,*args): return OCRResult(text="Totale 123",engine=self.name)
    output=tmp_path/"resume.docx"
    first=convert(pdf_fixtures["scan_it"],output,Settings(),ocr_engine=OCR())
    class NoCall(OCR):
        def recognize(self,*args): raise AssertionError("checkpoint should be used")
    # Fingerprint includes injected class identity; same adapter type with a
    # patched method demonstrates actual checkpoint reuse.
    adapter=OCR()
    adapter.recognize=lambda *args: (_ for _ in ()).throw(AssertionError("cached"))
    second=convert(pdf_fixtures["scan_it"],output,Settings(overwrite=True),ocr_engine=adapter)
    assert second.performance["cache_pages_reused"]==1
    assert json.loads(Path(second.json_path).read_text())["engine"]=="test-local"


def test_changed_config_cannot_reuse_old_page_checkpoint(pdf_fixtures,tmp_path):
    output=tmp_path/"change.docx"
    convert(pdf_fixtures["native"],output,Settings())
    changed=convert(pdf_fixtures["native"],output,Settings(dpi=150,overwrite=True))
    assert changed.performance["cache_pages_reused"]==0


def test_second_pass_preserves_original_and_conflicting_alternative(pdf_fixtures,tmp_path,monkeypatch):
    import pdf2docx_ai.pipeline as pipeline
    class OCR:
        name="first"
        def initialize(self): pass
        def shutdown(self): pass
        def recognize(self,*args): return OCRResult(text="Totale 1O2",engine=self.name,confidence=.4)
    class Second(OCR):
        name="second"
        def recognize(self,*args): return OCRResult(text="Totale 102",engine=self.name)
    monkeypatch.setattr(pipeline,"create_engine",lambda *args:Second())
    result=convert(pdf_fixtures["scan_it"],tmp_path/"review.docx",Settings(second_pass=True,second_engine="minicpm"),ocr_engine=OCR())
    model=json.loads(Path(result.model_path).read_text())
    region=next(r for r in model["pages"][0]["regions"] if r["source"]=="ocr")
    assert region["text"]=="Totale 1O2"
    assert region["alternatives"]["second"]=="Totale 102"
    assert any("Conflitto" in w for w in result.warnings)


def test_compare_retains_both_versions_without_assigning_winner(pdf_fixtures,tmp_path,monkeypatch):
    import pdf2docx_ai.pipeline as pipeline
    class OCR:
        def __init__(self,name): self.name=name
        def initialize(self): pass
        def shutdown(self): pass
        def recognize(self,*args): return OCRResult(text="Totale "+("100" if self.name=="xiaomi" else "200"),engine=self.name)
    monkeypatch.setattr(pipeline,"select_engine",lambda settings:OCR(settings.engine))
    result=compare(pdf_fixtures["scan_it"],tmp_path/"comparison.html")
    report=json.loads(Path(result.json_path).read_text())
    assert len(report["comparison"]["results"])==2
    assert report["comparison"]["conflicts"][0]["versions"]=={"xiaomi":"Totale 100","minicpm":"Totale 200"}
    assert "winner" not in report["comparison"]


def test_native_table_preserves_cell_font_and_bold(pdf_fixtures,tmp_path):
    result=convert(pdf_fixtures["table"],tmp_path/"table.docx")
    table=WordDocument(result.output_path).tables[0]
    runs=table.cell(0,0).paragraphs[0].runs
    assert any(r.font.size and r.font.size.pt==11 for r in runs)


def test_native_image_is_retained_if_auto_has_no_ocr(pdf_fixtures,tmp_path,monkeypatch):
    import pdf2docx_ai.pipeline as pipeline
    from pdf2docx_ai.ocr.base import OCRUnavailableError
    def missing(*args): raise OCRUnavailableError("No OCR installed")
    monkeypatch.setattr(pipeline,"select_engine",missing)
    result=convert(pdf_fixtures["image"],tmp_path/"image.docx")
    from docx.oxml.ns import qn
    assert len(list(WordDocument(result.output_path).element.iter(qn('pic:pic'))))>=1
    assert any("non modificabile" in warning for warning in result.warnings)


def test_empty_scan_ocr_is_an_explicit_error(pdf_fixtures,tmp_path):
    class Empty:
        def initialize(self): pass
        def shutdown(self): pass
        def recognize(self,*args): return OCRResult(text="",engine="empty")
    with pytest.raises(RuntimeError,match="nessun testo"):
        convert(pdf_fixtures["scan_it"],tmp_path/"empty.docx",ocr_engine=Empty())
    assert not (tmp_path/"empty.docx").exists()


@pytest.mark.renderer
def test_font_substitution_does_not_wrap_source_title(pdf_fixtures,tmp_path):
    import pymupdf
    from pdf2docx_ai.quality.validator import find_renderer
    if not find_renderer(): pytest.skip("LibreOffice optional renderer unavailable")
    result=convert(pdf_fixtures["landscape"],tmp_path/"landscape.docx",Settings(validate_visual=True))
    rendered=Path(result.output_path).with_suffix(".work")/"rendered"/"landscape.pdf"
    with pymupdf.open(rendered) as pdf:
        lines=["".join(s["text"] for s in line["spans"]) for b in pdf[0].get_text("dict")["blocks"] if b["type"]==0 for line in b["lines"]]
    assert "Pagina orizzontale" in lines


def test_rotated_text_reconstructs_as_readable_flow(pdf_fixtures,tmp_path):
    result=convert(pdf_fixtures["rotated_crop"],tmp_path/"rotated.docx")
    paragraphs=[p for p in WordDocument(result.output_path).paragraphs if p.text.strip()]
    assert paragraphs[0].paragraph_format.left_indent.pt==0
    assert paragraphs[0].paragraph_format.right_indent.pt==0


def test_real_web_pipeline_produces_downloadable_editable_docx(pdf_fixtures,tmp_path):
    import time
    import io
    from fastapi.testclient import TestClient
    from pdf2docx_ai.web.app import create_app
    with TestClient(create_app(tmp_path),base_url="http://127.0.0.1") as client:
        response=client.post("/api/jobs",files={"file":("native.pdf",pdf_fixtures["native"].read_bytes(),"application/pdf")})
        assert response.status_code==202
        identifier=response.json()["id"]
        for _ in range(100):
            status=client.get(f"/api/jobs/{identifier}").json()
            if status["status"] in ("complete","failed"): break
            time.sleep(.02)
        assert status["status"]=="complete",status
        data=client.get(status["files"]["docx"]).content
        assert "Documento nativo italiano" in "\n".join(p.text for p in WordDocument(io.BytesIO(data)).paragraphs)

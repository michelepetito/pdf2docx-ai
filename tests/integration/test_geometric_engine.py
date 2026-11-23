"""Geometric regressions independent of the held-out complex corpus."""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZipFile

from docx import Document as WordDocument
from docx.oxml.ns import qn
from PIL import Image
import pymupdf
import pytest

from pdf2docx_ai.config import Settings
from pdf2docx_ai.document.models import OCRResult
from pdf2docx_ai.pdf.extractor import extract_page
from pdf2docx_ai.pdf.renderer import render_page
from pdf2docx_ai.pipeline import convert
from pdf2docx_ai.quality.validator import find_renderer


class EmptyImageOCR:
    """A non-text native picture remains a picture; no heavyweight runtime."""
    name="empty-image-test"
    def initialize(self): pass
    def shutdown(self): pass
    def recognize(self,*args): return OCRResult(text="",engine=self.name)


def _word_text(word):
    parts=[word.element]
    for part in word.part.package.parts:
        if ("/header" in str(part.partname) or "/footer" in str(part.partname)) and hasattr(part,"element"):
            parts.append(part.element)
    return " ".join(node.text or "" for part in parts for node in part.iter(qn("w:t")))


@pytest.mark.parametrize("rotation,cropped",[(0,False),(0,True),(90,True),(180,True),(270,True)])
def test_native_baselines_follow_crop_and_display_transform_without_changing_advance(tmp_path,rotation,cropped):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=640,height=900)
        page.insert_text((90,140),"Coordinate native",fontsize=16)
        if cropped: page.set_cropbox(pymupdf.Rect(40,50,600,850))
        page.set_rotation(rotation)
        cropbox=tuple(page.cropbox)
        raw=next(s for b in page.get_text("dict")["blocks"] if b["type"]==0 for l in b["lines"] for s in l["spans"])
        expected=pymupdf.Point(raw["origin"])*page.rotation_matrix
        image,transform=render_page(page,72)
        model=extract_page(page,1,image,transform,tmp_path)
        image.close()
        line=next(line for region in model.regions for line in region.lines if line.text=="Coordinate native")
        span=line.spans[0]
        assert tuple(page.cropbox)==cropbox
        assert line.baseline==pytest.approx((expected.x,expected.y),abs=.001)
        assert span.baseline==pytest.approx(line.baseline,abs=.001)
        assert span.ascender>0 and span.descender<0
        # Horizontal glyph advances are font metrics, not the displayed bbox
        # width, which becomes a line's height at 90/270 degree page rotation.
        assert span.advance_width==pytest.approx(raw["bbox"][2]-raw["bbox"][0],abs=.01)


def test_same_baseline_date_and_role_use_word_tabs_without_layout_table(tmp_path):
    source=tmp_path/"date-fields.pdf"
    with pymupdf.open() as pdf:
        page=pdf.new_page()
        page.insert_text((60,90),"2020 - 2024",fontsize=11)
        page.insert_text((190,90),"Responsabile digitale",fontsize=11)
        page.insert_text((190,115),"Laboratorio di prova",fontsize=11)
        pdf.save(source)
    result=convert(source,tmp_path/"date-fields.docx",Settings(optimize_layout=False))
    word=WordDocument(result.output_path)
    assert not word.tables
    paragraph=next(p for p in word.paragraphs if "2020 - 2024" in p.text)
    assert "Responsabile digitale" in paragraph.text
    assert "\t" in paragraph.text
    assert paragraph._p.xpath("./w:pPr/w:tabs/w:tab")
    assert not word.element.xpath("//w:txbxContent")
    assert _word_text(word).count("Responsabile digitale")==1


def test_jpeg_bytes_and_page_anchor_are_preserved(tmp_path):
    stream=BytesIO();Image.new("RGB",(160,120),(50,110,170)).save(stream,format="JPEG",quality=91)
    jpeg=stream.getvalue();source=tmp_path/"native-jpeg.pdf"
    with pymupdf.open() as pdf:
        page=pdf.new_page()
        page.insert_text((60,65),"Immagine autonoma e testo nativo",fontsize=12)
        page.insert_image(pymupdf.Rect(230,100,390,220),stream=jpeg)
        assert pdf.extract_image(page.get_images()[0][0])["image"]==jpeg
        pdf.save(source)
    result=convert(source,tmp_path/"native-jpeg.docx",Settings(optimize_layout=False),ocr_engine=EmptyImageOCR())
    word=WordDocument(result.output_path)
    anchors=word.element.xpath("//wp:anchor[.//pic:pic]")
    assert len(anchors)==1
    assert not word.element.xpath("//wp:inline")
    assert int(anchors[0].xpath("./wp:positionH/wp:posOffset")[0].text)==230*12700
    assert int(anchors[0].xpath("./wp:positionV/wp:posOffset")[0].text)==100*12700
    with ZipFile(result.output_path) as package:
        assert jpeg in [package.read(name) for name in package.namelist() if name.startswith("word/media/")]
    report=json.loads(Path(result.json_path).read_text())
    assert report["structural"]["source_image_assets_preserved_bytes"]==1
    assert not report["structural"]["raster_only_editable_document"]


def test_adobe_cmyk_jpeg_is_decoded_at_source_resolution_for_word(tmp_path):
    stream=BytesIO();Image.new('CMYK',(160,120),(0,100,70,0)).save(stream,format='JPEG')
    source=tmp_path/'adobe-jpeg.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page();p.insert_text((50,70),'Native picture compatibility',fontsize=12)
        xref=p.insert_image(pymupdf.Rect(50,100,210,220),stream=stream.getvalue())
        # insert_image normalizes this header; restore the valid Adobe stream
        # to exercise PDFs produced by other writers without that normalization.
        pdf.update_stream(xref,stream.getvalue(),compress=False)
        pdf.xref_set_key(xref,'Filter','/DCTDecode')
        pdf.xref_set_key(xref,'ColorSpace','/DeviceCMYK')
        pdf.save(source)
    result=convert(source,tmp_path/'adobe-jpeg.docx',Settings(optimize_layout=False),ocr_engine=EmptyImageOCR())
    model=json.loads(Path(result.model_path).read_text())
    picture=next(r for r in model['pages'][0]['regions'] if r['kind']=='image')
    assert picture['metadata']['native_image_bytes'] is False
    with Image.open(picture['image_path']) as decoded:
        assert decoded.format=='PNG' and decoded.size==(160,120)
    assert Path(picture['image_path']).with_suffix('.jpeg').is_file()
    assert len(WordDocument(result.output_path).element.xpath('//pic:pic'))==1
    assert any('compatibilità DOCX' in warning for warning in result.warnings)


@pytest.mark.renderer
def test_normalized_vertical_text_does_not_wrap_into_character_fragments(pdf_fixtures,tmp_path):
    if not find_renderer():pytest.skip('Optional LibreOffice renderer unavailable')
    result=convert(pdf_fixtures['rotated_crop'],tmp_path/'readable-rotation.docx',Settings(resume=False))
    report=json.loads(Path(result.json_path).read_text())
    assert report['visual']['textual']['content_token_counts_equal']
    assert report['visual']['textual']['missing_words']==0
    assert report['visual']['page_count_difference']==0


@pytest.mark.parametrize("decorations",[False,True])
def test_drawingml_shapes_only_represent_actual_source_decoration(tmp_path,decorations):
    source=tmp_path/f"decoration-{decorations}.pdf"
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((60,75),"Contenuto modificabile",fontsize=12)
        if decorations:
            page.draw_line((60,100),(480,100),color=(.1,.3,.6),width=.8)
            page.draw_rect(pymupdf.Rect(60,130,220,150),fill=(.8,.9,.95),color=None)
        pdf.save(source)
    result=convert(source,tmp_path/f"decoration-{decorations}.docx",Settings(optimize_layout=False))
    word=WordDocument(result.output_path)
    shapes=word.element.xpath("//*[local-name()='wsp']")
    assert len(shapes)==(2 if decorations else 0)
    assert not word.element.xpath("//w:txbxContent")
    assert not word.tables
    assert _word_text(word)=="Contenuto modificabile"


def test_unicode_numeric_values_and_true_table_remain_editable(tmp_path):
    source=tmp_path/"unicode-table.pdf"
    expected="Città, qualità, perché: 1.234,56 euro; 16/11/2026"
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((50,80),expected,fontsize=11)
        xs,ys=[50,210,350,500],[120,150,180]
        for x in xs:page.draw_line((x,ys[0]),(x,ys[-1]))
        for y in ys:page.draw_line((xs[0],y),(xs[-1],y))
        values=[["Voce","Quantità","Importo"],["Analisi","2","1.234,56"]]
        for row,items in enumerate(values):
            for column,text in enumerate(items):page.insert_text((xs[column]+6,ys[row]+20),text,fontsize=10)
        native_words=Counter(page.get_text().split())
        pdf.save(source)
    result=convert(source,tmp_path/"unicode-table.docx",Settings(optimize_layout=False))
    word=WordDocument(result.output_path)
    assert expected in _word_text(word)
    assert len(word.tables)==1
    assert word.tables[0].cell(1,2).text=="1.234,56"
    assert word.tables[0].cell(0,1).text=="Quantità"
    assert Counter(_word_text(word).split())==native_words
    assert not word.element.xpath("//pic:pic|//w:txbxContent")


def _lines(page):
    result={}
    for block in page.get_text("dict")["blocks"]:
        if block["type"]!=0:continue
        for line in block["lines"]:
            text=" ".join("".join(s["text"] for s in line["spans"]).split())
            if text:result[text]=line["spans"][0]["origin"][1]
    return result


@pytest.mark.renderer
def test_sparse_columns_keep_native_x_and_do_not_carry_an_extra_line(pdf_fixtures,tmp_path):
    if not find_renderer():pytest.skip("Optional LibreOffice renderer unavailable")
    result=convert(pdf_fixtures['columns'],tmp_path/'sparse-columns.docx',Settings(resume=False))
    report=json.loads(Path(result.json_path).read_text());visual=report['visual']
    assert visual['page_count_difference']==0
    assert visual['mean_ssim']>.98
    assert visual['geometry']['p95_baseline_error_pt']<1
    assert visual['textual']['content_token_counts_equal']
    for page in visual['pages']:
        assert max(abs(m['dx_pt']) for m in page['line_matches'])<1


@pytest.mark.renderer
def test_rendered_header_and_footer_baselines_stay_within_two_points(pdf_fixtures,tmp_path):
    if not find_renderer():pytest.skip("Optional LibreOffice renderer unavailable")
    result=convert(pdf_fixtures["headers"],tmp_path/"header-baselines.docx",Settings(
        optimize_layout=True,max_layout_iterations=3,resume=False))
    report=json.loads(Path(result.json_path).read_text())
    assert report["visual"]["status"]=="measured"
    with pymupdf.open(pdf_fixtures["headers"]) as source,pymupdf.open(report["visual"]["rendered_pdf_path"]) as target:
        assert len(source)==len(target)==3
        for i in range(3):
            original,rendered=_lines(source[i]),_lines(target[i])
            for text in ("Rapporto aziendale",f"Pagina {i+1}"):
                assert text in original and text in rendered
                assert abs(original[text]-rendered[text])<=2


@pytest.mark.complex
@pytest.mark.skipif(os.environ.get("PDF2DOCX_COMPLEX")!="1",reason="Enable the development CV regression explicitly")
def test_development_european_cv_is_structured_and_text_complete(tmp_path):
    # Deliberately read only the development CV; held-out corpus is untouched.
    source=Path(__file__).parents[1]/"fixtures/complex/generated/europass_fictitious.reference.pdf"
    if not source.is_file():pytest.skip("Generate the complex source CV first")
    result=convert(source,tmp_path/"cv-regression.docx",Settings(optimize_layout=True,max_layout_iterations=3,resume=False),ocr_engine=EmptyImageOCR())
    report=json.loads(Path(result.json_path).read_text())
    assert report["structural"]["native_word_tables"]==1
    assert report["structural"]["picture_count"]==1
    assert report["structural"]["text_box_count"]==0
    assert report["structural"]["missing_source_token_count"]==0
    assert report["structural"]["source_image_assets_preserved_bytes"]==1
    assert report["visual"]["page_count_difference"]==0
    assert report["visual"]["textual"]["cer"]==0
    assert report["visual"]["geometry"]["median_baseline_error_pt"]<=2

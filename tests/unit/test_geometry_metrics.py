"""Metrics must expose missing content, outliers and typography independently."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

from pdf2docx_ai.quality.metrics import text_metrics
from pdf2docx_ai.quality.reporting import write_report
from pdf2docx_ai.quality.visual_diff import compare_pdfs,evaluate_pdf_pair


def make_pdf(path,pages,*,font="helv",image=None):
    with pymupdf.open() as document:
        for items in pages:
            page=document.new_page(width=420,height=595)
            for text,x,y in items:
                page.insert_text((x,y),text,fontname=font,fontsize=12)
            if image:
                payload,rectangle=image
                page.insert_image(rectangle,stream=payload)
        document.save(path)
    return path


def test_identical_pdf_has_complete_geometry_and_content(tmp_path):
    source=make_pdf(tmp_path/"same.pdf",[[('Città utile 12345',50,80)]])
    report=evaluate_pdf_pair(source,source)
    assert report['mean_ssim']==pytest.approx(1)
    assert report['foreground']['foreground_ssim']==pytest.approx(1)
    assert report['geometry']['match_coverage']==1
    assert report['geometry']['median_position_error_pt']==0
    assert report['geometry']['median_baseline_error_pt']==0
    assert report['geometry']['mean_iou']==1
    assert report['textual']['cer']==0
    assert report['textual']['missing_words']==0
    line=report['pages'][0]['line_matches'][0]
    assert line['source_baseline']==pytest.approx([50,80])
    assert line['target_baseline']==pytest.approx([50,80])
    assert line['source_font']=='Helvetica'


def test_translation_is_not_hidden_by_visual_registration(tmp_path):
    source=make_pdf(tmp_path/"source.pdf",[[('Alpha beta',50,80)]])
    target=make_pdf(tmp_path/"target.pdf",[[('Alpha beta',60,86)]])
    report=evaluate_pdf_pair(source,target)
    assert report['geometry']['median_position_error_pt']==pytest.approx((10**2+6**2)**.5,abs=.001)
    assert report['geometry']['median_baseline_error_pt']==pytest.approx(6)
    assert report['pages'][0]['alignment_shift_px']==[0,0]
    assert report['mean_ssim']>report['foreground']['foreground_ssim']+.1
    assert report['foreground']['ink_f1']<1
    assert report['textual']['cer']==0


def test_font_ascender_change_is_not_mislabelled_as_baseline_drift(tmp_path):
    source=make_pdf(tmp_path/"helvetica.pdf",[[('Font metriche',50,80)]],font='helv')
    target=make_pdf(tmp_path/"times.pdf",[[('Font metriche',50,80)]],font='tiro')
    report=evaluate_pdf_pair(source,target)
    assert report['geometry']['median_baseline_error_pt']==0
    assert report['geometry']['median_position_error_pt']>0
    assert report['geometry']['median_width_error_pt']>0
    line=report['pages'][0]['line_matches'][0]
    assert line['source_font']!=line['target_font']


def test_repeated_tokens_match_one_to_one_and_excess_is_visible(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Ripeti 123',50,80),('Ripeti 123',50,140)]])
    target=make_pdf(tmp_path/'target.pdf',[[('Ripeti 123',50,80),('Ripeti 123',50,140),('Ripeti 123',50,200)]])
    report=evaluate_pdf_pair(source,target)
    matches=report['pages'][0]['word_matches']
    assert len(matches)==4
    assert len({tuple(m['target_bbox']) for m in matches})==4
    assert report['geometry']['median_position_error_pt']==0
    assert report['textual']['excess_words']==2
    assert report['textual']['potential_duplicate_words']==2
    assert report['textual']['content_token_counts_equal'] is False


def test_altered_number_and_date_are_separate_from_geometry(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Data 12/03/2026 Totale +12345',50,80)]])
    target=make_pdf(tmp_path/'target.pdf',[[('Data 12/04/2026 Totale +12346',50,80)]])
    report=evaluate_pdf_pair(source,target)
    assert report['textual']['missing_words']==2
    assert report['textual']['numbers_dates']['missing_count']==2
    assert report['textual']['numbers_dates']['excess_count']==2
    assert report['geometry']['match_coverage']==.5


def test_missing_page_remains_in_metrics_and_visual_report(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Prima pagina',50,80)],[('Seconda unica',50,80)]])
    target=make_pdf(tmp_path/'target.pdf',[[('Prima pagina',50,80)]])
    report=evaluate_pdf_pair(source,target)
    assert report['page_count_difference']==-1
    assert len(report['pages'])==2
    assert report['pages'][1]['target_page_missing'] is True
    assert report['pages'][1]['ssim']<1
    assert report['textual']['missing_words']==2
    assert report['geometry']['unmatched_source_words']==2


def test_text_moved_to_another_page_is_counted_as_page_drift(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Unico trasferito',50,80)],[]])
    target=make_pdf(tmp_path/'target.pdf',[[],[('Unico trasferito',50,80)]])
    report=evaluate_pdf_pair(source,target)
    assert report['page_count_difference']==0
    assert report['geometry']['page_drift_words']==2
    assert report['geometry']['match_coverage']==1
    assert report['geometry']['median_position_error_pt'] is None
    assert all(p['geometry']['unmatched_target_words']>=0 for p in report['pages'])


def test_rewrapped_line_retains_diagnostic_word_and_baseline_matches(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Alpha beta gamma delta',50,80)]])
    target=make_pdf(tmp_path/'target.pdf',[[('Alpha beta',50,80),('gamma delta',50,96)]])
    report=evaluate_pdf_pair(source,target)
    assert report['geometry']['matched_words']==4
    assert report['geometry']['p95_baseline_error_pt']==pytest.approx(16)
    assert report['pages'][0]['line_matches'][0]['target_wrap_lines']==2
    assert report['textual']['content_token_counts_equal'] is True


def test_line_split_across_pages_does_not_provide_false_correction_baseline(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('Alpha beta gamma delta',50,80)]])
    target=make_pdf(tmp_path/'target.pdf',[[('Alpha beta',50,80)],[('gamma delta',50,80)]])
    report=evaluate_pdf_pair(source,target)
    assert report['geometry']['page_drift_words']==2
    assert report['pages'][0]['line_matches']==[]


def test_rotation_crop_and_table_measurement_do_not_mutate_pdf(tmp_path):
    source=tmp_path/'rotated.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=640,height=900)
        page.insert_text((90,140),'Testo ruotato',fontsize=12)
        page.set_cropbox(pymupdf.Rect(40,50,600,850));page.set_rotation(90)
        pdf.save(source)
    original=source.read_bytes()
    report=compare_pdfs(source,source,tmp_path/'assets')
    assert source.read_bytes()==original
    assert report['geometry']['median_position_error_pt']==0
    assert report['geometry']['median_baseline_error_pt']==0
    assert report['pages'][0]['original_size_pt']==[800,560]
    assert report['pages'][0]['line_matches'][0]['source_baseline']==pytest.approx([710,50])
    assert report['pages'][0]['original_detected_tables'] is None


def test_image_hash_geometry_and_scanned_text_accuracy_are_distinguished(tmp_path):
    stream=BytesIO();Image.new('RGB',(30,40),'red').save(stream,format='PNG')
    source=make_pdf(tmp_path/'source.pdf',[[]],image=(stream.getvalue(),pymupdf.Rect(50,80,100,140)))
    target=make_pdf(tmp_path/'target.pdf',[[]],image=(stream.getvalue(),pymupdf.Rect(55,80,105,140)))
    report=evaluate_pdf_pair(source,target,include_images=True)
    assert report['images']['matched_images']==1
    assert report['images']['matches'][0]['method']=='decoded_pixel_digest'
    assert report['images']['matches'][0]['position_error_pt']==5
    assert report['textual']['status']=='unavailable_no_source_text'
    assert report['textual']['cer'] is None


def test_self_contained_report_contains_evolution_heatmap_and_coordinates(tmp_path):
    source=make_pdf(tmp_path/'source.pdf',[[('<script> Alpha',50,80)]])
    target=make_pdf(tmp_path/'target.pdf',[[('<script> Alpha',55,83)]])
    visual=compare_pdfs(source,target,tmp_path/'assets')
    report={'source':'<script>source','mode':'editable','pages':1,'visual':visual,
            'optimization':{'status':'converged','algorithm':'bounded coordinate descent','best_iteration':1,
                            'history':[{'iteration':1,'objective':.1,'accepted':True,'ssim':visual['mean_ssim']}],
                            'before':visual,'after':visual}}
    destination=tmp_path/'report.html';write_report(report,destination)
    html=destination.read_text()
    assert 'Heatmap differenze' in html
    assert 'Coordinate delle righe' in html
    assert "Prima e dopo pagina" in html
    assert "Ottimizzazione del layout" in html
    assert 'data:image/jpeg;base64,' in html
    assert '&lt;script&gt;' in html
    assert '<script>' not in html


def test_renderer_does_not_reuse_stale_pdf_after_failed_render(tmp_path,monkeypatch):
    from pdf2docx_ai.quality import validator
    work=tmp_path/'work';(work/'rendered').mkdir(parents=True)
    stale=work/'rendered'/'input.pdf';stale.write_bytes(b'stale')
    monkeypatch.setattr(validator,'find_renderer',lambda renderer:'fake-soffice')
    monkeypatch.setattr(validator.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='',stderr=''))
    result=validator.render_docx_to_pdf(tmp_path/'input.docx',work)
    assert result['status']=='failed'
    assert not stale.exists()


def test_long_identical_or_nearly_identical_native_text_has_exact_distance():
    reference='x'*100_000+'fine'
    assert text_metrics(reference,reference)['cer']==0
    assert text_metrics(reference,'x'*100_000+'fina')['cer']==pytest.approx(1/100_004)


def test_structural_editability_does_not_split_words_at_style_run_boundaries(tmp_path):
    from docx import Document as WordDocument
    from pdf2docx_ai.document.models import BBox,Document,Page,Region
    from pdf2docx_ai.quality.validator import structural_validation
    bounds=BBox(x0=0,y0=0,x1=420,y1=595)
    region=Region(page_number=1,bbox=BBox(x0=50,y0=60,x1=150,y1=80),text='Documento')
    model=Document(source_path='synthetic.pdf',source_sha256='test',pages=[Page(
        number=1,width=420,height=595,cropbox=bounds,classification='native',regions=[region])])
    word=WordDocument();paragraph=word.add_paragraph();paragraph.add_run('Docu').bold=True;paragraph.add_run('mento')
    path=tmp_path/'styles.docx';word.save(path)
    result=structural_validation(path,model,'editable')
    assert result['editable_characters']==9
    assert result['missing_source_token_count']==0
    assert result['text_box_count']==0
    assert result['additional_word_tables']==0


def test_structural_image_assets_are_byte_preserved_in_docx(tmp_path):
    from docx import Document as WordDocument
    from pdf2docx_ai.document.models import BBox,Document,Page,Region
    from pdf2docx_ai.quality.validator import structural_validation
    image=tmp_path/'original.png';Image.new('RGB',(20,30),'blue').save(image)
    bounds=BBox(x0=0,y0=0,x1=420,y1=595)
    region=Region(page_number=1,bbox=BBox(x0=50,y0=60,x1=70,y1=90),kind='image',image_path=str(image))
    model=Document(source_path='synthetic.pdf',source_sha256='test',pages=[Page(
        number=1,width=420,height=595,cropbox=bounds,classification='native',regions=[region])])
    word=WordDocument();word.add_picture(str(image));path=tmp_path/'image.docx';word.save(path)
    result=structural_validation(path,model,'editable')
    assert result['source_image_assets_checked']==1
    assert result['source_image_assets_preserved_bytes']==1
    assert result['raster_only_editable_document'] is True

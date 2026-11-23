from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pymupdf
import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

from pdf2docx_ai.quality.metrics import edit_distance,text_metrics
from pdf2docx_ai.quality.textual import analyze_text,normalize_text
from pdf2docx_ai.quality.units import MM_PER_PT
from pdf2docx_ai.quality.geometry_metrics import CATEGORIES,extract_elements,compare_elements
from pdf2docx_ai.quality.structure import audit_docx
from pdf2docx_ai.quality.assessment import _compare_regression,persist_assessment,assess_conversion
from pdf2docx_ai.quality.visual_diff import evaluate_pdf_pair
from pdf2docx_ai.quality.reporting import write_report


def word(text,x=50,y=80,index=0,page=1):
    return {'id':f'{page}:word:{index}','text':text,'page':page,'index':index,'bbox':[x,y,x+40,y+12],
            'line_id':f'{page}:line:{index}','baseline':[x,y+10]}


@pytest.mark.parametrize('a,b,expected', [('kitten','sitting',3),('città','citta',1),('','abc',3),('abc','',3),(['one','two'],['one','too'],1)])
def test_exact_distance_keeps_reference_denominator_and_unicode(a,b,expected):
    assert edit_distance(a,b)==expected


def test_exact_cer_works_beyond_the_previous_quadratic_guard():
    a='a'*20000+'1';b='b'+'a'*20000
    assert edit_distance(a,b)==2
    assert text_metrics(a,b)['cer']==pytest.approx(2/20001)


def test_typographic_normalization_is_explicit_and_preserves_values():
    source=[word('citta\u0300'),word('ﬁnanziaria',110,index=1),word('12\u00a0345',210,index=2)]
    target=[word('città'),word('finanziaria',110,index=1),word('12 345',210,index=2)]
    result=analyze_text(source,target)
    assert result['strict_stream']['cer']>0
    assert result['normalized_stream']['cer']==0
    assert result['normalization_only_difference']
    assert normalize_text('m² − 3; 16/11/2026')=='m² − 3; 16/11/2026'
    assert normalize_text('m²')!=normalize_text('m2')
    assert normalize_text('Città')!=normalize_text('citta')


def test_a_small_numeric_change_is_not_hidden_by_tiny_global_cer():
    source=[word('a'*6000),word('16/11/2026',200,index=1)]
    target=[word('a'*6000),word('16/11/2027',200,index=1)]
    result=analyze_text(source,target)
    assert 0<result['normalized_stream']['cer']<.001
    assert result['numbers_dates']['missing_count']==1
    assert result['numbers_dates']['added_count']==1
    assert result['numbers_dates']['missing_locations'][0]['bbox_mm'][0]==pytest.approx(200*MM_PER_PT)
    assert result['sequence_edit_count']==1
    assert result['sequence_edit_locations'][0]['source']['page']==1


def test_repeated_missing_number_is_localized_by_identity_and_position():
    source=[word('123',y=80),word('123',y=140,index=1)]
    result=analyze_text(source,[word('123',y=80)])
    assert result['numbers_dates']['missing_locations'][0]['bbox_pt'][1]==140
    assert result['potential_duplicate_token_count']==0
    dup=analyze_text([word('123',y=80)],source)
    assert dup['potential_duplicate_token_count']==1
    assert dup['potential_duplicate_locations'][0]['bbox_pt'][1]==140


def test_reading_order_is_reported_without_inventing_character_loss():
    source=[word('Alpha'),word('Beta',y=100,index=1),word('Gamma',y=120,index=2)]
    target=[source[2],source[1],source[0]]
    r=analyze_text(source,target)
    assert r['missing_characters']==r['added_characters']==0
    assert r['normalized_stream']['cer']>0
    assert r['stream_order']['inversions']==3
    assert r['sequence_error_interpretation']=='order_or_tokenization'


def _pdf(path,shift=0):
    with pymupdf.open() as pdf:
        for n in range(2):
            p=pdf.new_page(width=600,height=800)
            p.insert_text((50+shift,25),'Company report 2026',fontsize=10)
            p.insert_text((50+shift,775),f'Page {n+1}',fontsize=10)
            for i in range(5):
                p.insert_text((50+shift,120+i*18),'Left column contains measured text',fontsize=10)
                p.insert_text((320+shift,120+i*18),'Right column contains measured text',fontsize=10)
            xs=[50+shift,210+shift,370+shift];ys=[310,340,370]
            for x in xs:p.draw_line((x,ys[0]),(x,ys[-1]))
            for y in ys:p.draw_line((xs[0],y),(xs[-1],y))
            for r in range(2):
                for c in range(2):p.insert_text((xs[c]+5,ys[r]+20),f'Cell {r} {c}',fontsize=10)
            import io
            buf=io.BytesIO();Image.new('RGB',(90,60),'steelblue').save(buf,format='PNG')
            p.insert_image(pymupdf.Rect(400+shift,400,490+shift,460),stream=buf.getvalue())
        pdf.save(path)
    return path


def test_all_categories_are_measured_in_points_and_mm(tmp_path):
    a=extract_elements(_pdf(tmp_path/'a.pdf'));b=extract_elements(_pdf(tmp_path/'b.pdf',shift=10))
    report=compare_elements(a,b)
    assert set(report['categories'])==set(CATEGORIES)
    for key,category in report['categories'].items():
        z=category['summary']
        assert z['source_elements']>0,key
        assert z['source_coverage']==1,key
        assert z['mean_position_error_pt']==pytest.approx(10,abs=.02),key
        assert z['median_position_error_mm']==pytest.approx(10*MM_PER_PT,abs=.01),key
        assert z['p95_position_error_mm']==pytest.approx(10*MM_PER_PT,abs=.01),key
    assert len(a['logical_words'])==len(a['words'])
    assert len({w['id'] for w in a['logical_words']})==len(a['words'])
    assert a['pages'][0]['inferred_columns']==2
    assert report['margins']['pages'][0]['absolute_error_mm']['left']==pytest.approx(10*MM_PER_PT,abs=.01)


def test_missing_elements_have_no_fake_perfect_iou(tmp_path):
    source=extract_elements(_pdf(tmp_path/'a.pdf'))
    with pymupdf.open() as p:p.new_page(width=600,height=800);p.save(tmp_path/'blank.pdf')
    target=extract_elements(tmp_path/'blank.pdf');r=compare_elements(source,target)
    assert r['categories']['paragraphs']['summary']['source_coverage']==0
    assert r['categories']['paragraphs']['summary']['mean_iou'] is None
    assert r['layout']['difference_count']>=1


def test_fragmented_paragraph_is_not_hidden_by_union_iou():
    ww=[word('Alpha'),word('Beta',y=100,index=1)]
    def data(records):
        return {'words':ww,'images':[],'pages':[{'page':1,'width_pt':600,'height_pt':800,'table_detection':'measured_native_grids','inferred_columns':1,'visible_body_margins_pt':None}],
                'word_columns':{},'elements':{**{k:[] for k in CATEGORIES},'paragraphs':records}}
    source=data([{'id':'a','page':1,'bbox':[50,80,90,112],'text':'Alpha Beta','word_ids':[w['id'] for w in ww]}])
    target=data([{'id':str(i),'page':1,'bbox':w['bbox'],'text':w['text'],'word_ids':[w['id']]} for i,w in enumerate(ww)])
    z=compare_elements(source,target)['categories']['paragraphs']['summary']
    assert z['mean_iou']==1
    assert z['split_source_elements']==1


def test_inherited_hidden_text_does_not_count_as_editable(tmp_path):
    path=tmp_path/'hidden.docx';d=Document();d.styles['Normal'].font.hidden=True;d.add_paragraph('Hidden native content');d.save(path)
    audit=audit_docx(path)
    assert audit['hidden_characters']>=len('Hidden native content')
    assert audit['visible_nonwhitespace_characters']==0


def test_protection_invisible_tables_and_native_properties_are_audited(tmp_path):
    p=tmp_path/'layout.docx';d=Document();para=d.add_paragraph('Ordinary paragraph\twith a tab')
    para.paragraph_format.left_indent=12700*12
    tab=d.add_table(rows=1,cols=1);tab.cell(0,0).text='Layout only'
    borders=OxmlElement('w:tblBorders')
    for side in ('top','bottom','left','right','insideH','insideV'):
        node=OxmlElement('w:'+side);node.set(qn('w:val'),'nil');borders.append(node)
    tab._tbl.tblPr.append(borders)
    protection=OxmlElement('w:documentProtection');protection.set(qn('w:enforcement'),'1');protection.set(qn('w:edit'),'readOnly');d.settings.element.append(protection);d.save(p)
    model=SimpleNamespace(pages=[SimpleNamespace(regions=[])])
    audit=audit_docx(p,model)
    assert audit['unverified_additional_tables']==1
    assert audit['explicitly_invisible_tables']==1
    assert audit['document_protection_enforced']
    assert audit['tabs']==1 and audit['indented_paragraphs']>0


def _assessment(ssim=.99,cer=0,median=.1,p95=.2):
    return {'assessment_id':'a'*64,'inputs':{'source_sha256':'b'*64},'methodology':{'renderer':'same renderer'},
            'dimensions':{'visual':{'mean_ssim':ssim,'minimum_page_ssim':ssim},'textual':{'primary':{'cer':cer,'wer':cer},'missing_characters':0,'added_characters':0},
                'geometry':{'word_summary':{'median_position_error_mm':median,'p95_position_error_mm':p95},'page_count_difference':0},
                'structure':{'raster_pages':{'suspected_replacement_count':0},'audit':{'hidden_characters':0,'unverified_additional_tables':0}}}}


def test_ssim_gain_cannot_hide_text_or_geometry_regression():
    old=_assessment();new=_assessment(ssim=.999,cer=.01,p95=3)
    result=_compare_regression(old,new)
    assert result['tradeoff']
    assert {'cer','wer','p95_geometry_mm'}<={x['metric'] for x in result['regressions']}
    new['inputs']['source_sha256']='other'
    with pytest.raises(ValueError,match='same source'):_compare_regression(old,new)


def test_history_preserves_previous_observation(tmp_path):
    item=_assessment();path=Path(persist_assessment(item,tmp_path));before=path.read_bytes()
    changed=deepcopy(item);changed['created_utc']='changed';persist_assessment(changed,tmp_path)
    assert path.read_bytes()==before


def test_visual_gain_cannot_hide_a_structural_regression_or_changed_reference():
    old=_assessment();new=_assessment(ssim=.999)
    old['dimensions']['structure']['audit']['text_box_count']=0
    new['dimensions']['structure']['audit']['text_box_count']=12
    new['dimensions']['textual']['primary']['reference']='external ground truth'
    new['inputs']['ground_truth_sha256']='c'*64
    result=_compare_regression(old,new)
    assert result['tradeoff']
    assert any(x['metric']=='textboxes' for x in result['regressions'])
    assert result['text_reference_changed']
    assert 'cer' in result['non_comparable_metrics']
    assert not any(x['metric']=='cer' for x in result['changes'])


def test_overwrite_archive_only_follows_known_verified_artifacts(tmp_path):
    from pdf2docx_ai.quality.history import archive_existing
    from hashlib import sha256
    word=tmp_path/'known.docx';word.write_bytes(b'known artifact')
    hidden=tmp_path/'unrelated.docx';hidden.write_bytes(b'unrelated')
    report=tmp_path/'previous.json';old=_assessment()
    old['inputs']['docx_sha256']=sha256(word.read_bytes()).hexdigest();old['inputs']['docx']=str(hidden)
    report.write_text(json.dumps(old))
    archive_existing(report,tmp_path/'history',docx=word)
    copied=list((tmp_path/'history').rglob('artifact.docx'))
    assert len(copied)==1 and copied[0].read_bytes()==b'known artifact'
    assert hidden.read_bytes()==b'unrelated'


def test_legacy_metrics_are_not_falsely_compared_to_new_references():
    old={'source_sha256':'b'*64,'visual':{'mean_ssim':.99,'textual':{'cer':.3}}}
    r=_compare_regression(old,_assessment())
    assert r['status']=='legacy_schema_not_directly_comparable'
    assert not r['regressions']


def test_worst_page_does_not_disappear_in_global_visual_mean(tmp_path):
    pdf=tmp_path/'source.pdf';_pdf(pdf)
    docx=tmp_path/'ordinary.docx';d=Document();d.add_paragraph('Visible ordinary text');d.save(docx)
    visual=evaluate_pdf_pair(pdf,pdf,include_images=True);visual.update(rendered_pdf_path=str(pdf),renderer='test')
    visual['mean_ssim']=.995;visual['pages'][0]['ssim']=.999;visual['pages'][1]['ssim']=.90
    a,_=assess_conversion(pdf,docx,tmp_path/'work',visual=visual)
    assert a['target_checks']['visual_document_ssim']['status']=='met'
    assert a['target_checks']['visual_every_page_ssim']['status']=='not_met'
    assert a['dimensions']['visual']['pages_below_target']==[2]
    assert a['composite_score'] is None
    report=tmp_path/'report.html';write_report({'source':'<script>bad()</script>','visual':visual,'assessment':a},report)
    text=report.read_text();assert '<script>bad()</script>' not in text
    assert 'Validazione in quattro dimensioni' in text


def test_missing_renderer_is_unavailable_not_zero_error(tmp_path):
    source=tmp_path/'source.pdf'
    with pymupdf.open() as p:p.new_page();p.save(source)
    docx=tmp_path/'x.docx';d=Document();d.add_paragraph('Visible');d.save(docx)
    a,_=assess_conversion(source,docx,tmp_path/'work',visual={'status':'unavailable','reason':'no renderer'})
    assert a['target_checks']['visual_document_ssim']['status']=='unavailable'
    assert a['target_checks']['geometry_median_mm']['status']=='unavailable'
    assert a['target_checks']['text_cer']['status']=='unavailable'


def test_native_reference_does_not_count_correct_ocr_as_added_errors(tmp_path):
    from pdf2docx_ai.document.models import Document as Model,Page,Region,BBox
    source=tmp_path/'partial.pdf';_pdf(source)
    docx=tmp_path/'mixed.docx';d=Document();d.add_paragraph('Native and OCR content');d.save(docx)
    region=Region(page_number=1,source='ocr',text='OCR content',bbox=BBox(x0=50,y0=100,x1=200,y1=120))
    model=Model(source_path=str(source),source_sha256='test',pages=[Page(number=1,width=595,height=842,classification='mixed',cropbox=BBox(x0=0,y0=0,x1=595,y1=842),regions=[region])])
    visual=evaluate_pdf_pair(source,source,include_images=True);visual.update(rendered_pdf_path=str(source),renderer='test')
    a,_=assess_conversion(source,docx,tmp_path/'work',model=model,visual=visual)
    text=a['dimensions']['textual']
    assert text['primary']['cer'] is None and text['primary']['wer'] is None
    assert text['missing_characters'] is None and text['added_characters'] is None
    assert text['native_reference_diagnostics']['primary']['cer']==0
    assert a['target_checks']['text_cer']['status']=='unavailable'

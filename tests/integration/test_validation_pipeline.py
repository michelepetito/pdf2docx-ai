from pathlib import Path
from hashlib import sha256
import json,os
import pymupdf
import pytest
from docx import Document
from docx.shared import Pt,RGBColor
from typer.testing import CliRunner
from pdf2docx_ai.cli import app
from pdf2docx_ai.config import Settings
from pdf2docx_ai.pipeline import convert
from pdf2docx_ai.quality.assessment import assess_conversion
from pdf2docx_ai.quality.validator import find_renderer
from pdf2docx_ai.reconstruction.ooxml import anchor_picture


@pytest.mark.renderer
def test_full_page_picture_with_tiny_editable_label_cannot_game_validation(tmp_path):
    if not find_renderer():pytest.skip('Local renderer required')
    source=tmp_path/'native.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=420,height=595)
        # Sparse ink makes the raster shortcut look almost perfect globally.
        for i in range(2):page.insert_text((50,80+i*24),f'Native editable content row {i+1}: total 12345',fontsize=11)
        page.get_pixmap(dpi=144,alpha=False).save(tmp_path/'screenshot.png');pdf.save(source)
    doc=Document();s=doc.sections[0];s.page_width=Pt(420);s.page_height=Pt(595)
    s.left_margin=s.right_margin=s.top_margin=s.bottom_margin=Pt(0)
    p=doc.add_paragraph();p.paragraph_format.line_spacing=Pt(1)
    run=p.add_run('label');run.font.size=Pt(1);run.font.color.rgb=RGBColor(255,255,255)
    pic=p.add_run().add_picture(str(tmp_path/'screenshot.png'),width=Pt(420),height=Pt(595));anchor_picture(pic._inline,0,0)
    fake=tmp_path/'fake.docx';doc.save(fake)
    a,v=assess_conversion(source,fake,tmp_path/'validation')
    assert v['mean_ssim']>.99
    assert a['dimensions']['structure']['audit']['visible_nonwhitespace_characters']>0
    assert a['target_checks']['no_page_raster_replacement']['status']=='not_met'
    assert a['target_checks']['text_cer']['status']=='not_met'


@pytest.mark.renderer
def test_conversion_pipeline_and_validate_cli_publish_four_dimensions(pdf_fixtures,tmp_path):
    if not find_renderer():pytest.skip('Local renderer required')
    output=tmp_path/'native.docx';result=convert(pdf_fixtures['native'],output,Settings(validate_editability=True,resume=False))
    report=json.loads(Path(result.json_path).read_text());a=report['assessment']
    assert set(a['dimensions'])=={'visual','textual','geometry','structure'}
    assert a['inputs']['docx']==str(output)
    assert a['dimensions']['structure']['edit_probe']['status']=='measured'
    assert Path(report['assessment_history_path']).is_file()
    before=sha256(output.read_bytes()).hexdigest()
    command=CliRunner().invoke(app,['validate',str(pdf_fixtures['native']),str(output),'--output',str(tmp_path/'validate.html'),'--no-edit-probe','--json'])
    assert command.exit_code==0,command.output
    assert Path(json.loads(command.stdout)['json_path']).is_file()
    assert sha256(output.read_bytes()).hexdigest()==before


@pytest.mark.complex
@pytest.mark.renderer
@pytest.mark.skipif(os.environ.get('PDF2DOCX_COMPLEX')!='1',reason='Enable mandatory development CV explicitly')
def test_europass_probe_keeps_original_and_all_content(tmp_path):
    root=Path(__file__).resolve().parents[2]
    source=root/'tests/fixtures/complex/generated/europass_fictitious.reference.pdf'
    target=root/'examples/output/reconstruction-review/deliverables/europass-geometric.docx'
    if not source.is_file() or not target.is_file():pytest.fail('Mandatory CV references must be prepared')
    before=sha256(target.read_bytes()).hexdigest()
    a,v=assess_conversion(source,target,tmp_path/'cv-validation',run_edit_probe=True)
    probe=a['dimensions']['structure']['edit_probe']
    assert probe['status']=='measured'
    assert probe['original_unchanged'] and probe['objects_preserved']
    assert probe['missing_baseline_characters']==0
    assert probe['rule_text_collisions']['introduced_count']>=2
    assert probe['outcome']=='layout_disruption_suspected'
    assert a['target_checks']['edit_probe_no_new_rule_collisions']['status']=='not_met'
    assert a['dimensions']['textual']['primary']['cer']==0
    assert a['dimensions']['geometry']['categories']['tables']['summary']['source_elements']==1
    assert sha256(target.read_bytes()).hexdigest()==before

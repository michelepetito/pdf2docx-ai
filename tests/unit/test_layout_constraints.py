"""Bounded optimizer and typography safety tests, without a Word renderer."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from docx import Document as WordDocument
from docx.oxml import OxmlElement
from docx.shared import Pt
from PIL import Image
import pytest
from typer.testing import CliRunner

from pdf2docx_ai.cli import app
from pdf2docx_ai.config import Settings
from pdf2docx_ai.document.models import BBox,Document,Page,Region,TextLine,TextSpan
from pdf2docx_ai.reconstruction import optimizer
from pdf2docx_ai.reconstruction.fonts import FontResolver


def _model():
    box=BBox(x0=60,y0=75,x1=260,y1=90)
    span=TextSpan(text="Totale 123",bbox=box,size=12,baseline=(60,86),advance_width=200)
    line=TextLine(text=span.text,bbox=box,baseline=span.baseline,spans=[span])
    region=Region(id="body",page_number=1,text=span.text,bbox=box,spans=[span],lines=[line])
    page=Page(number=1,width=595,height=842,cropbox=BBox(x0=0,y0=0,x1=595,y1=842),classification="native",regions=[region])
    return Document(source_path="synthetic.pdf",source_sha256="0"*64,pages=[page])


def _measurement(error,dx=0,foreground=.9):
    match=dict(source_page=1,target_page=1,source_bbox=[60,75,260,90],target_bbox=[60+dx,75+error,260+dx,90+error],
               dx_pt=dx,dy_pt=error,baseline_dy_pt=error,target_wrap_lines=1)
    return dict(geometry=dict(median_position_error_pt=abs(error),p95_position_error_pt=abs(error),
                             median_baseline_error_pt=abs(error),p95_baseline_error_pt=abs(error),matched_words=2,page_drift_words=0),
                foreground=dict(foreground_ssim=foreground),textual=dict(missing_characters=0,excess_characters=0,cer=0),
                page_count_difference=0,mean_ssim=.99,pages=[dict(page=1,line_matches=[match],word_matches=[match])])


def _initial(tmp_path):
    source=tmp_path/"original.docx";output=tmp_path/"output.docx"
    doc=WordDocument();doc.add_paragraph().add_run("Totale 123").font.size=Pt(12);doc.save(source)
    shutil.copy2(source,output)
    return source,output


def _mock_runtime(monkeypatch,measurements,original,mutation=None):
    seen={};calls=[]
    def render(candidate,folder,*args,**kwargs):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/"result.pdf";path.write_bytes(str(Path(candidate).resolve()).encode())
        return dict(status="rendered",pdf_path=str(path),renderer="test-double")
    def evaluate(source,pdf,*args,**kwargs):
        index=len(calls);calls.append(str(pdf))
        measured=deepcopy(measurements[min(index,len(measurements)-1)])
        seen[Path(pdf).read_bytes()]=measured
        return measured
    def compare(source,pdf,*args,**kwargs):return deepcopy(seen[Path(pdf).read_bytes()])
    class Builder:
        def __init__(self,**kwargs): pass
        def reconstruct(self,model,path,mode,adjustments):
            doc=WordDocument(original)
            if mutation=="text":doc.paragraphs[0].runs[0].text="Totale 999"
            elif mutation=="font_size":doc.paragraphs[0].runs[0].font.size=Pt(6)
            elif mutation=="table":doc.add_table(rows=1,cols=1)
            elif mutation=="textbox":doc.paragraphs[0]._p.append(OxmlElement("w:txbxContent"))
            elif mutation=="image":
                asset=Path(path).parent/"additional.png";Image.new("RGB",(10,10),"red").save(asset)
                doc.add_picture(str(asset))
            else:doc.paragraphs[0].paragraph_format.left_indent=Pt(adjustments.get("body",{}).get("left",0))
            doc.save(path)
            return {"builder":"test-double"}
    monkeypatch.setattr(optimizer,"render_docx_to_pdf",render)
    monkeypatch.setattr(optimizer,"evaluate_pdf_pair",evaluate)
    monkeypatch.setattr(optimizer,"compare_pdfs",compare)
    monkeypatch.setattr(optimizer,"DocumentReconstructionEngine",Builder)
    return calls


def test_optimizer_keeps_best_candidate_and_respects_iteration_limit(tmp_path,monkeypatch):
    original,output=_initial(tmp_path)
    _mock_runtime(monkeypatch,[_measurement(10),_measurement(8)],original)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/"source.pdf",output,tmp_path/"work",
                                         Settings(max_layout_iterations=1),{})
    assert len(report["history"])==2
    assert max(item["iteration"] for item in report["history"])==1
    assert report["best_iteration"]==1
    accepted=[item["objective"] for item in report["history"] if item["accepted"]]
    assert all(b<=a for a,b in zip(accepted,accepted[1:]))
    assert min(accepted)<=report["history"][0]["objective"]


def test_optimizer_does_not_replace_output_with_a_worse_trial(tmp_path,monkeypatch):
    original,output=_initial(tmp_path);before=hashlib.sha256(output.read_bytes()).hexdigest()
    _mock_runtime(monkeypatch,[_measurement(2),_measurement(20)],original)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/"source.pdf",output,tmp_path/"work",
                                         Settings(max_layout_iterations=1),{})
    assert report["best_iteration"]==0
    assert report["history"][-1]["accepted"] is False
    assert hashlib.sha256(output.read_bytes()).hexdigest()==before


def test_zero_iteration_limit_renders_only_initial_candidate(tmp_path,monkeypatch):
    original,output=_initial(tmp_path)
    calls=_mock_runtime(monkeypatch,[_measurement(10)],original)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/"source.pdf",output,tmp_path/"work",
                                         Settings(max_layout_iterations=0),{})
    assert len(calls)==1
    assert len(report["history"])==1
    assert report["best_iteration"]==0


def test_font_trial_cannot_trade_foreground_fidelity_for_lower_position_error(tmp_path,monkeypatch):
    original,output=_initial(tmp_path);before=hashlib.sha256(output.read_bytes()).hexdigest()
    _mock_runtime(monkeypatch,[_measurement(2,foreground=.9),_measurement(0,foreground=.6)],original)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/'source.pdf',output,tmp_path/'work',
        Settings(max_layout_iterations=1),{'font_matching':[{'available':False,'source':'MissingFont'}]})
    assert report['history'][1]['kind']=='font matching'
    assert report['history'][1]['accepted'] is False
    assert report['best_iteration']==0
    assert hashlib.sha256(output.read_bytes()).hexdigest()==before


def test_renderer_can_accept_a_measured_font_when_all_constraints_improve(tmp_path,monkeypatch):
    original,output=_initial(tmp_path)
    _mock_runtime(monkeypatch,[_measurement(10,foreground=.7),_measurement(1,foreground=.95)],original)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/'source.pdf',output,tmp_path/'work',
        Settings(max_layout_iterations=1),{'font_matching':[{'available':False,'source':'MissingFont'}]})
    assert report['history'][1]['kind']=='font matching'
    assert report['history'][1]['accepted'] is True
    assert report['font_policy']=='metric'
    assert report['best_iteration']==1


@pytest.mark.parametrize("mutation",["text","font_size","table","textbox","image"])
def test_optimizer_rejects_semantic_or_editability_mutations_even_if_metric_improves(tmp_path,monkeypatch,mutation):
    original,output=_initial(tmp_path);before=hashlib.sha256(output.read_bytes()).hexdigest()
    calls=_mock_runtime(monkeypatch,[_measurement(10),_measurement(0,foreground=1)],original,mutation)
    _,report,_=optimizer.optimize_layout(_model(),tmp_path/"source.pdf",output,tmp_path/"work",
                                         Settings(max_layout_iterations=2),{})
    assert report["best_iteration"]==0
    assert "invariant" in report["stop_reason"]
    assert len(calls)==1  # Rejected before rendering a manipulated candidate.
    assert hashlib.sha256(output.read_bytes()).hexdigest()==before


def test_parametric_proposal_is_bounded_and_never_changes_font_size_or_text():
    model=_model();before=model.model_dump()
    proposal,count=optimizer._proposal(model,_measurement(100,dx=40),{},bound=2.5)
    assert count==2
    assert set(proposal["body"])=={"y","left"}
    assert all(abs(value)<=2.5 for value in proposal["body"].values())
    assert model.model_dump()==before


def test_explicit_no_optimize_cli_does_not_call_renderer(pdf_fixtures,tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError("Optimization explicitly disabled")
    monkeypatch.setattr(optimizer,"optimize_layout",forbidden)
    result=CliRunner().invoke(app,["convert",str(pdf_fixtures["native"]),"--output",str(tmp_path/"plain.docx"),"--no-optimize-layout","--json"])
    assert result.exit_code==0,result.output
    report=json.loads(Path(json.loads(result.stdout)["json_path"]).read_text())
    assert report["optimization"]["status"]=="not_requested"
    assert report["optimization"]["history"]==[]


@pytest.mark.parametrize("target,expected_tracking",[(60.3,.06),(120,0)])
def test_font_matching_bounds_tracking_without_deforming_size(monkeypatch,target,expected_tracking):
    import pdf2docx_ai.reconstruction.fonts as fonts
    class Metric:
        def text_length(self,text,fontsize):return 60.
    monkeypatch.setattr(fonts,"installed_font",lambda *args:("test.ttf","test metrics"))
    monkeypatch.setattr(fonts,"_metric_font",lambda *args:Metric())
    span=TextSpan(text="numero",bbox=BBox(x0=60,y0=70,x1=60+target,y1=85),font="Helvetica",size=12,advance_width=target)
    before=span.model_dump()
    family,tracking,_=FontResolver().resolve(span)
    assert family=="Arial"
    assert tracking==pytest.approx(expected_tracking)
    assert abs(tracking)<=min(.15,span.size*.015)
    assert span.model_dump()==before

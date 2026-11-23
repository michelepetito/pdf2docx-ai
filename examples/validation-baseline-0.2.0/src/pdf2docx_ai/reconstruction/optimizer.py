"""Bounded, renderer-in-the-loop coordinate descent with content invariants."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from statistics import median
from zipfile import ZipFile
import hashlib,json,math,shutil,time
from lxml import etree
from .engine import DocumentReconstructionEngine
from ..quality.validator import render_docx_to_pdf
from ..quality.visual_diff import evaluate_pdf_pair,compare_pdfs


def content_signature(path):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    values=[];counts=defaultdict(int);media=[]
    with ZipFile(path) as package:
        for name in sorted(n for n in package.namelist() if n.startswith('word/') and n.endswith('.xml')):
            root=etree.fromstring(package.read(name))
            for tag in ('tbl','txbxContent','sz'):
                nodes=root.xpath('//w:'+tag,namespaces=ns)
                if tag=='sz':values.append((name+':font_sizes',[n.get('{'+ns['w']+'}val') for n in nodes]))
                else:counts[tag]+=len(nodes)
            text=''.join(root.xpath('//w:t/text()',namespaces=ns))
            if text:values.append((name,text))
        for name in sorted(n for n in package.namelist() if n.startswith('word/media/')):
            media.append(hashlib.sha256(package.read(name)).hexdigest())
    return hashlib.sha256(json.dumps([values,dict(counts),media],ensure_ascii=False).encode()).hexdigest()


def objective(measurement):
    g=measurement['geometry'];f=measurement['foreground'];t=measurement['textual']
    dx=[abs(m['dx_pt']) for p in measurement['pages'] for m in p['word_matches'] if m['source_page']==m['target_page']]
    baseline=g.get('median_baseline_error_pt')
    p95=g.get('p95_baseline_error_pt')
    geometric=(baseline or 0)+.25*(p95 or 0)+(median(dx) if dx else 0)
    return (abs(measurement['page_count_difference'])*1000+g.get('page_drift_words',0)*2+
            (t.get('missing_characters',0)+t.get('excess_characters',0))*2+
            geometric+2*(1-f.get('foreground_ssim',0)))


def _proposal(model,measurement,current,bound,axis='both',gain=1.):
    errors=defaultdict(list)
    for page in model.pages:
        candidates=[r for r in page.regions if r.kind not in ('image','graphic') and not r.metadata.get('omit_editable')]
        for source in measurement['pages']:
            if source['page']!=page.number:continue
            for match in source['line_matches']:
                if match['source_page']!=match['target_page'] or match.get('target_wrap_lines',0)>2:continue
                box=match['source_bbox'];center=((box[0]+box[2])/2,(box[1]+box[3])/2)
                possible=[r for r in candidates if r.bbox.x0-.5<=center[0]<=r.bbox.x1+.5 and r.bbox.y0-.5<=center[1]<=r.bbox.y1+.5]
                if not possible:continue
                region=min(possible,key=lambda r:r.bbox.area)
                if region.metadata.get('rotation_normalized'):continue
                errors[region.id].append((match.get('baseline_dy_pt') or match['dy_pt'],match['dx_pt']))
    proposal=deepcopy(current);count=0
    for key,values in errors.items():
        dy=median(y for y,x in values);dx=median(x for y,x in values)
        adjustment=proposal.setdefault(key,{})
        for field,error in [('y',dy),('left',dx)]:
            if axis not in ('both',field):continue
            if abs(error)<.025:continue
            value=max(-bound,min(bound,adjustment.get(field,0)-gain*error))
            if abs(value-adjustment.get(field,0))>.01:adjustment[field]=round(value*20)/20;count+=1
    return proposal,count


def optimize_layout(model,source,docx,work,settings,initial_result,progress=None):
    progress=progress or (lambda value,message:None)
    started=time.monotonic()
    folder=Path(work)/'optimization';folder.mkdir(parents=True,exist_ok=True)
    initial=folder/'iteration-000.docx';shutil.copy2(docx,initial)
    render=render_docx_to_pdf(initial,folder/'iteration-000',settings.renderer,timeout=settings.layout_optimization_timeout)
    if render['status']!='rendered':
        return initial_result,{'status':render['status'],'stop_reason':render.get('reason'),'history':[]},None
    current_measure=evaluate_pdf_pair(source,Path(render['pdf_path']),folder/'before',include_images=True,dpi=100)
    before=current_measure;best_measure=current_measure;best_file=initial;best_pdf=Path(render['pdf_path']);best_result=initial_result
    best_loss=objective(current_measure);signature=content_signature(initial);adjustments={};history=[];best_iteration=0
    font_trial=any(not f.get('available',True) for f in initial_result.get('font_matching',[]))
    font_policy='requested'
    def record(iteration,measurement,loss,accepted,changed,kind='geometry'):
        return dict(iteration=iteration,kind=kind,objective=loss,accepted=accepted,parameters_changed=changed,
            median_position_error_pt=measurement['geometry'].get('median_position_error_pt'),
            p95_position_error_pt=measurement['geometry'].get('p95_position_error_pt'),
            median_baseline_error_pt=measurement['geometry'].get('median_baseline_error_pt'),
            ssim=measurement.get('mean_ssim'),foreground_ssim=measurement['foreground'].get('foreground_ssim'),
            page_count_difference=measurement['page_count_difference'],matched_words=measurement['geometry'].get('matched_words'),
            text_error=measurement['textual'].get('cer'))
    history.append(record(0,current_measure,best_loss,True,0));stop='maximum iterations'
    for iteration in range(1,settings.max_layout_iterations+1):
        remaining=settings.layout_optimization_timeout-(time.monotonic()-started)
        if remaining<=1:stop='optimization time limit';break
        # Alternating local axes after a rejected coupled step gives deterministic
        # bounded coordinate search, rather than claiming differentiable Word.
        trying_fonts=font_trial and iteration==1
        geometry_trials=[h for h in history[1:] if h.get('kind')=='geometry']
        axis='both' if not geometry_trials or geometry_trials[-1]['accepted'] else ('y' if len(geometry_trials)%2 else 'left')
        gain=1. if not geometry_trials or geometry_trials[-1]['accepted'] else .5
        if trying_fonts:
            proposal=deepcopy(adjustments);changed=sum(not f.get('available',True) for f in initial_result.get('font_matching',[]))
        else:proposal,changed=_proposal(model,best_measure,adjustments,settings.layout_max_adjustment_pt,axis,gain)
        if not changed:stop='no supported geometric discrepancy';break
        candidate=folder/f'iteration-{iteration:03d}.docx'
        progress(.80+.08*iteration/max(1,settings.max_layout_iterations),f'Ottimizzazione layout {iteration}/{settings.max_layout_iterations}')
        candidate_builder=(DocumentReconstructionEngine(font_policy='metric') if trying_fonts or font_policy=='metric'
                           else DocumentReconstructionEngine())
        candidate_result=candidate_builder.reconstruct(model,candidate,'editable',proposal)
        if content_signature(candidate)!=signature:
            stop='content invariant rejected candidate';break
        rendered=render_docx_to_pdf(candidate,folder/f'iteration-{iteration:03d}',settings.renderer,timeout=max(1,remaining))
        if rendered['status']!='rendered':stop='candidate renderer failed';break
        measured=evaluate_pdf_pair(source,Path(rendered['pdf_path']),dpi=100)
        loss=objective(measured)
        text=measured['textual'];reference=before['textual']
        admissible=(text.get('missing_characters',0)<=reference.get('missing_characters',0) and
                    text.get('excess_characters',0)<=reference.get('excess_characters',0) and
                    abs(measured['page_count_difference'])<=abs(before['page_count_difference']))
        original_tail=before['geometry'].get('p95_baseline_error_pt')
        candidate_tail=measured['geometry'].get('p95_baseline_error_pt')
        if original_tail is not None and candidate_tail is not None and candidate_tail>original_tail+.5:
            admissible=False
        if trying_fonts and (measured.get('mean_ssim',0)<best_measure.get('mean_ssim',0)-.001 or
                             measured['foreground'].get('foreground_ssim',0)<best_measure['foreground'].get('foreground_ssim',0)-.001):
            admissible=False
        accepted=admissible and loss<best_loss-settings.layout_min_improvement
        history.append(record(iteration,measured,loss,accepted,changed,'font matching' if trying_fonts else 'geometry'))
        if accepted:
            best_loss=loss;best_file=candidate;best_pdf=Path(rendered['pdf_path']);best_measure=measured
            best_result=candidate_result;best_iteration=iteration;adjustments=proposal
            if trying_fonts:font_policy='metric'
            if (measured['geometry'].get('p95_baseline_error_pt') or 0)<settings.layout_tolerance_pt and measured.get('mean_ssim',0)>=.98:
                stop='geometric tolerance and visual target';break
        elif not trying_fonts and geometry_trials and not geometry_trials[-1]['accepted']:
            stop='no significant admissible improvement';break
    shutil.copy2(best_file,docx)
    canonical=Path(work)/'rendered'/(Path(docx).stem+'.pdf');canonical.parent.mkdir(exist_ok=True)
    shutil.copy2(best_pdf,canonical)
    final=compare_pdfs(source,canonical,Path(work)/'visual');final['renderer']=render['renderer'];final['rendered_pdf_path']=str(canonical)
    data=dict(status='measured',algorithm='bounded coordinate descent',renderer=render['renderer'],history=history,font_policy=font_policy,
              best_iteration=best_iteration,stop_reason=stop,before=before,after=final,
              constraints='unchanged OOXML text; no new tables/textboxes/raster pages; no font-size deformation; no increased missing rendered characters',
              parameters=adjustments)
    return best_result,data,final

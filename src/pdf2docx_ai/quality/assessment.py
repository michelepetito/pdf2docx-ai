"""Four independent validation dimensions and experimental acceptance targets."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re,subprocess
import importlib.metadata
from functools import lru_cache
from .geometry_metrics import extract_elements,compare_elements
from .textual import analyze_text,normalize_text,NORMALIZATION_PROFILE
from .structure import audit_docx,edit_probe
from .units import MM_PER_PT,with_mm

SCHEMA_VERSION='2.0'
DEFAULT_TARGETS={'ssim':.990,'cer':.001,'median_geometry_mm':1.,'p95_geometry_mm':2.,'max_edit_probe_extra_pages':1}


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _code_fingerprint():
    root=Path(__file__).resolve().parents[1];h=hashlib.sha256()
    paths=sorted((root/'quality').glob('*.py'))+[root/'document/reading_order.py',root/'document/models.py']
    for path in paths:h.update(str(path.relative_to(root)).encode());h.update(path.read_bytes())
    return h.hexdigest()


@lru_cache(maxsize=8)
def _renderer_version(executable,mtime,checksum):
    try:
        run=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=20)
        return (run.stdout+run.stderr).strip()[:500]
    except (OSError,subprocess.TimeoutExpired):return 'unavailable'


def _renderer_details(executable,explicit=None):
    from .validator import find_renderer
    if not executable:return {'status':'unavailable','path':None}
    file=Path(executable)
    if not file.is_file():return {'status':'unverified','path':str(executable)}
    checksum=_sha(file);data={'path':str(file.resolve()),'wrapper_sha256':checksum}
    # Never execute a path taken only from cached report data. Probe the actual
    # configured renderer or the known current default, which renders the DOCX.
    allowed=find_renderer(explicit)
    if allowed and Path(allowed).resolve()==file.resolve():
        data['version']=_renderer_version(str(file),file.stat().st_mtime_ns,checksum);data['status']='measured'
    else:data['status']='cached_path_not_executed'
    return data


def _check(value,operator,threshold,basis):
    if value is None:return {'status':'unavailable','value':None,'operator':operator,'threshold':threshold,'basis':basis}
    met=value>=threshold if operator=='>=' else value<=threshold if operator=='<=' else value==threshold
    return {'status':'met' if met else 'not_met','value':value,'operator':operator,'threshold':threshold,'basis':basis}


def _raster_pages(source,target,model):
    suspicious=[];original=[]
    for image in target['images']:
        page=target['pages'][image['page']-1];box=image['bbox'];area=(box[2]-box[0])*(box[3]-box[1])
        if area<page['width_pt']*page['height_pt']*.80:continue
        same=[s for s in source['images'] if s['page']==image['page'] and s['digest']==image['digest']]
        native=[w for w in source['words'] if w['page']==image['page']]
        scan=False
        if model is not None and image['page']<=len(model.pages):
            source_page=model.pages[image['page']-1]
            scan=source_page.classification=='scanned' or any(r.kind=='image' and r.metadata.get('omit_editable') and r.bbox.area>source_page.width*source_page.height*.7 for r in source_page.regions)
        entry={'page':image['page'],'bbox_pt':box,'coverage':area/(page['width_pt']*page['height_pt'])}
        if same and native and not scan:original.append({**entry,'basis':'same decoded source image; native text exists; original full-bleed image is not automatically a rasterization shortcut'})
        else:suspicious.append({**entry,'basis':'page-sized image without verified native full-bleed source evidence, or retained scan background'})
    return {'suspected_replacement_count':len(suspicious),'suspected_pages':suspicious,'verified_original_full_bleed':original,
            'limitation':'Identity is decoded-pixel based. Transcoding can require review; an unverified large image is not silently accepted.'}


def _compare_regression(previous,current):
    if previous is None:return {'status':'no_previous_assessment','regressions':[],'tradeoff':False}
    previous=previous.get('assessment',previous)
    if 'dimensions' not in previous:
        old_sha=previous.get('source_sha256')
        if old_sha is not None and old_sha!=current['inputs']['source_sha256']:
            raise ValueError('A regression comparison requires the same source PDF SHA-256')
        return {'status':'legacy_schema_not_directly_comparable','regressions':[],'tradeoff':False,
                'reason':'Previous report preserved. Re-evaluate the same PDF/DOCX pair with evaluate_validation.py; changed text references are not compared as if they were the same metric.'}
    if previous.get('inputs',{}).get('source_sha256')!=current['inputs']['source_sha256']:
        raise ValueError('A regression comparison requires the same source PDF SHA-256')
    def values(a):
        d=a['dimensions'];v=d['visual'];t=d['textual'];g=d['geometry'];s=d['structure'];primary=t.get('primary',{})
        probe=s.get('edit_probe',{});audit=s.get('audit',{})
        return {'ssim':v.get('mean_ssim'),'worst_page_ssim':v.get('minimum_page_ssim'),'cer':primary.get('cer'),
                'wer':primary.get('wer'),'median_geometry_mm':g.get('word_summary',{}).get('median_position_error_mm'),
                'p95_geometry_mm':g.get('word_summary',{}).get('p95_position_error_mm'),
                'missing_characters':t.get('missing_characters'),'added_characters':t.get('added_characters'),
                'raster_replacements':s.get('raster_pages',{}).get('suspected_replacement_count'),
                'hidden_characters':s.get('audit',{}).get('hidden_characters'),
                'additional_tables':s.get('audit',{}).get('unverified_additional_tables'),
                'textboxes':audit.get('text_box_count'),'missing_native_images':s.get('image_evidence',{}).get('missing_native_images'),
                'document_protection':int(audit['document_protection_enforced']) if 'document_protection_enforced' in audit else None,
                'locked_content_controls':audit.get('locked_content_controls'),
                'edit_probe_lost_characters':probe.get('missing_baseline_characters') if probe.get('status')=='measured' else None,
                'edit_probe_new_rule_collisions':probe.get('rule_text_collisions',{}).get('introduced_count') if probe.get('status')=='measured' else None,
                'page_count_error':abs(g.get('page_count_difference',0))}
    before,after=values(previous),values(current);regressions=[];changes=[]
    text_reference_changed=any(previous.get('inputs',{}).get(key)!=current.get('inputs',{}).get(key) for key in ('ground_truth_sha256',)) or previous['dimensions']['textual'].get('primary',{}).get('reference')!=current['dimensions']['textual'].get('primary',{}).get('reference') or previous.get('methodology',{}).get('normalization')!=current.get('methodology',{}).get('normalization')
    incomparable=['cer','wer','missing_characters','added_characters'] if text_reference_changed else []
    eps={'ssim':1e-6,'worst_page_ssim':1e-6,'cer':1e-9,'wer':1e-9,'median_geometry_mm':.001,'p95_geometry_mm':.001}
    for key,value in after.items():
        if key in incomparable:continue
        old=before.get(key)
        if old is None or value is None:continue
        delta=value-old;worse=delta < -eps.get(key,0) if key in ('ssim','worst_page_ssim') else delta > eps.get(key,0)
        entry={'metric':key,'before':old,'after':value,'delta':delta,'regressed':worse}
        changes.append(entry)
        if worse:regressions.append(entry)
    renderer_changed=previous.get('methodology',{}).get('renderer_details',previous.get('methodology',{}).get('renderer'))!=current['methodology'].get('renderer_details',current['methodology'].get('renderer'))
    improved=after.get('ssim') is not None and before.get('ssim') is not None and after['ssim']>before['ssim']+eps['ssim']
    return {'status':'compared','previous_id':previous.get('assessment_id'),'regressions':regressions,'changes':changes,
            'tradeoff':improved and any(r['metric']!='ssim' for r in regressions),'numerical_tolerances':eps,
            'text_reference_changed':text_reference_changed,'non_comparable_metrics':incomparable,
            'renderer_changed':renderer_changed,'interpretation':'renderer confounded' if renderer_changed else 'same recorded renderer; all dimensions remain separate'}


def assess_conversion(source,docx,work,*,model=None,visual=None,structural=None,renderer=None,
                      ground_truth=None,run_edit_probe=False,targets=None,previous=None):
    from .validator import visual_validation
    source=Path(source);docx=Path(docx);work=Path(work);work.mkdir(parents=True,exist_ok=True)
    limits={**DEFAULT_TARGETS,**(targets or {})};audit=(structural or {}).get('audit') or audit_docx(docx,model)
    body_text=audit['visible_body_text'];audit={k:v for k,v in audit.items() if k!='visible_body_text'}
    visual=visual if visual is not None else visual_validation(source,docx,work,renderer)
    rendered=visual.get('rendered_pdf_path');measured=visual.get('status')=='measured' and rendered and Path(rendered).is_file()
    shape={'status':visual.get('status','not_requested') if not visual.get('status')=='measured' or measured else 'unavailable_missing_rendered_pdf',
           'word_summary':with_mm(visual.get('geometry',{})),
           'page_count_difference':visual.get('page_count_difference',0)}
    text={'status':'unavailable_no_rendered_reference','primary':{'cer':None,'wer':None}}
    raster={'suspected_replacement_count':None,'suspected_pages':[]}
    image_evidence={'missing_native_images':None,'justified_scan_background_omissions':[],'ocr_replacements_needing_review':[]}
    if measured:
        src=extract_elements(source);dst=extract_elements(rendered)
        details=compare_elements(src,dst);shape.update(status='measured',**details)
        truth=Path(ground_truth).read_text(encoding='utf-8') if ground_truth is not None else None
        target_flow=' '.join(w['text'] for w in dst['logical_words'])
        text=analyze_text(src['words'],dst['words'],logical_source=src['logical_words'],logical_target=dst['logical_words'],
                          source_body=src['body_words'],docx_body_text=body_text,ground_truth=truth,ground_truth_hypothesis=target_flow)
        primary=text.get('ground_truth') if truth is not None else text.get('logical_pdf_flow')
        text['primary']=primary or {'cer':None,'wer':None,'reference':'no native text or external reference'}
        text['primary']['normalization']=NORMALIZATION_PROFILE
        if truth is not None:
            text['native_pdf_reference_status']=text['status'];text['status']='measured_external_ground_truth'
            ref=normalize_text(truth);hyp=normalize_text(target_flow)
            a=Counter(''.join(ref.split()));b=Counter(''.join(hyp.split()))
            text['missing_characters']=sum((a-b).values());text['added_characters']=sum((b-a).values())
            numbers=lambda s:Counter(re.findall(r'[+−-]?\d+(?:[.,:/−-]\d+)*%?',s))
            na,nb=numbers(ref),numbers(hyp)
            text['reference_numbers_dates']={'missing_count':sum((na-nb).values()),'added_count':sum((nb-na).values()),
                                             'missing':dict(na-nb),'added':dict(nb-na),'reference':'external ground truth'}
        else:text['reference_numbers_dates']=text['numbers_dates']
        has_ocr=model is not None and any(r.source=='ocr' and r.text for p in model.pages for r in p.regions)
        text['native_only_reference_incomplete_for_ocr']=has_ocr and truth is None
        if text['native_only_reference_incomplete_for_ocr']:
            text['native_reference_diagnostics']={k:text.get(k) for k in ('primary','missing_characters','added_characters','reference_numbers_dates')}
            text['status']='unavailable_incomplete_native_reference'
            text['primary']={'cer':None,'wer':None,'status':'unavailable_incomplete_native_reference',
                             'reference':'native PDF text omits OCR regions; a complete external reference is required'}
            text['missing_characters']=None;text['added_characters']=None
            text['reference_numbers_dates']={'missing_count':None,'added_count':None,'reference':'incomplete native reference; raw native-only diagnostics retained separately'}
        raster=_raster_pages(src,dst,model)
        missing_images=details['categories']['images'].get('unmatched_source',[]);unjustified=[]
        for image in missing_images:
            p=src['pages'][image['page']-1];b=image['bbox'];coverage=(b[2]-b[0])*(b[3]-b[1])/(p['width_pt']*p['height_pt'])
            native=any(w['page']==image['page'] for w in src['words'])
            matches=[]
            if model is not None and image['page']<=len(model.pages):
                matches=[r for r in model.pages[image['page']-1].regions if r.kind=='image' and r.metadata.get('omit_editable') and
                         abs(r.bbox.x0-b[0])+abs(r.bbox.y0-b[1])<2]
            if coverage>.7 and (not native or matches):image_evidence['justified_scan_background_omissions'].append(image)
            elif matches:image_evidence['ocr_replacements_needing_review'].append(image)
            else:unjustified.append(image)
        image_evidence['missing_native_images']=len(unjustified)
        image_evidence['missing_image_locations']=unjustified
        image_evidence['note']='Full-page scan backgrounds can be deliberately omitted for editable OCR. A small OCR image replacement has unverified graphic semantics and requires review.'
        if audit['expected_source_tables'] is None and all(p['table_detection']=='measured_native_grids' for p in src['pages']):
            expected=len(src['elements']['tables']);audit['expected_source_tables']=expected
            audit['unverified_additional_tables']=max(0,audit['native_tables']-expected)
            audit['source_table_basis']='independent native grid detection, not semantic ground truth'
    probe={'status':'not_requested'}
    if run_edit_probe and measured:probe=edit_probe(docx,rendered,work/'edit-probe',renderer or visual.get('renderer'))
    elif run_edit_probe:probe={'status':'unavailable','reason':'A baseline renderer is required.'}
    v={k:visual.get(k) for k in ('status','mean_ssim','minimum_page_ssim','p10_page_ssim','foreground','normalization','renderer')}
    v['minimum_page_ssim']=min((p['ssim'] for p in visual.get('pages',[])),default=None)
    v['pages']=[{k:p.get(k) for k in ('page','ssim','foreground','changed_pixel_fraction','source_page_missing','target_page_missing','effective_dpi')} for p in visual.get('pages',[])]
    v['pages_below_target']=[p['page'] for p in v['pages'] if p['ssim'] is not None and p['ssim']<limits['ssim']]
    v['note']='SSIM is not a certified percentage of fidelity. Foreground and worst-page values accompany the mean.'
    t=text.get('primary',{});g=shape['word_summary'];incomplete=text.get('native_only_reference_incomplete_for_ocr',False)
    numeric=text.get('reference_numbers_dates',{});visible=audit['visible_nonwhitespace_characters']>0
    structurally_editable=visible and not audit['hidden_characters'] and not audit['document_protection_enforced'] and not audit['locked_content_controls'] and audit['textbox_text_fraction']<.5
    checks={'visual_document_ssim':_check(v.get('mean_ssim'),'>=',limits['ssim'],'global visual mean; separate from text and structure'),
            'visual_every_page_ssim':_check(v['minimum_page_ssim'],'>=',limits['ssim'],'worst page; the mean cannot hide a bad page'),
            'text_cer':_check(None if incomplete else t.get('cer'),'<=',limits['cer'],t.get('reference','reference unavailable')),
            'text_missing_characters':_check(None if incomplete or not measured or text['status']=='unavailable_no_native_reference' and ground_truth is None else text.get('missing_characters'),'==',0,'normalized character count deficits; sequence errors remain separate'),
            'text_added_characters':_check(None if incomplete or not measured or text['status']=='unavailable_no_native_reference' and ground_truth is None else text.get('added_characters'),'==',0,'normalized character count surplus; native-only references cannot grade added OCR text'),
            'numeric_date_changes':_check(None if incomplete or not measured or text['status']=='unavailable_no_native_reference' and ground_truth is None else numeric.get('missing_count',0)+numeric.get('added_count',0),'==',0,'critical values checked independently of aggregate CER'),
            'geometry_median_mm':_check(g.get('median_position_error_mm'),'<=' ,limits['median_geometry_mm'],'matched same-page word box origins; coverage and baseline errors are also reported'),
            'geometry_p95_mm':_check(g.get('p95_position_error_mm'),'<=' ,limits['p95_geometry_mm'],'matched same-page word box origins; unmatched content is not silently accepted'),
            'page_count':_check(abs(shape['page_count_difference']) if measured else None,'==',0,'source versus rendered page count'),
            'editable_text':_check(structurally_editable,'==',True,'visible ordinary Word text; protection, hidden text and dominant textboxes checked'),
            'no_page_raster_replacement':_check(raster['suspected_replacement_count'],'==',0,'source-aware full-page raster investigation'),
            'no_unverified_tables':_check(audit['unverified_additional_tables'],'==',0,'source model or inferred native table evidence; ambiguity requires review'),
            'no_unverified_textboxes':_check(audit['text_box_count'],'==',0,'independent floating text exceptions need source evidence and review; boxes are not certified automatically'),
            'native_images_preserved':_check(None if image_evidence['ocr_replacements_needing_review'] else image_evidence['missing_native_images'],'==',0,'unmatched native images, excluding justified scan backgrounds; unresolved OCR replacements require review'),
            'edit_probe_content_preserved':_check((probe.get('missing_baseline_characters',0)+(not probe.get('objects_preserved'))+(not probe.get('original_unchanged'))+(not probe.get('xml_text_change_exact'))) if probe.get('status')=='measured' else None,'==',0,'save/reopen/render of a copy; exact XML insertion, expected added text, objects and original file must be preserved'),
            'edit_probe_pagination':_check(abs(probe.get('page_count_change',0)) if probe.get('status')=='measured' else None,'<=',limits['max_edit_probe_extra_pages'],'explicit diagnostic budget for a three-word insertion; natural downstream reflow is also reported'),
            'edit_probe_no_new_rule_collisions':_check(probe.get('rule_text_collisions',{}).get('introduced_count') if probe.get('status')=='measured' else None,'==',0,'new intersections of thin horizontal vector rules with central text-line boxes require review; heuristic, not glyph-level proof')}
    if not structurally_editable and raster['suspected_replacement_count'] is None and audit['page_sized_picture_candidates']:
        checks['no_page_raster_replacement']=_check(len(audit['page_sized_picture_candidates']),'==',0,'non-editable document with page-sized raster picture')
    inputs={'source_sha256':_sha(source),'docx_sha256':_sha(docx),'rendered_pdf_sha256':_sha(rendered) if measured else None,
            'ground_truth_sha256':_sha(ground_truth) if ground_truth is not None else None,
            'model_sha256':hashlib.sha256(json.dumps(model.model_dump(mode='json'),sort_keys=True).encode()).hexdigest() if model is not None else None,
            'source':str(source.resolve()),'docx':str(docx.resolve()),'rendered_pdf':str(Path(rendered).resolve()) if measured else None}
    methodology={'schema_version':SCHEMA_VERSION,'renderer':visual.get('renderer',renderer),'raster_dpi_requested':100,
                 'renderer_details':_renderer_details(visual.get('renderer',renderer),renderer),'validator_code_sha256':_code_fingerprint(),
                 'normalization':NORMALIZATION_PROFILE,'geometry_units':{'point_to_mm':MM_PER_PT},
                 'text_distance':'exact uniform Levenshtein; no cutoff or fuzzy similarity',
                 'libraries':{name:importlib.metadata.version(name) for name in ('PyMuPDF','python-docx','numpy','Pillow','lxml','RapidFuzz')},
                 'inference_warning':'Paragraphs, columns, repeated edge roles and physical reading order are explicit hypotheses; no semantic ground truth is invented.'}
    identity=hashlib.sha256(json.dumps({'inputs':{k:v for k,v in inputs.items() if k.endswith('sha256')},'methodology':methodology,'targets':limits,'edit_probe':run_edit_probe},sort_keys=True).encode()).hexdigest()
    result={'schema_version':SCHEMA_VERSION,'assessment_id':identity,'created_utc':datetime.now(timezone.utc).isoformat(),
            'inputs':inputs,'methodology':methodology,'experimental_targets':limits,'target_checks':checks,
            'dimensions':{'visual':v,'textual':text,'geometry':shape,'structure':{'audit':audit,'raster_pages':raster,'image_evidence':image_evidence,'edit_probe':probe}},
            'composite_score':None,'interpretation':'Four dimensions stay separate; meeting experimental targets is not certification.'}
    result['regression']=_compare_regression(previous,result)
    result['target_summary']=dict(Counter(c['status'] for c in checks.values()))
    return result,visual


def persist_assessment(assessment,root):
    if not re.fullmatch(r'[a-f0-9]{64}',assessment['assessment_id']):raise ValueError('Invalid assessment identity')
    root=Path(root);history=root/'history';history.mkdir(parents=True,exist_ok=True)
    path=history/(assessment['assessment_id']+'.json')
    # Immutable first observation for an identical artifact/method/target set.
    try:
        with path.open('x',encoding='utf-8') as f:json.dump(assessment,f,ensure_ascii=False,indent=2)
    except FileExistsError:pass
    return str(path.resolve())

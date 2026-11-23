"""OOXML editability evidence, not a visual-similarity substitute."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib,re
from zipfile import ZipFile
from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from .textual import normalize_text


def model_text(model):
    if model is None:return None
    result=[]
    for page in model.pages:
        for r in page.regions:
            if r.kind in ('image','graphic') or r.metadata.get('omit_editable'):continue
            if r.kind=='formula' and r.metadata.get('ocr_format')=='latex' and r.crop_path:continue
            result.append(' '.join(c.text for c in r.cells) if r.kind=='table' else r.text)
    return '\n'.join(result)


def _true(node):
    return node is not None and node.get(qn('w:val'),'1').lower() not in ('0','false','off','no')


def _nearest(node,tag):
    return next((a for a in node.iterancestors() if a.tag==qn(tag)),None)


def audit_docx(path,model=None):
    doc=Document(path);styles={s.get(qn('w:styleId')):s for s in doc.styles.element}
    def inherited(run,p,name):
        direct=run.find('./'+qn('w:rPr')+'/'+qn('w:'+name)) if run is not None else None
        if direct is not None:return _true(direct)
        candidates=[]
        if run is not None:
            rstyle=run.find('./'+qn('w:rPr')+'/'+qn('w:rStyle'))
            if rstyle is not None:candidates.append(rstyle.get(qn('w:val')))
        pstyle=p.find('./'+qn('w:pPr')+'/'+qn('w:pStyle')) if p is not None else None
        candidates.append(pstyle.get(qn('w:val')) if pstyle is not None else 'Normal')
        for identifier in candidates:
            seen=set()
            while identifier in styles and identifier not in seen:
                seen.add(identifier);style=styles[identifier];node=style.find('./'+qn('w:rPr')+'/'+qn('w:'+name))
                if node is not None:return _true(node)
                base=style.find(qn('w:basedOn'));identifier=base.get(qn('w:val')) if base is not None else None
        return False
    visible=[];body=[];hidden_chars=0;textbox_chars=0;all_chars=0;parts=[];pictures=0;anchors=0;inline=0
    textbox_count=0;table_count=0;invisible_tables=0;page_sized=[];field_codes=[]
    sizes=[(s.page_width.pt if s.page_width is not None else None,s.page_height.pt if s.page_height is not None else None) for s in doc.sections]
    media=[]
    with ZipFile(path) as package:
        for name in sorted(package.namelist()):
            if name.startswith('word/media/'):media.append(hashlib.sha256(package.read(name)).hexdigest())
            if not re.fullmatch(r'word/(document|header\d+|footer\d+|footnotes|endnotes)\.xml',name):continue
            root=etree.fromstring(package.read(name));parts.append(name)
            textbox_count+=len(list(root.iter(qn('w:txbxContent'))))
            field_codes.extend(n.text or '' for n in root.iter(qn('w:instrText')))
            field_codes.extend(n.get(qn('w:instr'),'') for n in root.iter(qn('w:fldSimple')))
            for p in root.iter(qn('w:p')):
                text=[]
                for n in p.iter():
                    if n is p or _nearest(n,'w:p') is not p:continue
                    if n.tag not in (qn('w:t'),qn('m:t'),qn('w:tab'),qn('w:br'),qn('w:cr')):continue
                    value=(n.text or '') if n.tag in (qn('w:t'),qn('m:t')) else '\t' if n.tag==qn('w:tab') else '\n'
                    run=_nearest(n,'w:r');hidden=inherited(run,p,'vanish') or inherited(run,p,'webHidden')
                    all_chars+=len(value)
                    if _nearest(n,'w:txbxContent') is not None:textbox_chars+=len(value)
                    if hidden:hidden_chars+=len(value)
                    else:text.append(value)
                if text:
                    joined=''.join(text);visible.append(joined)
                    if name=='word/document.xml' and _nearest(p,'w:txbxContent') is None:body.append(joined)
            for picture in root.iter(qn('pic:pic')):
                pictures+=1;anchor=_nearest(picture,'wp:anchor');container=anchor if anchor is not None else _nearest(picture,'wp:inline')
                anchors+=anchor is not None;inline+=container is not None and anchor is None
                if container is not None:
                    extent=container.find(qn('wp:extent'))
                    if extent is not None:
                        w=int(extent.get('cx','0'))/12700;h=int(extent.get('cy','0'))/12700
                        if any(pw and ph and w>=pw*.85 and h>=ph*.85 and w*h>=pw*ph*.80 for pw,ph in sizes):
                            page_sized.append({'part':name,'width_pt':w,'height_pt':h})
            for table in root.iter(qn('w:tbl')):
                table_count+=1;borders=table.xpath('.//w:tblBorders/*|.//w:tcBorders/*',namespaces={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})
                if borders and all(n.get(qn('w:val'),'nil') in ('nil','none','0') for n in borders):invisible_tables+=1
    visible_text='\n'.join(visible);body_text='\n'.join(body)
    columns=[];margins=[]
    for section in doc.sections:
        cols=section._sectPr.find(qn('w:cols'));count=int(cols.get(qn('w:num'),'1')) if cols is not None else 1
        columns.append(count);margins.append({k:getattr(section,k+'_margin').pt if getattr(section,k+'_margin') is not None else None for k in ('left','right','top','bottom')})
    expected=model_text(model);missing=None;added=None
    if expected is not None:
        a=Counter(''.join(normalize_text(expected).split()));b=Counter(''.join(normalize_text(visible_text).split()))
        missing=sum((a-b).values());added=sum((b-a).values())
    expected_tables=sum(r.kind=='table' for p in model.pages for r in p.regions) if model is not None else None
    protection=doc.settings.element.find(qn('w:documentProtection'))
    protected=protection is not None and protection.get(qn('w:enforcement'),'0') in ('1','true','on')
    locks=doc.element.xpath('//w:sdtPr/w:lock')
    locked=sum(n.get(qn('w:val')) in ('contentLocked','sdtContentLocked') for n in locks)
    return {'status':'measured','visible_editable_characters':len(visible_text),
        'visible_nonwhitespace_characters':len(''.join(normalize_text(visible_text).split())),'visible_flow_body_characters':len(body_text),
        'hidden_characters':hidden_chars,'textbox_characters':textbox_chars,'textbox_text_fraction':textbox_chars/max(all_chars,1),
        'text_box_count':textbox_count,'picture_count':pictures,'anchored_pictures':anchors,'inline_pictures':inline,
        'page_sized_picture_candidates':page_sized,'native_tables':table_count,'expected_source_tables':expected_tables,
        'unverified_additional_tables':max(0,table_count-expected_tables) if expected_tables is not None else None,
        'explicitly_invisible_tables':invisible_tables,'sections':len(doc.sections),'native_column_counts':columns,
        'multi_column_sections':sum(n>1 for n in columns),'explicit_page_breaks':len(doc.element.xpath('//w:br[@w:type="page"]')),
        'explicit_column_breaks':len(doc.element.xpath('//w:br[@w:type="column"]')),
        'tab_stops':len(doc.element.xpath('//w:tabs/w:tab')),'tabs':len(doc.element.xpath('//w:tab')),
        'indented_paragraphs':len(doc.element.xpath('//w:pPr/w:ind')),'paragraphs':len(list(doc.element.iter(qn('w:p')))),
        'paragraph_styles':dict(Counter(p.style.name for p in doc.paragraphs)),
        'section_margins_pt':margins,'document_protection_enforced':protected,'locked_content_controls':locked,
        'missing_model_characters':missing,'added_model_characters':added,'field_codes':field_codes,
        'text_parts_checked':parts,'visible_body_text':body_text,'media_sha256':sorted(media),
        'assumptions':['PDF table evidence is inferred, not a semantic certificate.','Absent explicit borders does not prove an invisible layout table.',
                       'A page-sized picture is investigated against source assets and text; it is not accepted on SSIM alone.',
                       'Visible text excludes explicit/inherited vanish and webHidden; complex conditional display is not simulated.']}


def _rule_text_collisions(path):
    """Heuristic intersections with thin horizontal rules; not glyph analysis."""
    import pymupdf
    from ..pdf.runtime import PDF_LOCK
    from .units import MM_PER_PT
    records={}
    with PDF_LOCK,pymupdf.open(path) as pdf:
        for number,page in enumerate(pdf,1):
            rules={}
            for drawing in page.get_drawings():
                box=drawing['rect']*page.rotation_matrix
                if box.width>=40 and box.height<=2:
                    key=tuple(round(x,1) for x in box);rules[key]=box
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    text=normalize_text(''.join(s['text'] for s in line['spans']))
                    box=pymupdf.Rect(line['bbox'])*page.rotation_matrix
                    if not text or not box.height:continue
                    for rule_key,rule in rules.items():
                        y=(rule.y0+rule.y1)/2
                        overlap=min(box.x1,rule.x1)-max(box.x0,rule.x0)
                        if box.y0+box.height*.2<y<box.y1-box.height*.1 and overlap>min(10,box.width*.3):
                            key=(number,rule_key,text)
                            records[key]={'page':number,'text':text,'text_bbox_pt':list(box),'rule_bbox_pt':list(rule),
                                          'text_bbox_mm':[x*MM_PER_PT for x in box],'rule_bbox_mm':[x*MM_PER_PT for x in rule]}
    return records


def edit_probe(docx,baseline_pdf,work,renderer=None,timeout=120):
    from .validator import render_docx_to_pdf
    from .visual_diff import evaluate_pdf_pair
    docx=Path(docx);work=Path(work);work.mkdir(parents=True,exist_ok=True)
    original_hash=hashlib.sha256(docx.read_bytes()).hexdigest();document=Document(docx)
    candidates=[p for p in document.paragraphs if p.text.strip() and not p.style.name.startswith(('Heading','Title'))]
    if not candidates:
        seen=set()
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell._tc in seen:continue
                    seen.add(cell._tc);candidates.extend(p for p in cell.paragraphs if p.text.strip())
    paragraph=next((p for p in candidates if len(p.text)>=160),
                   next((p for p in candidates if len(p.text)>=40),candidates[0] if candidates else None))
    if paragraph is None:return {'status':'unavailable','reason':'No ordinary editable paragraph or table cell to modify.'}
    run=next((r for r in paragraph.runs if r.text.strip()),None)
    if run is None:return {'status':'unavailable','reason':'Selected text is not in a directly editable ordinary run.'}
    prefix='verifica di prova ';before=paragraph.text
    nodes=list(document.element.iter(qn('w:t')));first=next(iter(run._r.iter(qn('w:t'))),None)
    if first is None:return {'status':'unavailable','reason':'No ordinary text node in the selected run.'}
    offset=sum(len(n.text or '') for n in nodes[:nodes.index(first)])
    raw_before=''.join(n.text or '' for n in nodes);expected_sequence=raw_before[:offset]+prefix+raw_before[offset:]
    run.text=prefix+run.text
    changed=work/'ordinary-edit.docx';document.save(changed)
    reopened=Document(changed);old_audit=audit_docx(docx);new_audit=audit_docx(changed)
    unchanged_objects=all(old_audit[k]==new_audit[k] for k in ('native_tables','picture_count','text_box_count','sections','media_sha256'))
    sequence_correct=''.join(n.text or '' for n in reopened.element.iter(qn('w:t')))==expected_sequence
    rendered=render_docx_to_pdf(changed,work/'rendered-probe',renderer,timeout=timeout)
    result={'status':rendered['status'],'operation':'insert three ordinary words into the first suitable long body paragraph or table cell (160 characters preferred, then 40, then first editable)',
            'inserted_text':prefix,'original_unchanged':hashlib.sha256(docx.read_bytes()).hexdigest()==original_hash,
            'objects_preserved':unchanged_objects,'paragraph_before':before[:250],'paragraph_after':paragraph.text[:280],
            'xml_text_change_exact':sequence_correct,
            'probe_docx':str(changed),'renderer':rendered.get('renderer'),'reason':rendered.get('reason')}
    if rendered['status']!='rendered':return result
    measured=evaluate_pdf_pair(Path(baseline_pdf),Path(rendered['pdf_path']),include_images=True,dpi=100)
    textual=measured['textual']
    import pymupdf
    with pymupdf.open(baseline_pdf) as before_pdf,pymupdf.open(rendered['pdf_path']) as after_pdf:
        expected=Counter(''.join(normalize_text(' '.join(p.get_text() for p in before_pdf)+prefix).split()))
        observed=Counter(''.join(normalize_text(' '.join(p.get_text() for p in after_pdf)).split()))
    lost=sum((expected-observed).values())
    old_collisions=_rule_text_collisions(baseline_pdf);new_collisions=_rule_text_collisions(rendered['pdf_path'])
    introduced=[value for key,value in new_collisions.items() if key not in old_collisions]
    collision_check={'status':'measured','before':len(old_collisions),'after':len(new_collisions),'introduced_count':len(introduced),
                     'introduced':introduced[:80],'records_truncated':len(introduced)>80,
                     'basis':'Heuristic: horizontal vector rules at least 40 pt wide and at most 2 pt high cross the central 20–90% of a native text line box. New page/rule/text combinations require review; intentional strikethroughs and glyph bounds are not resolved.'}
    result.update(status='measured',rendered_pdf=rendered['pdf_path'],page_count_change=measured['page_count_difference'],
                  missing_baseline_characters=lost,added_characters=textual.get('excess_characters'),
                  rule_text_collisions=collision_check,
                  word_drift=measured['geometry'],affected_pages=[p['page'] for p in measured['pages'] if p['changed_pixel_fraction']>1e-5],
                  page_pixel_changes=[{'page':p['page'],'changed_pixel_fraction':p['changed_pixel_fraction'],'ssim':p['ssim']} for p in measured['pages']],
                  outcome='content_loss' if lost or not unchanged_objects or not sequence_correct else 'large_pagination_change' if abs(measured['page_count_difference'])>1 else 'layout_disruption_suspected' if introduced else 'reflow_measured',
                  note='A real save/reopen/render of a copy. Reflow is measured, not certified harmless; downstream changes can be legitimate in natural Word flow.')
    from PIL import Image
    previews=[]
    with pymupdf.open(baseline_pdf) as a,pymupdf.open(rendered['pdf_path']) as b:
        for i in range(min(3,len(a),len(b))):
            first=a[i].get_pixmap(dpi=100,alpha=False);second=b[i].get_pixmap(dpi=100,alpha=False)
            ai=Image.frombytes('RGB',(first.width,first.height),first.samples)
            bi=Image.frombytes('RGB',(second.width,second.height),second.samples)
            size=(max(ai.width,bi.width),max(ai.height,bi.height));ca=Image.new('RGB',size,'white');cb=ca.copy()
            ca.paste(ai,(0,0));cb.paste(bi,(0,0));entry={'page':i+1}
            for name,img in (('before',ca),('after',cb),('overlay',Image.blend(ca,cb,.5))):
                filename=work/f'edit-page-{i+1}-{name}.jpg';img.save(filename,quality=85);entry[name+'_path']=str(filename)
            previews.append(entry)
    result['previews']=previews;result['preview_page_limit']=3
    return result

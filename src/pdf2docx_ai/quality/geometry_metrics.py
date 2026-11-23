"""Measured PDF element geometry, with explicit hypotheses and word anchors.

PDF blocks/lines and native grids are observable. Paragraphs, lanes and repeated
edge roles are hypotheses, not semantic ground truth. No raster registration.
"""
from collections import Counter,defaultdict
from hashlib import sha256
from statistics import median
import math,re
import numpy as np
import pymupdf
from ..document.models import BBox,Page,Region,TextLine,TextSpan
from ..document.reading_order import order_regions
from ..pdf.runtime import PDF_LOCK
from .visual_diff import _extract,_image_records,_match_images,_match_tokens,_measurement,_stats
from .textual import normalize_text
from .units import with_mm,MM_PER_PT

CATEGORIES=('text_blocks','paragraphs','lines','columns','tables','images','headers','footers')
BASES={'text_blocks':'native PDF extraction blocks; grouping can differ between renderers',
       'paragraphs':'inferred flow groups split by large baseline gaps; not semantic paragraph ground truth; excludes native table cells',
       'lines':'native physical text lines',
       'columns':'inferred visible text lanes, not original section widths',
       'tables':'native detected grid evidence; borderless/raster table semantics unverified',
       'images':'native raster object boxes; pixel identity or explicit aspect/position heuristic',
       'headers':'repeated top-edge text hypothesis',
       'footers':'repeated bottom-edge text hypothesis'}


def _union(boxes):
    return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]


def _inside(word,box):
    b=word['bbox'];area=max((b[2]-b[0])*(b[3]-b[1]),1e-8)
    return max(0,min(b[2],box[2])-max(b[0],box[0]))*max(0,min(b[3],box[3])-max(b[1],box[1]))/area>.6


def _element(identifier,page,box,words,**extra):
    return dict(id=identifier,page=page,bbox=list(box),word_ids=[w['id'] for w in words],
                text=' '.join(w['text'] for w in words),**extra)


def _tables(page,number):
    if page.rotation or page.cropbox!=page.mediabox:return [],'unavailable_rotated_or_cropped'
    try:
        # Isolate the detector's page mutations and native object lifetimes.
        with pymupdf.open() as copy:
            copy.insert_pdf(page.parent,from_page=page.number,to_page=page.number)
            tables=[{'id':f'{number}:table:{i}','page':number,'bbox':list(t.bbox),
                     'rows':t.row_count,'columns':t.col_count} for i,t in enumerate(copy[0].find_tables().tables)]
        return tables,'measured_native_grids'
    except Exception as exc:return [],'unavailable_'+type(exc).__name__


def extract_elements(path):
    data={'words':[],'lines':[],'pages':[],'images':[],'elements':{k:[] for k in CATEGORIES},
          'logical_words':[],'body_words':[],'word_columns':{}}
    by_page=[]
    with PDF_LOCK,pymupdf.open(path) as pdf:
        for n,page in enumerate(pdf,1):
            words,lines=_extract(page,n)
            for w in words:w['id']=f"{n}:word:{w['index']}"
            for line in lines:line['block_id']=line['id'].rsplit(':',1)[0]
            tables,status=_tables(page,n)
            data['words'].extend(words);data['lines'].extend(lines);data['images'].extend(_image_records(page,n))
            info={'page':n,'width_pt':page.rect.width,'height_pt':page.rect.height,'rotation':page.rotation,'table_detection':status}
            data['pages'].append(info);by_page.append((info,words,lines,tables))
    repeats={'header':Counter(),'footer':Counter()}
    key=lambda t:re.sub(r'\d+','#',normalize_text(t))
    for info,words,lines,tables in by_page:
        for role,predicate in (('header',lambda l:l['bbox'][3]<info['height_pt']*.12),
                               ('footer',lambda l:l['bbox'][1]>info['height_pt']*.90)):
            repeats[role].update({key(l['text']) for l in lines if predicate(l)})
    for info,words,lines,tables in by_page:
        n=info['page'];words_by_line=defaultdict(list);word_map={w['id']:w for w in words}
        for w in words:words_by_line[w['line_id']].append(w)
        role={}
        for line in lines:
            role[line['id']]=('header' if line['bbox'][3]<info['height_pt']*.12 and repeats['header'][key(line['text'])]>=2 else
                              'footer' if line['bbox'][1]>info['height_pt']*.90 and repeats['footer'][key(line['text'])]>=2 else 'text')
            ww=words_by_line[line['id']]
            record=_element(line['id'],n,line['bbox'],ww,baseline=line['baseline'])
            data['elements']['lines'].append(record)
            if role[line['id']]!='text':data['elements'][role[line['id']]+'s'].append(record)
        blocks=defaultdict(list)
        for line in lines:blocks[line['block_id']].append(line)
        for bid,ll in blocks.items():
            ww=[w for l in ll for w in words_by_line[l['id']]]
            data['elements']['text_blocks'].append(_element(bid,n,_union([l['bbox'] for l in ll]),ww))
        table_words=set();regions=[];line_word_map={}
        for table in tables:
            ww=[w for w in words if _inside(w,table['bbox'])];table_words.update(w['id'] for w in ww)
            table.update(word_ids=[w['id'] for w in ww],text=' '.join(w['text'] for w in ww))
            data['elements']['tables'].append(table)
            flow=sorted(ww,key=lambda w:(round(w['bbox'][1],0),w['bbox'][0]))
            regions.append(Region(id=table['id'],page_number=n,kind='table',bbox=BBox(x0=table['bbox'][0],y0=table['bbox'][1],x1=table['bbox'][2],y1=table['bbox'][3]),
                                  text=table['text'],metadata={'flow_word_ids':[w['id'] for w in flow]}))
        flow_groups=defaultdict(list)
        for line in lines:
            ww=[w for w in words_by_line[line['id']] if w['id'] not in table_words]
            if not ww:continue
            ww=sorted(ww,key=(lambda w:w['index']) if abs(line['direction'][1])>.1 else lambda w:w['bbox'][0])
            fid=line['id']+':flow';line_word_map[fid]=[w['id'] for w in ww]
            box=_union([w['bbox'] for w in ww]);b=BBox(x0=box[0],y0=box[1],x1=box[2],y1=box[3])
            span=TextSpan(id=fid+':span',text=' '.join(w['text'] for w in ww),bbox=b,size=line['font_size'],baseline=tuple(line['baseline']))
            tl=TextLine(id=fid,text=span.text,bbox=b,baseline=span.baseline,direction=tuple(line['direction']),spans=[span])
            flow_groups[(line['block_id'],role[line['id']])].append(tl)
        for (bid,kind),ll in flow_groups.items():
            box=_union([l.bbox.as_tuple() for l in ll])
            regions.append(Region(id=bid+':'+kind,page_number=n,kind=kind,bbox=BBox(x0=box[0],y0=box[1],x1=box[2],y1=box[3]),
                                  text='\n'.join(l.text for l in ll),lines=ll,spans=[s for l in ll for s in l.spans]))
        page_model=Page(number=n,width=info['width_pt'],height=info['height_pt'],classification='native' if words else 'blank',
                        cropbox=BBox(x0=0,y0=0,x1=info['width_pt'],y1=info['height_pt']),regions=regions)
        order_regions(page_model);info['inferred_columns']=page_model.columns if any(r.kind not in ('header','footer') for r in page_model.regions) else 0
        lanes=defaultdict(list)
        for region in page_model.regions:
            ll=sorted(region.lines,key=lambda l:(l.baseline[1],l.bbox.x0))
            ids=region.metadata.get('flow_word_ids',[wid for l in ll for wid in line_word_map[l.id]])
            ww=[word_map[wid] for wid in ids]
            data['logical_words'].extend(ww)
            if region.kind in ('header','footer'):continue
            data['body_words'].extend(ww)
            if region.column>=0:
                lanes[region.column].extend(ww)
                for w in ww:data['word_columns'][w['id']]=region.column
            if region.kind=='table' or not ll:continue
            advances=[b.baseline[1]-a.baseline[1] for a,b in zip(ll,ll[1:]) if b.baseline[1]-a.baseline[1]>1]
            pitch=median(advances) if advances else max(s.size for l in ll for s in l.spans)*1.2
            groups=[]
            for line in ll:
                if not groups or line.baseline[1]-groups[-1][-1].baseline[1]>1.65*pitch:groups.append([])
                groups[-1].append(line)
            for group in groups:
                ids=[wid for l in group for wid in line_word_map[l.id]];pw=[word_map[wid] for wid in ids]
                identifier=f'{n}:paragraph:'+sha256('|'.join(ids).encode()).hexdigest()[:16]
                data['elements']['paragraphs'].append(_element(identifier,n,_union([w['bbox'] for w in pw]),pw,baseline=list(group[0].baseline)))
        for lane,ww in lanes.items():
            data['elements']['columns'].append(_element(f'{n}:lane:{lane}',n,_union([w['bbox'] for w in ww]),ww,lane=lane))
        body=[w for w in data['body_words'] if w['page']==n]
        if body:
            b=_union([w['bbox'] for w in body]);info['visible_body_margins_pt']={'left':b[0],'top':b[1],'right':info['width_pt']-b[2],'bottom':info['height_pt']-b[3]}
        else:info['visible_body_margins_pt']=None
    return data


def _summary(matches,source_count,target_count,matched_targets):
    same=[m for m in matches if m['source_page']==m['target_page']]
    result={'source_elements':source_count,'target_elements':target_count,'matched_elements':len(matches),
            'matched_target_elements':matched_targets,'unmatched_source_elements':source_count-len(matches),
            'unmatched_target_elements':target_count-matched_targets,'same_page_matches':len(same),
            'source_coverage':len(matches)/source_count if source_count else None,
            'target_coverage':matched_targets/target_count if target_count else None,
            'mean_iou':float(np.mean([m['iou'] for m in same])) if same else None}
    for field,label in (('position_error_pt','position_error_pt'),('dx_pt','x_error_pt'),('dy_pt','y_error_pt'),
                         ('width_error_pt','width_error_pt'),('height_error_pt','height_error_pt'),('baseline_error_pt','baseline_error_pt')):
        result.update(_stats([abs(m[field]) for m in same if field in m],label))
    return with_mm(result)


def compare_elements(source,target,limit=80):
    sw,tw=source['words'],target['words']
    pairs=_match_tokens([{**w,'text':normalize_text(w['text'])} for w in sw],[{**w,'text':normalize_text(w['text'])} for w in tw])
    result={};all_differences=[]
    for category in CATEGORIES:
        if category=='images':
            images=_match_images(source['images'],target['images']);matches=images['matches']
            summary=_summary(matches,images['source_images'],images['target_images'],images['matched_images'])
            result[category]={'status':'measured' if images['source_images'] or images['target_images'] else 'not_applicable',
                              'basis':BASES[category],'summary':summary,'matches':matches[:limit],
                              'unmatched_source':images['unmatched_source_records'][:limit],
                              'unmatched_target':images['unmatched_target_records'][:limit],
                              'identity_verified_matches':images['verified_identity_matches'],'heuristic_matches':images['heuristic_matches']}
            continue
        src=source['elements'][category];dst=target['elements'][category]
        smap={wid:r['id'] for r in src for wid in r['word_ids']};tmap={wid:r['id'] for r in dst for wid in r['word_ids']}
        dest={r['id']:r for r in dst};links=defaultdict(Counter)
        for i,j in pairs:
            a=smap.get(sw[i]['id']);b=tmap.get(tw[j]['id'])
            if a and b:links[a][b]+=1
        matches=[];used=Counter()
        for record in src:
            candidates=[dest[k] for k,v in links[record['id']].items()
                        if v>=max(1,math.ceil(min(len(record['word_ids']),len(dest[k]['word_ids']))*.5))]
            if not candidates:continue
            page_votes=Counter()
            for c in candidates:page_votes[c['page']]+=links[record['id']][c['id']]
            page=page_votes.most_common(1)[0][0];dominant=[c for c in candidates if c['page']==page]
            box=_union([c['bbox'] for c in dominant]);target_record={'page':page,'bbox':box,'text':record['text']}
            baseline=next((c.get('baseline') for c in dominant if c.get('baseline')),None)
            if baseline:target_record['baseline']=baseline
            match=_measurement(record,target_record)
            match.update(source_element_id=record['id'],target_element_ids=sorted(c['id'] for c in candidates),
                         target_pages=sorted(page_votes),fragments=len(candidates),
                         matched_word_fraction=sum(links[record['id']][c['id']] for c in candidates)/max(len(record['word_ids']),1))
            matches.append(match)
            for c in candidates:used[c['id']]+=1
        summary=_summary(matches,len(src),len(dst),len(used))
        summary.update(split_source_elements=sum(m['fragments']>1 for m in matches),merged_target_elements=sum(n>1 for n in used.values()))
        status='measured' if src or dst else 'not_detected' if category in ('paragraphs','headers','footers') else 'no_native_grid_evidence' if category=='tables' else 'not_applicable'
        if category=='tables' and any(p['table_detection'].startswith('unavailable') for p in source['pages']):status='partially_measured'
        result[category]={'status':status,'basis':BASES[category],'matching':'exact-word anchors; one-to-many unions and merges reported explicitly',
                          'summary':summary,'matches':sorted(matches,key=lambda m:m['position_error_pt'],reverse=True)[:limit],
                          'unmatched_source':[{'page':r['page'],'bbox_pt':r['bbox'],'text':r['text'][:160]} for r in src if r['id'] not in {m['source_element_id'] for m in matches}][:limit]}
    layout=[];margins=[]
    for i in range(max(len(source['pages']),len(target['pages']))):
        a=source['pages'][i] if i<len(source['pages']) else None;b=target['pages'][i] if i<len(target['pages']) else None
        if a is None or b is None:
            layout.append({'kind':'missing_page' if b is None else 'extra_page','page':i+1});continue
        if a['inferred_columns']!=b['inferred_columns']:layout.append({'kind':'inferred_column_count','page':i+1,'source':a['inferred_columns'],'target':b['inferred_columns']})
        if abs(a['width_pt']-b['width_pt'])>.1 or abs(a['height_pt']-b['height_pt'])>.1:
            layout.append({'kind':'page_size','page':i+1,'source_pt':[a['width_pt'],a['height_pt']],'target_pt':[b['width_pt'],b['height_pt']]})
        ma=a['visible_body_margins_pt'];mb=b['visible_body_margins_pt']
        if ma is not None and mb is not None:
            delta={k:mb[k]-ma[k] for k in ma}
            margins.append({'page':i+1,'source_pt':ma,'target_pt':mb,'delta_pt':delta,'absolute_error_mm':{k:abs(v)*MM_PER_PT for k,v in delta.items()}})
    page_drift=[];column_drift=[]
    for i,j in pairs:
        a,b=sw[i],tw[j]
        if a['page']!=b['page']:page_drift.append({'text':a['text'],'source_page':a['page'],'target_page':b['page'],'source_bbox_pt':a['bbox'],'target_bbox_pt':b['bbox']})
        ca=source['word_columns'].get(a['id']);cb=target['word_columns'].get(b['id'])
        if ca is not None and cb is not None and ca!=cb:column_drift.append({'text':a['text'],'source_page':a['page'],'target_page':b['page'],'source_lane':ca,'target_lane':cb})
    errors=[v for m in margins for v in m['absolute_error_mm'].values()]
    return {'categories':result,'margins':{'basis':'visible body ink bounds, not inferred actual Word section margins','pages':margins,
              **_stats(errors,'margin_error_mm')},'layout':{'difference_count':len(layout),'differences':layout,
              'page_drift_words':len(page_drift),'page_drift_locations':page_drift[:limit],
              'column_lane_drift_words':len(column_drift),'column_drift_locations':column_drift[:limit],
              'column_note':'Lane identity is inferred from visible text; native Word column properties are audited separately.'},
            'coordinate_system':'displayed crop-relative PDF points; 1pt=25.4/72mm; absolute coordinates, no registration',
            'sample_limit':limit,'table_availability':{'source':[p['table_detection'] for p in source['pages']],'target':[p['table_detection'] for p in target['pages']]}}

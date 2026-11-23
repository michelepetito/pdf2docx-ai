"""Independent text, geometry and foreground measurements on rendered PDFs.

All geometry is measured BEFORE image registration in displayed/cropped PDF
points. Exact token text establishes identity; distance only disambiguates
repetitions. This is a diagnostic matcher, not semantic ground truth.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import math
from pathlib import Path
import re
import unicodedata

import numpy as np
import pymupdf
from PIL import Image,ImageChops,ImageDraw,ImageFilter

from .metrics import ssim_map,text_metrics
from ..pdf.renderer import render_page
from ..pdf.runtime import PDF_LOCK

# The pinned detector otherwise emits a product recommendation on stdout.
pymupdf.no_recommend_layout()


def _normalize(text):
    return " ".join(unicodedata.normalize("NFC",text).split())


def _box(rect,page):
    return [float(v) for v in pymupdf.Rect(rect)*page.rotation_matrix]


def _point(point,page):
    return [float(v) for v in pymupdf.Point(point)*page.rotation_matrix]


def _extract(page,number):
    """Retain line baselines so font ascenders do not mimic position drift."""
    lines=[];by_id={}
    data=page.get_text("dict",flags=pymupdf.TEXT_PRESERVE_WHITESPACE|pymupdf.TEXT_PRESERVE_LIGATURES)
    for bi,block in enumerate(data["blocks"]):
        if block["type"]!=0: continue
        for li,line in enumerate(block["lines"]):
            spans=[s for s in line["spans"] if s["text"].strip()]
            if not spans: continue
            largest=max(s["size"] for s in spans)
            chosen=max((s for s in spans if s["size"]>=largest*.8),key=lambda s:len(s["text"]))
            origin=_point(chosen.get("origin",(line["bbox"][0],line["bbox"][3])),page)
            key=(block.get("number",bi),li)
            record=dict(page=number,id=f"{number}:{key[0]}:{li}",index=len(lines),
                        text=_normalize("".join(s["text"] for s in spans)),bbox=_box(line["bbox"],page),
                        baseline=origin,font=chosen["font"],font_size=float(chosen["size"]),
                        ascender=float(chosen.get("ascender",0)),descender=float(chosen.get("descender",0)),
                        direction=list(line.get("dir",(1.,0.))))
            lines.append(record);by_id[key]=record
    words=[]
    for wi,word in enumerate(page.get_text("words",sort=False)):
        text=_normalize(word[4])
        if not text: continue
        line=by_id.get((word[5],word[6]))
        words.append(dict(page=number,index=wi,text=text,bbox=_box(word[:4],page),
                          line_id=line["id"] if line else None,baseline=line["baseline"] if line else None,
                          font=line["font"] if line else None,font_size=line["font_size"] if line else None))
    return words,lines


def _center(box):
    return ((box[0]+box[2])/2,(box[1]+box[3])/2)


def _cost(a,b):
    ac,bc=_center(a["bbox"]),_center(b["bbox"])
    return abs(a["page"]-b["page"])*10000+math.hypot(ac[0]-bc[0],ac[1]-bc[1])


def _match_tokens(source,target):
    """Exact one-to-one tokens, including text moved to another page.

    Bounded edge lists avoid quadratic allocation for extremely common words.
    Positional ties for repeated words remain a documented ambiguity.
    """
    src=defaultdict(list);dst=defaultdict(list)
    for i,item in enumerate(source): src[item["text"]].append(i)
    for i,item in enumerate(target): dst[item["text"]].append(i)
    pairs=[]
    for text,indices in src.items():
        candidates=dst.get(text,[])
        if not candidates: continue
        available=set(candidates)
        if len(indices)*len(candidates)<=20000:
            edges=sorted((_cost(source[i],target[j]),i,j) for i in indices for j in candidates)
            used=set()
            for _,i,j in edges:
                if i not in used and j in available:
                    pairs.append((i,j));used.add(i);available.remove(j)
        else:
            pages=defaultdict(set)
            for j in candidates: pages[target[j]["page"]].add(j)
            for i in indices:
                if not available: break
                local=pages.get(source[i]["page"],set())&available
                j=min(local or available,key=lambda j:_cost(source[i],target[j]))
                pairs.append((i,j));available.remove(j)
    return sorted(pairs)


def _iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=max(0,a[2]-a[0])*max(0,a[3]-a[1])+max(0,b[2]-b[0])*max(0,b[3]-b[1])-intersection
    return intersection/union if union>0 else 1.


def _measurement(a,b):
    sa,ta=a["bbox"],b["bbox"]
    dx,dy=ta[0]-sa[0],ta[1]-sa[1]
    result=dict(text=a["text"],source_page=a["page"],target_page=b["page"],source_bbox=sa,target_bbox=ta,
                dx_pt=dx,dy_pt=dy,width_error_pt=(ta[2]-ta[0])-(sa[2]-sa[0]),
                height_error_pt=(ta[3]-ta[1])-(sa[3]-sa[1]),position_error_pt=math.hypot(dx,dy),
                corner_error_pt=float(np.mean([math.hypot(dx,dy),math.hypot(ta[2]-sa[2],ta[3]-sa[3])])),
                iou=_iou(sa,ta),source_baseline=a.get("baseline"),target_baseline=b.get("baseline"),
                source_font=a.get("font"),target_font=b.get("font"),
                source_font_size=a.get("font_size"),target_font_size=b.get("font_size"))
    if a.get("baseline") and b.get("baseline"):
        result["baseline_dy_pt"]=b["baseline"][1]-a["baseline"][1]
        result["baseline_error_pt"]=abs(result["baseline_dy_pt"])
    return result


def _stats(values,prefix):
    if not values: return {f"{key}_{prefix}":None for key in ("mean","median","p90","p95","max")}
    return {f"{key}_{prefix}":float(value) for key,value in zip(
        ("mean","median","p90","p95","max"),
        (np.mean(values),np.median(values),np.percentile(values,90),np.percentile(values,95),max(values)))}


def _geometry(matches,source_count,target_count):
    same_page=[m for m in matches if m["source_page"]==m["target_page"]]
    return dict(source_words=source_count,target_words=target_count,matched_words=len(matches),
                matched_same_page_words=len(same_page),match_coverage=len(matches)/source_count if source_count else None,
                target_match_coverage=len(matches)/target_count if target_count else None,
                unmatched_source_words=source_count-len(matches),unmatched_target_words=target_count-len(matches),
                page_drift_words=len(matches)-len(same_page),
                mean_iou=float(np.mean([m["iou"] for m in same_page])) if same_page else None,
                **_stats([m["position_error_pt"] for m in same_page],"position_error_pt"),
                **_stats([m["baseline_error_pt"] for m in same_page if "baseline_error_pt" in m],"baseline_error_pt"),
                **_stats([m["corner_error_pt"] for m in same_page],"corner_error_pt"),
                **_stats([abs(m["width_error_pt"]) for m in same_page],"width_error_pt"),
                **_stats([abs(m["height_error_pt"]) for m in same_page],"height_error_pt"))


def _counter_delta(source,target):
    missing=source-target;extra=target-source
    return dict(missing_count=sum(missing.values()),excess_count=sum(extra.values()),
                missing=dict(missing.most_common(50)),excess=dict(extra.most_common(50)))


def _textual(source,target):
    a=[w["text"] for w in source];b=[w["text"] for w in target]
    reference,hypothesis=" ".join(a)," ".join(b);ca,cb=Counter(a),Counter(b)
    counts=_counter_delta(ca,cb)
    reference_chars="".join(reference.split());hypothesis_chars="".join(hypothesis.split())
    characters=_counter_delta(Counter(reference_chars),Counter(hypothesis_chars))
    result=dict(status="measured_native_pdf_text" if a else "unavailable_no_source_text",
                reference="native PDF extraction; not OCR ground truth",source_words=len(a),target_words=len(b),
                source_characters=len(reference),target_characters=len(hypothesis),token_sequence_equal=a==b,
                content_token_counts_equal=ca==cb,missing_words=counts["missing_count"],excess_words=counts["excess_count"],
                missing_token_samples=counts["missing"],excess_token_samples=counts["excess"],
                non_whitespace_character_sequence_equal=reference_chars==hypothesis_chars,
                non_whitespace_character_counts_equal=Counter(reference_chars)==Counter(hypothesis_chars),
                missing_characters=characters["missing_count"],excess_characters=characters["excess_count"],
                potential_duplicate_words=sum(n for token,n in (cb-ca).items() if token in ca))
    if not a:
        result.update(cer=None,wer=None);return result
    try: result.update(text_metrics(reference,hypothesis))
    except ValueError as exc: result.update(cer=None,wer=None,accuracy_reason=str(exc))
    numbers=lambda text:Counter(re.findall(r"[+−-]?\d+(?:[.,:/−-]\d+)*%?",text))
    symbols=lambda text:Counter(c for c in text if unicodedata.category(c).startswith("S"))
    result["numbers_dates"]=_counter_delta(numbers(reference),numbers(hypothesis))
    result["symbols"]=_counter_delta(symbols(reference),symbols(hypothesis))
    return result


def _line_matches(source_lines,target_lines,source_words,target_words,pairs):
    """Aggregate source lines from exact tokens despite target rewrapping."""
    target_by_line={x["id"]:x for x in target_lines};source_by_line={x["id"]:x for x in source_lines}
    source_counts=Counter(w["line_id"] for w in source_words);grouped=defaultdict(list)
    for i,j in pairs:
        if source_words[i]["line_id"]: grouped[source_words[i]["line_id"]].append(target_words[j])
    matches=[]
    for line_id,words in grouped.items():
        original=source_by_line.get(line_id)
        if not original or len(words)/max(source_counts[line_id],1)<.8: continue
        target_page=Counter(w["page"] for w in words).most_common(1)[0][0]
        words=[w for w in words if w["page"]==target_page]
        if len(words)/max(source_counts[line_id],1)<.8: continue
        line_ids={w["line_id"] for w in words if w["line_id"] in target_by_line}
        destination_lines=[target_by_line[k] for k in line_ids]
        box=[min(w["bbox"][0] for w in words),min(w["bbox"][1] for w in words),max(w["bbox"][2] for w in words),max(w["bbox"][3] for w in words)]
        target=dict(page=target_page,bbox=box,text=" ".join(w["text"] for w in words))
        if destination_lines:
            first=min(destination_lines,key=lambda l:(l["bbox"][1],l["bbox"][0],l["index"]))
            target.update(baseline=first["baseline"],font=first["font"],font_size=first["font_size"])
        measurement=_measurement(original,target)
        measurement.update(source_line_id=line_id,target_line_ids=sorted(line_ids),
                           matched_word_fraction=len(words)/max(source_counts[line_id],1),target_wrap_lines=len(line_ids))
        matches.append(measurement)
    return matches


def _image_records(page,number):
    records=[]
    for image in page.get_image_info(hashes=True):
        digest=image.get("digest",b"")
        records.append(dict(page=number,index=len(records),bbox=_box(image["bbox"],page),
                            digest=digest.hex() if isinstance(digest,bytes) else str(digest),width=image.get("width"),height=image.get("height")))
    return records


def _match_images(source,target):
    pairs=[];remaining=set(range(len(target)))
    for image in source:
        candidates=[j for j in remaining if target[j]["digest"]==image["digest"]];method="decoded_pixel_digest"
        if not candidates:
            ratio=(image["bbox"][2]-image["bbox"][0])/max(image["bbox"][3]-image["bbox"][1],.01)
            candidates=[j for j in remaining if target[j]["page"]==image["page"] and abs(
                (target[j]["bbox"][2]-target[j]["bbox"][0])/max(target[j]["bbox"][3]-target[j]["bbox"][1],.01)-ratio)<.08*max(1,ratio)]
            method="aspect_and_position_heuristic"
        if not candidates: continue
        j=min(candidates,key=lambda j:_cost(image,target[j]));remaining.remove(j)
        match=_measurement({**image,"text":"image"},{**target[j],"text":"image"});match["method"]=method;pairs.append(match)
    return dict(source_images=len(source),target_images=len(target),matched_images=len(pairs),
                unmatched_source_images=len(source)-len(pairs),unmatched_target_images=len(target)-len(pairs),
                verified_identity_matches=sum(m["method"]=="decoded_pixel_digest" for m in pairs),
                heuristic_matches=sum(m["method"]!="decoded_pixel_digest" for m in pairs),matches=pairs)


def _foreground(a,b,score_map):
    aa=np.asarray(a.convert("RGB"),dtype=np.float32);bb=np.asarray(b.convert("RGB"),dtype=np.float32)
    ia=aa.min(axis=2)<225;ib=bb.min(axis=2)<225;union=ia|ib;intersection=ia&ib
    denom=int(ia.sum()+ib.sum())
    broad=np.asarray(Image.fromarray((union*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7)))>0
    valid=np.zeros(union.shape,dtype=bool);valid[3:-3,3:-3]=True;broad&=valid
    return dict(ink_threshold=225,source_ink_pixels=int(ia.sum()),target_ink_pixels=int(ib.sum()),
                ink_iou=float(intersection.sum()/union.sum()) if union.any() else 1.,ink_f1=float(2*intersection.sum()/denom) if denom else 1.,
                foreground_mean_absolute_pixel_error=float(np.abs(aa-bb)[union].mean()/255) if union.any() else 0.,
                foreground_ssim=float(score_map[broad].mean()) if broad.any() else 1.,foreground_fraction=float(union.mean()),
                note="Unregistered ink masks; foreground SSIM uses 3px neighbourhood around ink.")


def _draw_assets(ca,cb,difference,matches,path,index,width_pt,height_pt):
    path.mkdir(parents=True,exist_ok=True);gray=ca.convert("L").convert("RGB")
    intensity=np.asarray(difference.convert("L"),dtype=np.float32)/255;heat=np.asarray(gray,dtype=np.float32)
    heat[:,:,0]=np.maximum(heat[:,:,0],255*intensity);heat[:,:,1]*=1-intensity;heat[:,:,2]*=1-intensity
    geometry=ca.copy();draw=ImageDraw.Draw(geometry);sx,sy=ca.width/max(width_pt,1),ca.height/max(height_pt,1)
    for match in sorted(matches,key=lambda m:m["position_error_pt"],reverse=True)[:80]:
        for key,color in (("source_bbox",(0,140,80)),("target_bbox",(190,30,120))):
            box=match[key];draw.rectangle((box[0]*sx,box[1]*sy,box[2]*sx,box[3]*sy),outline=color,width=2)
    result={}
    for name,img in (("original",ca),("result",cb),("overlay",Image.blend(ca,cb,.5)),("diff",difference),
                     ("heatmap",Image.fromarray(heat.astype(np.uint8))),("geometry",geometry)):
        filename=path/f"page-{index+1:04d}-{name}.jpg";preview=img.copy();preview.thumbnail((900,1200));preview.save(filename,quality=85)
        result[name+"_path"]=str(filename)
    return result


def _table_count(page):
    try:
        with pymupdf.open() as copy:
            copy.insert_pdf(page.parent,from_page=page.number,to_page=page.number)
            if copy[0].rotation or copy[0].cropbox!=copy[0].mediabox: return None
            return len(copy[0].find_tables().tables)
    except Exception: return None


def evaluate_pdf_pair(original: Path,rendered: Path,assets: Path|None=None,
                      include_images: bool=False,dpi: int=100) -> dict:
    """Measure a pair; no assets means bounded-cost optimizer evaluation.

    include_images enables decoded image identity/position matching. Raster
    appearance is always measured. No registration improves the scores.
    """
    with PDF_LOCK,pymupdf.open(original) as a,pymupdf.open(rendered) as b:
        source_words=[];target_words=[];source_lines=[];target_lines=[];source_images=[];target_images=[]
        for number,page in enumerate(a,1):
            words,lines=_extract(page,number);source_words.extend(words);source_lines.extend(lines)
            if include_images: source_images.extend(_image_records(page,number))
        for number,page in enumerate(b,1):
            words,lines=_extract(page,number);target_words.extend(words);target_lines.extend(lines)
            if include_images: target_images.extend(_image_records(page,number))
        pairs=_match_tokens(source_words,target_words)
        word_matches=[_measurement(source_words[i],target_words[j]) for i,j in pairs]
        line_matches=_line_matches(source_lines,target_lines,source_words,target_words,pairs)
        results=[]
        for index in range(max(len(a),len(b))):
            source=a[index] if index<len(a) else None;target=b[index] if index<len(b) else None
            width=max(source.rect.width if source else 0,target.rect.width if target else 0);height=max(source.rect.height if source else 0,target.rect.height if target else 0)
            effective_dpi=min(float(dpi),72*math.sqrt(2_500_000/max(width*height,1)))
            ai,_=render_page(source,effective_dpi,2_500_000) if source else (None,None)
            bi,_=render_page(target,effective_dpi,2_500_000) if target else (None,None)
            size=(max(ai.width if ai else 0,bi.width if bi else 0,7),max(ai.height if ai else 0,bi.height if bi else 0,7))
            ca=Image.new("RGB",size,"white");cb=Image.new("RGB",size,"white")
            if ai: ca.paste(ai,(0,0))
            if bi: cb.paste(bi,(0,0))
            difference=ImageChops.difference(ca,cb);arr=np.asarray(difference);score_map=ssim_map(ca,cb)
            matches=[m for m in word_matches if m["source_page"]==index+1];lm=[m for m in line_matches if m["source_page"]==index+1]
            sw=[w for w in source_words if w["page"]==index+1];tw=[w for w in target_words if w["page"]==index+1]
            same=[m for m in matches if m["target_page"]==index+1]
            fg=_foreground(ca,cb,score_map)
            original_tables=_table_count(source) if source and assets is not None else None
            target_tables=_table_count(target) if target and assets is not None else None
            metrics=dict(page=index+1,ssim=float(score_map[3:-3,3:-3].mean()),mean_absolute_pixel_error=float(arr.mean()/255),
                         changed_pixel_fraction=float((arr.max(axis=2)>25).mean()),alignment_shift_px=[0,0],effective_dpi=effective_dpi,
                         source_page_missing=source is None,target_page_missing=target is None,
                         original_size_pt=[source.rect.width,source.rect.height] if source else None,
                         rendered_size_pt=[target.rect.width,target.rect.height] if target else None,
                         geometry=_geometry(matches,len(sw),len(tw)),foreground=fg,word_matches=matches,line_matches=lm,
                         matched_text_blocks=len(lm),mean_block_displacement_pt=float(np.mean([m["position_error_pt"] for m in lm if m["target_page"]==index+1])) if any(m["target_page"]==index+1 for m in lm) else None,
                         original_detected_tables=original_tables,rendered_detected_tables=target_tables,
                         table_detection_changed=(original_tables!=target_tables) if original_tables is not None and target_tables is not None else None)
            target_matched=sum(m["target_page"]==index+1 for m in word_matches)
            metrics["geometry"]["unmatched_target_words"]=len(tw)-target_matched
            metrics["geometry"]["target_match_coverage"]=target_matched/len(tw) if tw else None
            if assets is not None and index<50: metrics.update(_draw_assets(ca,cb,difference,same,Path(assets),index,width,height))
            results.append(metrics);ca.close();cb.close()
            if ai: ai.close()
            if bi: bi.close()
        return dict(status="measured",original_pages=len(a),rendered_pages=len(b),page_count_difference=len(b)-len(a),
                    normalization=f"{dpi}dpi (bounded raster), common white canvas, no registration/stretching; absolute PDF points",
                    note="SSIM is visual, not OCR accuracy. Exact token matching with positional tie-breaks; repeated identical tokens can remain ambiguous.",
                    geometry=_geometry(word_matches,len(source_words),len(target_words)),textual=_textual(source_words,target_words),
                    foreground={key:float(np.mean([p["foreground"][key] for p in results])) if results else None for key in ("ink_iou","ink_f1","foreground_mean_absolute_pixel_error","foreground_ssim")},
                    mean_ssim=float(np.mean([p["ssim"] for p in results])) if results else None,
                    images=_match_images(source_images,target_images) if include_images else {"status":"not_requested"},pages=results)


def compare_pdfs(original: Path,rendered: Path,assets: Path) -> dict:
    return evaluate_pdf_pair(original,rendered,assets,include_images=True)

from pathlib import Path
from PIL import Image,ImageChops,ImageEnhance
import numpy as np
import pymupdf
from .metrics import ssim
from ..pdf.renderer import render_page


def compare_pdfs(original: Path, rendered: Path, assets: Path) -> dict:
    assets.mkdir(parents=True,exist_ok=True)
    results=[]
    with pymupdf.open(original) as a,pymupdf.open(rendered) as b:
        for index in range(min(len(a),len(b))):
            ai,_=render_page(a[index],100,8_000_000);bi,_=render_page(b[index],100,8_000_000)
            # One physical point scale, white padded canvas; no anisotropic warping.
            size=(max(ai.width,bi.width),max(ai.height,bi.height))
            ca=Image.new("RGB",size,"white");cb=Image.new("RGB",size,"white")
            ca.paste(ai,(0,0));cb.paste(bi,(0,0))
            # Small translational registration at a reduced resolution, bounded to 3pt.
            shift=(0,0)
            if ai.size==bi.size:
                thumb=(max(7,size[0]//4),max(7,size[1]//4))
                aa=np.asarray(ca.convert("L").resize(thumb),dtype=float)
                bb=np.asarray(cb.convert("L").resize(thumb),dtype=float)
                best=float(np.mean(np.abs(aa-bb)))
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        trial=np.full_like(bb,255)
                        sy=slice(max(0,-dy),min(bb.shape[0],bb.shape[0]-dy));sx=slice(max(0,-dx),min(bb.shape[1],bb.shape[1]-dx))
                        ty=slice(max(0,dy),min(bb.shape[0],bb.shape[0]+dy));tx=slice(max(0,dx),min(bb.shape[1],bb.shape[1]+dx))
                        trial[ty,tx]=bb[sy,sx]
                        err=float(np.mean(np.abs(aa-trial)))
                        if err<best: best=err;shift=(dx*4,dy*4)
                aligned=Image.new("RGB",size,"white");aligned.paste(cb,shift);cb=aligned
            difference=ImageChops.difference(ca,cb)
            overlay=Image.blend(ca,cb,.5)
            arr=np.asarray(difference)
            metrics=dict(page=index+1,ssim=ssim(ca,cb),mean_absolute_pixel_error=float(arr.mean()/255),
                         changed_pixel_fraction=float((arr.max(axis=2)>25).mean()),alignment_shift_px=list(shift),
                         original_size_pt=list(a[index].rect)[2:],rendered_size_pt=list(b[index].rect)[2:])
            if index<50:
                for name,img in (("original",ca),("result",cb),("overlay",overlay),("diff",ImageEnhance.Contrast(difference).enhance(3))):
                    path=assets/f"page-{index+1:04d}-{name}.jpg"
                    preview=img.copy();preview.thumbnail((900,1200));preview.save(path,quality=80)
                    metrics[name+"_path"]=str(path)
            # Text matching is measured separately in points, before registration.
            src=a[index].get_text("blocks");dst=b[index].get_text("blocks")
            displacements=[]
            from difflib import SequenceMatcher
            remaining=[x for x in dst if x[6]==0]
            for block in (x for x in src if x[6]==0):
                text=" ".join(block[4].split())
                candidates=[(SequenceMatcher(None,text," ".join(x[4].split())).ratio(),j,x) for j,x in enumerate(remaining)]
                if not candidates: break
                score,j,match=max(candidates,key=lambda x:x[0])
                if score>=.8:
                    displacements.append(float(((block[0]-match[0])**2+(block[1]-match[1])**2)**.5));remaining.pop(j)
            metrics["matched_text_blocks"]=len(displacements)
            metrics["mean_block_displacement_pt"]=float(np.mean(displacements)) if displacements else None
            metrics["original_detected_tables"]=len(a[index].find_tables().tables)
            metrics["rendered_detected_tables"]=len(b[index].find_tables().tables)
            metrics["table_detection_changed"]=metrics["original_detected_tables"]!=metrics["rendered_detected_tables"]
            results.append(metrics)
        return dict(status="measured",original_pages=len(a),rendered_pages=len(b),page_count_difference=len(b)-len(a),
                    normalization="100dpi, common white canvas, bounded translation <=4px; no stretching",
                    note="SSIM misura aspetto visivo, non precisione OCR. Matching geometrico testuale euristico.",pages=results)

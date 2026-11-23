"""Page-wise conversion, persistent checkpoints and explicitly local OCR."""
from __future__ import annotations

from collections import Counter,defaultdict
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Callable

import psutil
import pymupdf
from pydantic import BaseModel,Field

from . import __version__
from .config import Settings
from .document.models import BBox,Document,Page,Region,TextSpan,TableCell
from .document.geometry import PageTransform
from .document.reading_order import order_regions
from .pdf.inspector import open_pdf
from .pdf.runtime import PDF_LOCK
from .pdf.extractor import extract_page
from .pdf.renderer import render_page,crop_region
from .ocr.selector import select_engine,create_engine
from .ocr.base import OCRUnavailableError
from .quality.enhancer import QualityEnhancer
from .quality.metrics import text_metrics
from .quality.validator import structural_validation,visual_validation
from .quality.reporting import write_report
from .reconstruction.engine import DocumentReconstructionEngine

# MuPDF explicitly does not support multithreaded use. In-process conversions
# are serialized; benchmark parallelism uses isolated processes instead.
_CONVERSION_LOCK=PDF_LOCK


class ConversionResult(BaseModel):
    output_path: str
    report_path: str
    json_path: str
    model_path: str
    searchable_path: str|None=None
    performance: dict=Field(default_factory=dict)
    warnings: list[str]=Field(default_factory=list)


def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024**2),b""): digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path,data):
    temporary=path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temporary,path)


@contextmanager
def output_lock(path: Path):
    lock=path.with_suffix(path.suffix+".lock")
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        try:
            pid=int(lock.read_text())
            if psutil.pid_exists(pid): raise FileExistsError(f"Conversione già attiva: {lock}")
        except (ValueError,OSError):
            raise FileExistsError(f"Lock non valido: rimuovere manualmente {lock}")
        lock.unlink()
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        os.write(fd,str(os.getpid()).encode());os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


class MemorySampler:
    def __init__(self):
        self.stop=threading.Event();self.peak=0;self.children_measured=True
        self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        process=psutil.Process()
        while not self.stop.is_set():
            try:
                rss=process.memory_info().rss
                try: rss+=sum(c.memory_info().rss for c in process.children(recursive=True) if c.is_running())
                except (psutil.Error,OSError): self.children_measured=False
                self.peak=max(self.peak,rss)
            except (psutil.Error,OSError): pass
            self.stop.wait(.05)
    def __enter__(self): self.thread.start();return self
    def __exit__(self,*args): self.stop.set();self.thread.join()


def _recognition_regions(result,box: BBox,crop,number: int,path: Path,native: list[Region]) -> list[Region]:
    transform=PageTransform(box.width,box.height,crop.width,crop.height)
    common=dict(page_number=number,source="ocr",engine=result.engine,confidence=result.confidence,
                crop_path=str(path),metadata={"ocr_format":result.format})
    if result.format=="html" and "<table" in result.text.lower():
        from lxml import html
        root=html.fromstring(result.text)
        tables=root.xpath("//table")
        if tables:
            cells=[];occupied=set();ncols=0
            for ri,row in enumerate(tables[0].xpath(".//tr")):
                ci=0
                for cell in row.xpath("./td|./th"):
                    while (ri,ci) in occupied: ci+=1
                    rs=max(1,min(1000,int(cell.get("rowspan","1"))))
                    cs=max(1,min(100,int(cell.get("colspan","1"))))
                    cells.append(TableCell(row=ri,col=ci,text=cell.text_content(),rowspan=rs,colspan=cs))
                    for rr in range(ri,ri+rs):
                        for cc in range(ci,ci+cs): occupied.add((rr,cc))
                    ci+=cs;ncols=max(ncols,ci)
            if cells:
                return [Region(**common,kind="table",bbox=box,text=result.text,cells=cells,
                               rows=max(c.row+c.rowspan for c in cells),cols=ncols)]
    groups=defaultdict(list)
    for word in result.words: groups[word.line].append(word)
    regions=[]
    if groups:
        for words in groups.values():
            x0=min(w.bbox.x0 for w in words);y0=min(w.bbox.y0 for w in words)
            x1=max(w.bbox.x1 for w in words);y1=max(w.bbox.y1 for w in words)
            local=transform.pixels_to_pdf(BBox(x0=x0,y0=y0,x1=x1,y1=y1))
            absolute=BBox(x0=box.x0+local.x0,y0=box.y0+local.y0,x1=box.x0+local.x1,y1=box.y0+local.y1)
            text=" ".join(w.text for w in words).strip()
            # Native/OCR duplicate removal needs both geometry and text agreement.
            norm=lambda s: " ".join(s.split()).casefold()
            if any(absolute.coverage(n.bbox)>.45 and norm(text) in norm(n.text) for n in native): continue
            size=max(5,min(50,absolute.height*.82))
            spans=[TextSpan(text=text,bbox=absolute,size=size)]
            regions.append(Region(**{**common,"metadata":{**common["metadata"],"font_size":size,"line_count":1}},bbox=absolute,text=text,spans=spans))
    elif result.text.strip():
        text=result.text.strip()
        if not any(" ".join(text.split())==" ".join(n.text.split()) and box.coverage(n.bbox)>.5 for n in native):
            kind="formula" if result.format=="latex" else "text"
            regions.append(Region(**common,bbox=box,text=text,kind=kind))
    return regions


def _mark_repeated_parts(model):
    counts=Counter()
    for page in model.pages:
        seen=set()
        for r in page.regions:
            if r.text and r.bbox.y1<page.height*.12:
                key=re.sub(r"\d+","#"," ".join(r.text.split()))
                seen.add(key)
        counts.update(seen)
    for page in model.pages:
        for r in page.regions:
            key=re.sub(r"\d+","#"," ".join(r.text.split()))
            if len(model.pages)>1 and r.kind in ("text","title") and r.bbox.y1<page.height*.12 and counts[key]>=2:
                r.kind="header"
        order_regions(page)


def _searchable_pdf(source,model,path):
    with pymupdf.open(source) as pdf:
        for page_model in model.pages:
            page=pdf[page_model.number-1]
            for r in page_model.regions:
                if r.source!="ocr" or not r.text or r.kind=="table": continue
                rect=pymupdf.Rect(r.bbox.as_tuple())*page.derotation_matrix
                lines=r.text.splitlines() or [r.text]
                font=max(3,min(20,rect.height/max(1,len(lines))*.75))
                for i,line in enumerate(lines):
                    # Invisible Unicode text layer, independent of the visible source.
                    page.insert_text((max(0,rect.x0),max(font,rect.y0+(i+1)*font)),line,
                                     fontsize=font,fontname="helv",render_mode=3,overlay=True)
        pdf.save(path,garbage=4,deflate=True)


def convert(input_path: Path,output_path: Path,settings: Settings|None=None,
            progress: Callable[[float,str],None]|None=None,ocr_engine=None) -> ConversionResult:
    settings=settings or Settings()
    if settings.engine=="compare":
        if ocr_engine is not None: raise ValueError("compare non supporta engine iniettato")
        return compare(input_path,output_path.with_suffix(".comparison.html"),settings,output_path=output_path)
    with _CONVERSION_LOCK:
        return _convert(input_path,output_path,settings,progress,ocr_engine)


def _convert(input_path,output_path,settings,progress,ocr_engine):
    start=time.perf_counter();ocr_seconds=0.;cache_hits=0
    source=Path(input_path).resolve();out=Path(output_path).resolve()
    if out.suffix.lower()!=".docx": raise ValueError("Il file di uscita deve avere estensione .docx")
    if settings.mode=="visual" and not out.stem.endswith(".visual"): out=out.with_name(out.stem+".visual.docx")
    if out==source: raise ValueError("Ingresso e uscita devono essere distinti")
    out.parent.mkdir(parents=True,exist_ok=True)
    final=dict(docx=out,report=out.with_suffix(".quality.html"),json=out.with_suffix(".quality.json"),model=out.with_suffix(".model.json"))
    if settings.searchable_pdf: final["searchable"]=out.with_suffix(".searchable.pdf")
    for p in final.values():
        if p.exists() and not settings.overwrite: raise FileExistsError(f"File già esistente: {p}; usare --overwrite esplicitamente")
    notify=progress or (lambda value,message:None)
    engine=ocr_engine;initialized=False;secondary=None;layout_detector=None
    # Validate before opening a work directory or loading any model.
    with open_pdf(source,settings) as check: page_count=len(check)
    digest=sha256(source)
    work=out.with_suffix(".work");work.mkdir(mode=0o700,exist_ok=True)
    work.chmod(0o700)
    settings_data=settings.model_dump(mode="json",exclude={"overwrite","resume","ground_truth","validate_visual","renderer"})
    fingerprint=hashlib.sha256(json.dumps([__version__,digest,settings_data,type(ocr_engine).__name__ if ocr_engine else None],sort_keys=True).encode()).hexdigest()
    with output_lock(out),MemorySampler() as memory:
        for destination in final.values():
            if destination.exists() and not settings.overwrite:
                raise FileExistsError(f"File già esistente: {destination}")
        assets=work/"assets";assets.mkdir(exist_ok=True)
        manifest=work/"manifest.json"
        matching=False
        if settings.resume and manifest.is_file():
            try: matching=json.loads(manifest.read_text()).get("fingerprint")==fingerprint
            except (ValueError,OSError): pass
        if not matching:
            # A new manifest must never legitimize old page checkpoints after
            # an interrupted run with changed settings/source.
            for old in work.glob("page-*.json"): old.unlink()
        atomic_json(manifest,dict(fingerprint=fingerprint,version=__version__,source_sha256=digest))
        model=Document(source_path=str(source),source_sha256=digest,
                       metadata={"converter_version":__version__,"settings":settings_data,"coordinates":"displayed crop-relative PDF points"})
        issues=[];enhancer=QualityEnhancer()
        def recognize(crop,kind):
            nonlocal engine,initialized,ocr_seconds
            before=time.perf_counter()
            if engine is None: engine=select_engine(settings)
            if not initialized: engine.initialize();initialized=True
            result=engine.recognize(crop,kind,settings.language)
            ocr_seconds+=time.perf_counter()-before
            return result
        try:
            with open_pdf(source,settings) as pdf:
                for i,page in enumerate(pdf):
                    notify(.05+.70*i/page_count,f"Pagina {i+1}/{page_count}: analisi")
                    checkpoint=work/f"page-{i+1:04d}.json"
                    restored=None
                    if matching and checkpoint.is_file():
                        try:
                            restored=Page.model_validate_json(checkpoint.read_text())
                            paths=[restored.preview_path]+[p for r in restored.regions for p in (r.crop_path,r.image_path) if p]
                            if any(p and not Path(p).is_file() for p in paths): restored=None
                        except (ValueError,OSError): restored=None
                    if restored is not None:
                        model.pages.append(restored);cache_hits+=1
                        issues.extend(enhancer.inspect(restored));continue
                    image,transform=render_page(page,settings.dpi,settings.max_pixels)
                    preview=assets/f"p{i+1:04d}-original.png";image.save(preview)
                    structured=extract_page(page,i+1,image,transform,assets)
                    structured.preview_path=str(preview)
                    native=[r for r in structured.regions if r.text and r.source=="native"]
                    if settings.mode=="editable" or settings.searchable_pdf:
                        targets=[]
                        if structured.classification=="scanned":
                            if settings.layout=="ppdoclayout":
                                from .layout.ppdoclayout import PPDocLayoutDetector
                                if not settings.layout_model_dir: raise ValueError("PP-DocLayout richiede --layout-model-dir locale")
                                if layout_detector is None: layout_detector=PPDocLayoutDetector(settings.layout_model_dir)
                                detected=layout_detector.detect(image,page_number=i+1)
                                structured.metadata["layout_regions"]=[r.model_dump(mode="json") for r in detected]
                                for r in detected:
                                    b=transform.pixels_to_pdf(r.bbox)
                                    if r.kind in ("text","title","table","formula","header","footer","caption","list"):
                                        targets.append((b,r.kind,None))
                                    elif r.kind=="image":
                                        picture=assets/f"p{i+1:04d}-layout-{r.id}.png"
                                        crop_region(image,b,transform,picture).close()
                                        structured.regions.append(Region(page_number=i+1,kind="image",bbox=b,
                                                                         image_path=str(picture),crop_path=str(picture),source="raster",
                                                                         confidence=r.confidence,metadata={"layout_detector":layout_detector.name}))
                                if not targets: targets=[(BBox(x0=0,y0=0,x1=structured.width,y1=structured.height),"text",None)]
                            else:
                                from .layout.fallback import GeometricLayoutDetector
                                detected=GeometricLayoutDetector().detect(image,page_number=i+1)
                                structured.metadata["geometric_layout"]=[r.model_dump(mode="json") for r in detected]
                                # Whole-page recognition retains context and real engine line boxes.
                                targets=[(BBox(x0=0,y0=0,x1=structured.width,y1=structured.height),"text",None)]
                            for r in structured.regions:
                                if r.kind=="image" and not r.metadata.get("layout_detector"): r.metadata["omit_editable"]=True
                        elif structured.classification=="mixed":
                            for r in [r for r in structured.regions if r.kind=="image"]:
                                contained=[n for n in native if n.bbox.coverage(r.bbox)>.6]
                                if sum(len(n.text) for n in contained)>20:
                                    r.metadata["omit_editable"]=True
                                    structured.warnings.append("Immagine con testo nativo sovrapposto omessa in editable per evitare duplicazione.")
                                elif r.bbox.area>2500:
                                    targets.append((r.bbox,"text",r))
                        recognized=[]
                        for ti,(box,kind,original_region) in enumerate(targets):
                            path=assets/f"p{i+1:04d}-ocr{ti:03d}.png"
                            crop=crop_region(image,box,transform,path)
                            # Mixed pages: mask recoverable text rather than submitting it twice.
                            if native:
                                from PIL import ImageDraw
                                draw=ImageDraw.Draw(crop)
                                for n in native:
                                    if n.bbox.intersection(box)>0:
                                        px=transform.pdf_to_pixels(n.bbox);origin=transform.pdf_to_pixels(box)
                                        draw.rectangle((px.x0-origin.x0,px.y0-origin.y0,px.x1-origin.x0,px.y1-origin.y0),fill="white")
                            notify(.05+.70*(i+.4)/page_count,f"Pagina {i+1}: OCR locale")
                            try:
                                result=recognize(crop,kind)
                            except OCRUnavailableError as exc:
                                if structured.classification=="mixed" and settings.engine=="auto":
                                    structured.warnings.append("OCR non disponibile per l'immagine: conservata come immagine; eventuale testo interno non modificabile. "+str(exc))
                                    crop.close()
                                    continue
                                raise
                            atomic_json(path.with_suffix(".ocr.json"),result.model_dump(mode="json"))
                            structured.warnings.extend(result.warnings)
                            regions=_recognition_regions(result,box,crop,i+1,path,native)
                            for region in regions:
                                if region.kind=="text" and kind in ("title","header","footer","caption","list"):
                                    region.kind=kind
                                region.metadata["requested_region_type"]=kind
                            if kind=="table" and regions and not any(r.kind=="table" for r in regions):
                                structured.warnings.append("Tabella rilevata ma OCR senza struttura celle: testo conservato; griglia non ricostruita.")
                            recognized.extend(regions)
                            if regions and original_region: original_region.metadata["omit_editable"]=True
                            crop.close()
                        structured.regions.extend(recognized)
                        if structured.classification=="scanned" and targets and not recognized and settings.mode=="editable":
                            raise RuntimeError(f"Pagina {i+1}: nessun testo OCR riconosciuto. Per conservarne l'aspetto usare --mode visual.")
                    order_regions(structured)
                    page_issues=enhancer.inspect(structured)
                    if settings.second_pass and settings.second_engine and page_issues:
                        if engine and initialized: engine.shutdown();initialized=False
                        secondary=create_engine(settings.second_engine,settings);secondary.initialize()
                        try:
                            for issue in page_issues:
                                r=next((r for r in structured.regions if r.id==issue["region"]),None)
                                if not r or r.source!="ocr": continue
                                path=assets/f"p{i+1:04d}-review-{r.id}.png"
                                crop=crop_region(image,r.bbox,transform,path)
                                before=time.perf_counter();alternative=secondary.recognize(crop,r.kind,settings.language);ocr_seconds+=time.perf_counter()-before
                                r.alternatives[alternative.engine]=alternative.text
                                if alternative.text.strip()!=r.text.strip(): structured.warnings.append(f"Conflitto OCR nella regione {r.id}; entrambe le versioni conservate.")
                                crop.close()
                        finally: secondary.shutdown();secondary=None
                    issues.extend(page_issues);model.pages.append(structured)
                    atomic_json(checkpoint,structured.model_dump(mode="json"))
                    image.close()
        finally:
            if engine is not None: engine.shutdown()
            if secondary is not None: secondary.shutdown()
            if layout_detector is not None: layout_detector.shutdown()
        _mark_repeated_parts(model)
        for page in model.pages: model.warnings.extend(f"Pagina {page.number}: {w}" for w in page.warnings)
        notify(.80,"Ricostruzione Word")
        reconstruction_start=time.perf_counter()
        staged=work/out.name
        reconstruction=DocumentReconstructionEngine().reconstruct(model,staged,settings.mode)
        reconstruction_seconds=time.perf_counter()-reconstruction_start
        structural=structural_validation(staged,model,settings.mode)
        notify(.90,"Validazione e rapporto qualità")
        visual=visual_validation(source,staged,work,settings.renderer) if settings.validate_visual else {"status":"not_requested"}
        report=dict(application="PDF2DOCX AI Fidelity",version=__version__,source=source.name,source_sha256=digest,
                    pages=page_count,mode=settings.mode,structural=structural,visual=visual,issues=issues,
                    warnings=model.warnings+reconstruction["warnings"],non_editable=reconstruction["non_editable"],
                    font_substitutions=reconstruction["font_substitutions"],engine=engine.name if engine and hasattr(engine,"name") else ("injected" if ocr_engine else "not_needed"),
                    limitations=["Flusso Word ricalcolato; nessuna garanzia pixel-perfect", "Font incorporati PDF non redistribuiti", "Footnote e riferimenti mantenuti come testo, senza collegamenti semantici", "LaTeX complesso conservato come ritaglio, senza conversione OMML verificata"])
        used_engines=sorted({r.engine for p in model.pages for r in p.regions if r.engine})
        if used_engines: report["engine"]=",".join(used_engines)
        report["engines_used"]=used_engines
        if settings.ground_truth:
            text="\n".join(r.text for p in model.pages for r in p.regions if r.kind!="image")
            try: report["text_accuracy"]=text_metrics(settings.ground_truth.read_text(encoding="utf-8"),text)
            except ValueError as exc: report["warnings"].append(str(exc))
        if settings.searchable_pdf:
            _searchable_pdf(source,model,work/final["searchable"].name)
            report["warnings"].append("PDF ricercabile supplementare: testo invisibile, geometria approssimata; non equivale al DOCX.")
        performance=dict(total_seconds=time.perf_counter()-start,seconds_per_page=(time.perf_counter()-start)/page_count,
                         ocr_seconds=ocr_seconds,reconstruction_seconds=reconstruction_seconds,peak_rss_mb=memory.peak/1024**2,
                         memory_measurement="sampled50ms process"+("+children" if memory.children_measured else " only; children unavailable")+"; external model-server memory excluded",
                         cache_pages_reused=cache_hits)
        report["performance"]=performance
        atomic_json(work/final["model"].name,model.model_dump(mode="json"))
        atomic_json(work/final["json"].name,report)
        write_report(report,work/final["report"].name)
        for kind,destination in final.items():
            # The lock prevents concurrent writers; collision was checked above.
            os.replace(work/destination.name,destination)
        notify(1.,"Conversione completata")
        return ConversionResult(output_path=str(out),report_path=str(final["report"]),json_path=str(final["json"]),
                                model_path=str(final["model"]),searchable_path=str(final["searchable"]) if "searchable" in final else None,
                                performance=performance,warnings=report["warnings"])


def compare(input_path: Path,report_path: Path,settings: Settings|None=None,engines=None,output_path: Path|None=None) -> ConversionResult:
    settings=settings or Settings()
    engines=engines or ["xiaomi","minicpm"]
    if len(engines)!=2 or engines[0]==engines[1]: raise ValueError("compare richiede due motori distinti")
    report_path=Path(report_path).resolve()
    if report_path.exists() and not settings.overwrite: raise FileExistsError(str(report_path))
    comparison_json=report_path.with_suffix(".json")
    if comparison_json.exists() and not settings.overwrite: raise FileExistsError(str(comparison_json))
    base=Path(output_path).resolve() if output_path else report_path.with_suffix(".docx")
    results={};errors={}
    for engine in engines:
        try:
            cfg=settings.model_copy(update={"engine":engine})
            result=convert(input_path,base.with_name(base.stem+"."+engine+".docx"),cfg)
            results[engine]=result
        except Exception as exc: errors[engine]=str(exc)
    if not results: raise RuntimeError("Nessun motore disponibile: "+json.dumps(errors,ensure_ascii=False))
    comparison=dict(results={k:v.model_dump(mode="json") for k,v in results.items()},errors=errors,conflicts=[])
    if len(results)==2:
        models={k:Document.model_validate_json(Path(v.model_path).read_text()) for k,v in results.items()}
        for pa,pb in zip(models[engines[0]].pages,models[engines[1]].pages):
            ta="\n".join(r.text for r in pa.regions if r.source=="ocr")
            tb="\n".join(r.text for r in pb.regions if r.source=="ocr")
            if ta!=tb: comparison["conflicts"].append(dict(page=pa.number,versions={engines[0]:ta,engines[1]:tb}))
    first=next(iter(results.values()))
    report=json.loads(Path(first.json_path).read_text())
    report["comparison"]=comparison
    report["warnings"].append("Confronto senza classifica automatica; differenze testuali non implicano maggiore accuratezza.")
    report_path.parent.mkdir(parents=True,exist_ok=True)
    write_report(report,report_path)
    atomic_json(comparison_json,report)
    return first.model_copy(update={"report_path":str(report_path),"json_path":str(comparison_json),"warnings":report["warnings"]})

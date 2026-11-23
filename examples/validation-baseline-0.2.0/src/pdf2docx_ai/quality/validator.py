from pathlib import Path
import shutil
import subprocess
import tempfile
from docx import Document
from docx.oxml.ns import qn
from .visual_diff import compare_pdfs
from collections import Counter
import hashlib


def find_renderer(explicit: str | None=None) -> str | None:
    if explicit: return shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
    return shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice" if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").is_file() else None)


def structural_validation(path: Path,model,mode: str) -> dict:
    doc=Document(path)
    root=doc.element
    def part_text(element):
        paragraphs=[]
        for paragraph in element.iter(qn("w:p")):
            content=[]
            for child in paragraph.iter():
                if child.tag in (qn("w:t"),qn("m:t")): content.append(child.text or "")
                elif child.tag==qn("w:tab"): content.append("\t")
                elif child.tag in (qn("w:br"),qn("w:cr")): content.append("\n")
            paragraphs.append("".join(content))
        return "\n".join(paragraphs)
    text=part_text(root)
    expected_tables=sum(r.kind=="table" for p in model.pages for r in p.regions)
    actual_tables=len(doc.tables)
    picture_count=len(list(root.iter(qn("pic:pic"))))
    expected_images=sum(r.kind=="image" and not r.metadata.get("omit_editable") for p in model.pages for r in p.regions) if mode=="editable" else len(model.pages)
    expected_text=" ".join((" ".join(c.text for c in r.cells) if r.kind=="table" else r.text)
                           for p in model.pages for r in p.regions
                           if r.kind not in ("image","formula") and not r.metadata.get("omit_editable")
                           and not (r.kind=="footer" and r.text.strip().isdigit()))
    # Count native text in all Word parts; plain body parsing alone misses
    # editable headers and footers. A count mismatch is diagnostic, not proof
    # of an OCR error, and exact textual preservation is assessed on rendering.
    all_text=[text]
    for part in doc.part.package.parts:
        if ("/header" in str(part.partname) or "/footer" in str(part.partname)) and hasattr(part,"element"):
            all_text.append(part_text(part.element))
    token=lambda s:Counter(s.split())
    missing=token(expected_text)-token(" ".join(all_text))
    artificial_tables=max(0,actual_tables-expected_tables) if mode=="editable" else None
    embedded_hashes={hashlib.sha256(part.blob).hexdigest() for part in doc.part.package.parts
                     if str(getattr(part,"content_type","")).startswith("image/")}
    expected_assets=[Path(r.image_path or r.crop_path) for p in model.pages for r in p.regions
                     if r.kind=="image" and not r.metadata.get("omit_editable") and (r.image_path or r.crop_path)]
    asset_hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in expected_assets if p.is_file()]
    return dict(docx_package_opened=True,paragraphs=len(doc.paragraphs),editable_characters=len(text),
                native_word_tables=actual_tables,expected_tables=expected_tables,
                table_count_difference=actual_tables-expected_tables if mode=="editable" else None,
                picture_count=picture_count,expected_images=expected_images,
                missing_images=max(0,expected_images-picture_count),mode=mode,
                additional_word_tables=artificial_tables,
                text_box_count=len(list(root.iter(qn("w:txbxContent")))),
                editable_text_expected=mode=="editable",source_token_count=sum(token(expected_text).values()),
                missing_source_token_count=sum(missing.values()) if mode=="editable" else None,
                missing_source_token_samples=dict(missing.most_common(30)) if mode=="editable" else {},
                source_token_check="whitespace tokens; excludes raster formulas and generated numeric PAGE fields",
                source_image_assets_checked=len(asset_hashes),
                source_image_assets_preserved_bytes=sum(digest in embedded_hashes for digest in asset_hashes),
                raster_only_editable_document=mode=="editable" and len(text.strip())==0 and picture_count>0,
                font_availability="unverified on target Word/LibreOffice installations")


def render_docx_to_pdf(docx: Path,work: Path,renderer: str|None=None,timeout: float=120) -> dict:
    """Render with an isolated profile, returning a reusable PDF for optimization."""
    executable=find_renderer(renderer)
    if not executable: return dict(status="unavailable",reason="LibreOffice non trovato; nessuna metrica visiva inventata")
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    rendered=work/"rendered";rendered.mkdir(exist_ok=True)
    pdf=rendered/(Path(docx).stem+".pdf")
    # Never accept a stale PDF from a previous failed renderer invocation.
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-profile-",dir=work) as profile:
        try:
            run=subprocess.run([executable,"-env:UserInstallation="+Path(profile).resolve().as_uri(),"--headless","--convert-to","pdf","--outdir",str(rendered.resolve()),str(Path(docx).resolve())],capture_output=True,text=True,timeout=timeout)
            if run.returncode or not pdf.is_file():
                return dict(status="failed",reason=(run.stderr or run.stdout)[-2000:])
            return dict(status="rendered",pdf_path=str(pdf.resolve()),renderer=str(executable),renderer_output=(run.stdout+run.stderr)[-2000:])
        except (OSError,subprocess.TimeoutExpired) as exc:
            return dict(status="failed",reason=str(exc))


def visual_validation(original: Path,docx: Path,work: Path,renderer: str|None=None) -> dict:
    rendered=render_docx_to_pdf(docx,work,renderer)
    if rendered["status"]!="rendered": return rendered
    metrics=compare_pdfs(original,Path(rendered["pdf_path"]),Path(work)/"visual")
    metrics["renderer"]=rendered["renderer"]
    metrics["rendered_pdf_path"]=rendered["pdf_path"]
    return metrics

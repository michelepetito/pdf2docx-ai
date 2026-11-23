from pathlib import Path
import shutil
import subprocess
import tempfile
from docx import Document
from docx.oxml.ns import qn
from .visual_diff import compare_pdfs


def find_renderer(explicit: str | None=None) -> str | None:
    if explicit: return shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
    return shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice" if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").is_file() else None)


def structural_validation(path: Path,model,mode: str) -> dict:
    doc=Document(path)
    root=doc.element
    text="\n".join(t.text or "" for t in root.iter(qn("w:t")))
    expected_tables=sum(r.kind=="table" for p in model.pages for r in p.regions)
    actual_tables=len(doc.tables)
    picture_count=len(list(root.iter(qn("pic:pic"))))
    expected_images=sum(r.kind=="image" and not r.metadata.get("omit_editable") for p in model.pages for r in p.regions) if mode=="editable" else len(model.pages)
    return dict(docx_package_opened=True,paragraphs=len(doc.paragraphs),editable_characters=len(text),
                native_word_tables=actual_tables,expected_tables=expected_tables,
                table_count_difference=actual_tables-expected_tables if mode=="editable" else None,
                picture_count=picture_count,expected_images=expected_images,
                missing_images=max(0,expected_images-picture_count),mode=mode,
                font_availability="unverified on target Word/LibreOffice installations")


def visual_validation(original: Path,docx: Path,work: Path,renderer: str|None=None) -> dict:
    executable=find_renderer(renderer)
    if not executable: return dict(status="unavailable",reason="LibreOffice non trovato; nessuna metrica visiva inventata")
    rendered=work/"rendered";rendered.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-profile-",dir=work) as profile:
        try:
            run=subprocess.run([executable,"-env:UserInstallation="+Path(profile).as_uri(),"--headless","--convert-to","pdf","--outdir",str(rendered),str(docx.resolve())],capture_output=True,text=True,timeout=120)
            pdf=rendered/(docx.stem+".pdf")
            if run.returncode or not pdf.is_file():
                return dict(status="failed",reason=(run.stderr or run.stdout)[-2000:])
            return compare_pdfs(original,pdf,work/"visual")
        except (OSError,subprocess.TimeoutExpired) as exc:
            return dict(status="failed",reason=str(exc))

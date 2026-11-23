from pathlib import Path
import pymupdf
from ..config import Settings
from .runtime import PDF_LOCK

# The pinned API prints an optional product recommendation on stdout during
# table detection. Keep stdout machine-readable for the CLI --json contract.
pymupdf.no_recommend_layout()


class PDFError(ValueError):
    pass


def open_pdf(path: Path, settings: Settings):
    path = Path(path)
    if not path.is_file():
        raise PDFError(f"PDF non trovato: {path}")
    if path.stat().st_size > settings.max_file_mb * 1024**2:
        raise PDFError("PDF oltre il limite configurato di dimensione")
    with path.open("rb") as stream:
        if b"%PDF-" not in stream.read(1024):
            raise PDFError("Il file non contiene un'intestazione PDF valida")
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise PDFError("PDF non leggibile o danneggiato") from exc
    if doc.needs_pass or not doc.is_pdf or not 0 < len(doc) <= settings.max_pages:
        doc.close()
        raise PDFError("PDF cifrato, vuoto o oltre il limite di pagine")
    return doc


def classify_page(page) -> str:
    # Invisible OCR layers count as native text and must not be OCRed again.
    text = page.get_text().strip()
    usable = sum(c.isalnum() for c in text)
    damaged = text.count("\ufffd") / max(len(text), 1) > .05
    images = page.get_image_info()
    large_images = [i for i in images if pymupdf.Rect(i["bbox"]).get_area() > 2500]
    if usable and not damaged:
        if large_images:
            return "mixed"
        return "native"
    if images or damaged:
        return "scanned"
    if page.get_drawings():
        return "scanned"  # Outlined text / vector-only pages need recognition.
    return "blank"


def inspect_pdf(path: Path, settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    with PDF_LOCK,open_pdf(path, settings) as doc:
        pages = []
        for i, page in enumerate(doc):
            data=page.get_text("dict",flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            blocks=[(*line["bbox"],"",0,0) for block in data["blocks"] if block["type"]==0 for line in block["lines"]]
            narrow = [b for b in blocks if b[2]-b[0] < page.cropbox.width*.55]
            left = any(b[0] < page.cropbox.width*.3 for b in narrow)
            right = any(b[0] > page.cropbox.width*.45 for b in narrow)
            pages.append(dict(number=i+1, width=page.rect.width, height=page.rect.height,
                              rotation=page.rotation, classification=classify_page(page),
                              columns=2 if left and right else 1,
                              cropbox=list(page.cropbox)))
        kinds = {p["classification"] for p in pages} - {"blank"}
        classification = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "blank"
        return dict(path=str(Path(path).resolve()), page_count=len(doc),
                    classification=classification, pages=pages,
                    variable_page_sizes=len({(p["width"],p["height"]) for p in pages}) > 1,
                    metadata=doc.metadata)

"""Deterministic, redistributable PDF fixtures containing no third-party documents.

Run: python tests/fixtures/generate.py [output-directory]
The plaintext files are exact, human-authored ground truth for OCR evaluation.
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


ITALIAN = "La città è più bella: perché c'è qualità."
ENGLISH = "The document contains editable text and the number 12345."
SCAN_IT = "Documento scannerizzato\nLa città è più bella.\nTotale 12345 euro."
SCAN_EN = "Scanned document\nThe invoice is ready.\nTotal 12345 euros."


def _save(document: pymupdf.Document, path: Path) -> None:
    document.set_metadata({"title": path.stem, "author": "PDF2DOCX AI synthetic QA"})
    document.save(path, garbage=4, deflate=True)
    document.close()


def _scan_image(text: str, width: float = 595, height: float = 842) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_text((48, 110), text, fontsize=22, fontname="helv", lineheight=1.7)
    payload = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")
    doc.close()
    return payload


def generate(destination: Path) -> dict[str, Path]:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}

    def finish(name: str, doc: pymupdf.Document):
        files[name] = destination / f"{name}.pdf"
        _save(doc, files[name])

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Documento nativo italiano", fontsize=20, fontname="hebo")
    page.insert_text((50, 135), ITALIAN, fontsize=12)
    page.insert_text((50, 160), ENGLISH, fontsize=12)
    page.insert_text((50, 200), "Un testo in grassetto", fontsize=12, fontname="hebo", color=(0.1, 0.2, 0.5))
    page.insert_text((50, 225), "Una frase in corsivo", fontsize=12, fontname="heit")
    finish("native", doc)
    files["native"].with_suffix(".txt").write_text(
        "Documento nativo italiano\n" + ITALIAN + "\n" + ENGLISH +
        "\nUn testo in grassetto\nUna frase in corsivo\n", encoding="utf-8")

    for language, text in (("it", SCAN_IT), ("en", SCAN_EN)):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_image(page.rect, stream=_scan_image(text))
        finish(f"scan_{language}", doc)
        files[f"scan_{language}"].with_suffix(".txt").write_text(text + "\n", encoding="utf-8")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Intestazione nativa 123", fontsize=16)
    page.insert_image(pymupdf.Rect(50, 130, 545, 630), stream=_scan_image(
        "Regione scannerizzata 456", width=495, height=500))
    finish("mixed", doc)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Documento a due colonne", fontsize=18, fontname="hebo")
    for i in range(8):
        page.insert_text((50, 130 + i * 24), f"Sinistra {i + 1}: testo della prima colonna.", fontsize=11)
        page.insert_text((315, 130 + i * 24), f"Destra {i + 1}: testo della seconda colonna.", fontsize=11)
    finish("columns", doc)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Tabella di esempio", fontsize=18, fontname="hebo")
    xs, ys = [50, 200, 350, 500], [150, 190, 230, 270]
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.7)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.7)
    data = [["Prodotto", "Quantita", "Prezzo"], ["Matite", "12", "6.00"], ["Quaderni", "3", "9.00"]]
    for row, values in enumerate(data):
        for col, value in enumerate(values):
            page.insert_text((xs[col] + 8, ys[row] + 25), value, fontsize=11)
    finish("table", doc)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Tabella con celle unite", fontsize=18)
    for x in (50, 350, 500):
        page.draw_line((x, 150), (x, 270), width=.7)
    page.draw_line((200, 190), (200, 270), width=.7)
    for y in (150, 190, 230, 270):
        page.draw_line((50, y), (500, y), width=.7)
    page.insert_text((58, 175), "Dati riuniti", fontsize=11)
    page.insert_text((358, 175), "Valore", fontsize=11)
    for row, values in enumerate((("A", "B", "10"), ("C", "D", "20"))):
        for col, value in enumerate(values):
            page.insert_text((xs[col] + 8, 215 + row * 40), value, fontsize=11)
    finish("merged_table", doc)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Elenchi di esempio", fontsize=18)
    for i, text in enumerate(("1. Primo elemento", "2. Secondo elemento", "3. Terzo elemento")):
        page.insert_text((60, 145 + i * 28), text, fontsize=12)
    for i, text in enumerate(("Primo punto", "Secondo punto")):
        page.insert_text((60, 260 + i * 28), "• " + text, fontsize=12)
    finish("lists", doc)

    # A real image asset independent of the editable page text.
    image = Image.new("RGB", (420, 220), "#e9f1fa")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 25, 180, 190), fill="#2266aa")
    draw.ellipse((220, 35, 390, 200), fill="#dd7733")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Documento con immagine", fontsize=18)
    page.insert_image(pymupdf.Rect(50, 150, 470, 370), stream=buffer.getvalue())
    page.insert_text((50, 420), "Didascalia modificabile", fontsize=11)
    finish("image", doc)

    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((50, 30), "Rapporto aziendale", fontsize=10)
        page.insert_text((50, 120), f"Contenuto pagina {i + 1}", fontsize=15)
        page.insert_text((50, 160), ITALIAN, fontsize=12)
        page.insert_text((260, 820), f"Pagina {i + 1}", fontsize=10)
    finish("headers", doc)

    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((50, 90), "Pagina orizzontale", fontsize=22)
    page.insert_text((50, 145), ENGLISH, fontsize=13)
    finish("landscape", doc)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 85), "Formula matematica", fontsize=18)
    page.insert_text((50, 145), "E = mc", fontsize=18, fontname="tiro")
    page.insert_text((103, 137), "2", fontsize=11, fontname="tiro")
    page.insert_text((50, 200), "L'energia dipende dalla massa.", fontsize=12)
    finish("formula", doc)

    doc = pymupdf.open()
    for i, (width, height) in enumerate(((595, 842), (842, 595), (420, 595))):
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 90), f"Dimensioni pagina {i + 1}", fontsize=18)
    finish("page_sizes", doc)

    doc = pymupdf.open()
    page = doc.new_page(width=640, height=900)
    page.insert_text((90, 140), "Testo ruotato e ritagliato", fontsize=16)
    page.set_cropbox(pymupdf.Rect(40, 50, 600, 850))
    page.set_rotation(90)
    finish("rotated_crop", doc)

    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args()
    for name, path in generate(args.destination).items():
        print(f"{name}: {path}")

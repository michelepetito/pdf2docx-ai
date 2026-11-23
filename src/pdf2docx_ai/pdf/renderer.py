from pathlib import Path
import math
import pymupdf
from PIL import Image
from ..document.models import BBox
from ..document.geometry import PageTransform


def render_page(page, dpi: int = 180, max_pixels: int = 30_000_000) -> tuple[Image.Image, PageTransform]:
    if page.rect.width <= 0 or page.rect.height <= 0:
        raise ValueError("Dimensioni pagina non valide")
    scale = min(dpi / 72, math.sqrt(max_pixels / (page.rect.width * page.rect.height)))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return image, PageTransform(page.rect.width, page.rect.height, pix.width, pix.height)


def crop_region(image: Image.Image, box: BBox, transform: PageTransform, path: Path) -> Image.Image:
    p = transform.pdf_to_pixels(box)
    coords = (max(0, math.floor(p.x0)), max(0, math.floor(p.y0)),
              min(image.width, math.ceil(p.x1)), min(image.height, math.ceil(p.y1)))
    if coords[2] <= coords[0] or coords[3] <= coords[1]:
        raise ValueError("Regione fuori pagina")
    crop = image.crop(coords)
    path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(path)
    return crop

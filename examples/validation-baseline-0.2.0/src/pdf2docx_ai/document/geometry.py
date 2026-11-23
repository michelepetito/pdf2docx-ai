"""Explicit coordinate transforms; PDF points -> pixels -> Word twips/EMU."""
from dataclasses import dataclass
from .models import BBox


@dataclass(frozen=True)
class PageTransform:
    width_pt: float
    height_pt: float
    width_px: int
    height_px: int

    def pdf_to_pixels(self, box: BBox) -> BBox:
        sx, sy = self.width_px / self.width_pt, self.height_px / self.height_pt
        return BBox(x0=box.x0*sx, y0=box.y0*sy, x1=box.x1*sx, y1=box.y1*sy)

    def pixels_to_pdf(self, box: BBox) -> BBox:
        sx, sy = self.width_pt / self.width_px, self.height_pt / self.height_px
        return BBox(x0=box.x0*sx, y0=box.y0*sy, x1=box.x1*sx, y1=box.y1*sy)

    @staticmethod
    def points_to_twips(points: float) -> int:
        return round(points * 20)

    @staticmethod
    def points_to_emu(points: float) -> int:
        return round(points * 12700)


def displayed_box(rect, page) -> BBox:
    """PyMuPDF extraction is crop-relative and unrotated; display uses rotation."""
    import pymupdf
    return BBox(**dict(zip(("x0", "y0", "x1", "y1"), pymupdf.Rect(rect) * page.rotation_matrix)))


def displayed_point(point,page) -> tuple[float,float]:
    import pymupdf
    p=pymupdf.Point(point)*page.rotation_matrix
    return float(p.x),float(p.y)

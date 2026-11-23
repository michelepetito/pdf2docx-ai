"""Engine-neutral model. All boxes use displayed, cropped PDF points."""
from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def uid() -> str:
    return uuid4().hex


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def ordered(self):
        import math
        if not all(math.isfinite(v) for v in (self.x0, self.y0, self.x1, self.y1)):
            raise ValueError("Non-finite bounding box")
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Inverted bounding box")
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection(self, other: BBox) -> float:
        return max(0, min(self.x1, other.x1) - max(self.x0, other.x0)) * max(
            0, min(self.y1, other.y1) - max(self.y0, other.y0))

    def coverage(self, other: BBox) -> float:
        return self.intersection(other) / max(self.area, 1e-9)

    def as_tuple(self):
        return self.x0, self.y0, self.x1, self.y1


class TextSpan(BaseModel):
    id: str = Field(default_factory=uid)
    text: str
    bbox: BBox
    font: str = "Arial"
    size: float = 11
    bold: bool = False
    italic: bool = False
    color: str = "000000"
    superscript: bool = False
    baseline: tuple[float,float] | None = None
    ascender: float | None = None
    descender: float | None = None
    advance_width: float | None = None
    tracking_pt: float = 0


class TextLine(BaseModel):
    id: str = Field(default_factory=uid)
    text: str
    bbox: BBox
    baseline: tuple[float,float]
    direction: tuple[float,float] = (1.,0.)
    spans: list[TextSpan] = Field(default_factory=list)
    provenance: Literal["native","ocr","raster_estimate"] = "native"


class TableCell(BaseModel):
    id: str = Field(default_factory=uid)
    row: int
    col: int
    text: str = ""
    bbox: BBox | None = None
    rowspan: int = 1
    colspan: int = 1
    spans: list[TextSpan] = Field(default_factory=list)
    alignment: str = "left"
    vertical_alignment: str = "top"
    background: str | None = None


RegionType = Literal["text", "title", "table", "image", "graphic", "formula", "header", "footer", "caption", "list"]


class Region(BaseModel):
    id: str = Field(default_factory=uid)
    page_number: int
    kind: RegionType = "text"
    bbox: BBox
    text: str = ""
    spans: list[TextSpan] = Field(default_factory=list)
    lines: list[TextLine] = Field(default_factory=list)
    alignment: Literal["left", "right", "center", "justify"] = "left"
    reading_order: int = 0
    column: int = 0
    source: Literal["native", "ocr", "raster"] = "native"
    engine: str | None = None
    confidence: float | None = None
    crop_path: str | None = None
    image_path: str | None = None
    cells: list[TableCell] = Field(default_factory=list)
    rows: int = 0
    cols: int = 0
    alternatives: dict[str, str] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


# Named semantic types retain the same serialization and coordinate contract.
class TextBlock(Region):
    pass


class Paragraph(TextBlock):
    pass


class Table(Region):
    kind: RegionType = "table"


class Image(Region):
    kind: RegionType = "image"


class Formula(Region):
    kind: RegionType = "formula"


class Header(Region):
    kind: RegionType = "header"


class Footer(Region):
    kind: RegionType = "footer"


class Page(BaseModel):
    number: int
    width: float
    height: float
    rotation: int = 0
    cropbox: BBox
    classification: Literal["native", "scanned", "mixed", "blank"]
    regions: list[Region] = Field(default_factory=list)
    columns: int = 1
    preview_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class Document(BaseModel):
    schema_version: str = "1.0"
    id: str = Field(default_factory=uid)
    source_path: str
    source_sha256: str
    pages: list[Page] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class OCRWord(BaseModel):
    text: str
    bbox: BBox
    confidence: float | None = None
    line: str = "0"


class OCRResult(BaseModel):
    text: str
    engine: str
    confidence: float | None = None
    words: list[OCRWord] = Field(default_factory=list)
    format: Literal["text", "html", "latex", "markdown"] = "text"
    raw: str | None = None
    warnings: list[str] = Field(default_factory=list)

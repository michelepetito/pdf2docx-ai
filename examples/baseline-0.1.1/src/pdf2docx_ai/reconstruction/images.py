from docx.shared import Pt
from .ooxml import anchor_picture


def add_image(doc, region, width: float, anchored: bool=False):
    path=region.image_path or region.crop_path
    if not path:
        return
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0)
    actual=min(width,region.bbox.width)
    picture=p.add_run().add_picture(path,width=Pt(actual),height=Pt(actual*region.bbox.height/max(region.bbox.width,1)))
    if anchored:
        anchor_picture(picture._inline,region.bbox.x0,region.bbox.y0)
    return p

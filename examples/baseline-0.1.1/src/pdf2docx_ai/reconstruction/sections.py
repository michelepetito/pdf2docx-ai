from docx.shared import Pt
from docx.enum.section import WD_ORIENT
from .ooxml import set_columns, page_number
from .paragraphs import fill_paragraph
import re


def margins(page):
    body=[r for r in page.regions if r.kind not in ("header","footer") and not r.metadata.get("omit_editable")]
    if not body: return (36.,36.,36.,36.)
    left=max(0,min(72.,min(r.bbox.x0 for r in body)))
    right=max(0,min(72.,page.width-max(r.bbox.x1 for r in body)))
    top=max(0,min(72.,min(r.bbox.y0 for r in body)))
    bottom=max(8.,min(72.,page.height-max(r.bbox.y1 for r in body)))
    return left,right,top,bottom


def configure_section(section,page,columns=1,visual=False):
    section.page_width=Pt(page.width);section.page_height=Pt(page.height)
    section.orientation=WD_ORIENT.LANDSCAPE if page.width>page.height else WD_ORIENT.PORTRAIT
    left,right,top,bottom=(0,0,0,0) if visual else margins(page)
    section.left_margin=Pt(left);section.right_margin=Pt(right)
    section.top_margin=Pt(top);section.bottom_margin=Pt(bottom)
    section.header_distance=Pt(8);section.footer_distance=Pt(8)
    set_columns(section,columns)
    section.header.is_linked_to_previous=False;section.footer.is_linked_to_previous=False
    for kind,part in (("header",section.header),("footer",section.footer)):
        # Every page has its own section to preserve page-specific source content.
        for i,r in enumerate(r for r in page.regions if r.kind==kind):
            p=part.paragraphs[0] if i==0 else part.add_paragraph()
            if kind=="footer" and re.fullmatch(r"\s*\d+\s*",r.text):
                page_number(p)
            else:
                fill_paragraph(p,r,left,page.width-left-right)
    return left,right,top,bottom

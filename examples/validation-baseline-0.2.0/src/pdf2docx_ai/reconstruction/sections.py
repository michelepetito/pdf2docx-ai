from docx.shared import Pt
from docx.enum.section import WD_ORIENT
from .ooxml import set_columns,page_number
from .paragraphs import fill_paragraph
from .layout import page_margins,paragraph_geometry
import re


def margins(page):return page_margins(page)


def configure_section(section,page,columns=1,visual=False,*,geometry=None,continuous=False,resolver=None,adjustments=None):
    section.page_width=Pt(page.width);section.page_height=Pt(page.height)
    section.orientation=WD_ORIENT.LANDSCAPE if page.width>page.height else WD_ORIENT.PORTRAIT
    left,right,top,bottom=(0,0,0,0) if visual else margins(page)
    adjustments=adjustments or {}
    body=[r for r in page.regions if r.kind not in ('header','footer','image','graphic') and not r.metadata.get('omit_editable')]
    if body and not visual:
        first_body=min(body,key=lambda r:r.bbox.y0)
        top=max(0,top+adjustments.get(first_body.id,{}).get('y',0))
    section.left_margin=Pt(left);section.right_margin=Pt(right);section.top_margin=Pt(top);section.bottom_margin=Pt(bottom)
    set_columns(section,columns,geometry=geometry)
    if continuous:
        section.header.is_linked_to_previous=True;section.footer.is_linked_to_previous=True
        return left,right,top,bottom
    section.header.is_linked_to_previous=False;section.footer.is_linked_to_previous=False
    for kind,part in (('header',section.header),('footer',section.footer)):
        regions=[r for r in page.regions if r.kind==kind]
        if not regions:continue
        first=min(regions,key=lambda r:r.bbox.y0);last=max(regions,key=lambda r:r.bbox.y1)
        fg,lg=paragraph_geometry(first),paragraph_geometry(last)
        if kind=='header':section.header_distance=Pt(max(0,fg['baseline']-fg['offset']+adjustments.get(first.id,{}).get('y',0)))
        else:section.footer_distance=Pt(max(0,page.height-(lg['baseline']+lg['pitch']-lg['offset']+adjustments.get(last.id,{}).get('y',0))))
        cursor=fg['baseline']-fg['offset']+adjustments.get(first.id,{}).get('y',0)
        for i,r in enumerate(regions):
            p=part.paragraphs[0] if i==0 else part.add_paragraph();g=paragraph_geometry(r)
            gap=max(0,g['baseline']+adjustments.get(r.id,{}).get('y',0)-g['offset']-cursor)
            fill_paragraph(p,r,left,page.width-left-right,gap,resolver=resolver,geometry=g,adjustment=adjustments.get(r.id))
            cursor+=gap+g['height']
    return left,right,top,bottom

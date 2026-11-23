from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from .fonts import word_font
from .ooxml import simple_math


def clean_xml_text(text: str) -> str:
    return "".join(c for c in text if c in "\t\n\r" or (ord(c)>=32 and not 0xD800<=ord(c)<=0xDFFF))


def fill_paragraph(paragraph, region, left_origin: float, width: float, gap: float = 0, substitutions: set | None = None):
    fmt=paragraph.paragraph_format
    fmt.space_before=Pt(max(0,min(gap,500)))
    fmt.space_after=Pt(0)
    fmt.left_indent=Pt(0 if region.metadata.get("rotation_normalized") else max(0,region.bbox.x0-left_origin))
    # Source lines are already explicit. An exact glyph bbox would create extra
    # wrapping when Word substitutes font metrics.
    fmt.right_indent=Pt(0)
    fmt.widow_control=False
    fmt.keep_with_next=region.kind=="title"
    fmt.alignment={"left":WD_ALIGN_PARAGRAPH.LEFT,"right":WD_ALIGN_PARAGRAPH.RIGHT,
                   "center":WD_ALIGN_PARAGRAPH.CENTER,"justify":WD_ALIGN_PARAGRAPH.JUSTIFY}[region.alignment]
    if region.kind=="list":
        import re
        numbered=bool(re.match(r"^\s*\d+[.)]\s",region.text))
        paragraph.style="List Number" if numbered else "List Bullet"
        # Source markers are kept as literal editable characters. Disable the
        # style's automatic marker so it is not displayed twice.
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        num=OxmlElement("w:numPr");ident=OxmlElement("w:numId");ident.set(qn("w:val"),"0");num.append(ident)
        paragraph._p.get_or_add_pPr().append(num)
    if region.kind=="title":
        paragraph.style="Heading 1" if max((s.size for s in region.spans),default=14)>17 else "Heading 2"
    size=max((s.size for s in region.spans),default=region.metadata.get("font_size",11))
    lines=max(1,region.metadata.get("line_count",region.text.count("\n")+1))
    fmt.line_spacing=Pt(max(size*1.15,min(region.bbox.height/lines,size*1.6)))
    if region.kind=="formula" and region.metadata.get("formula_representation")=="simple_unicode_math":
        simple_math(paragraph,clean_xml_text(region.text))
    elif region.spans:
        for span in region.spans:
            run=paragraph.add_run(clean_xml_text(span.text))
            font,notice=word_font(span.font)
            run.font.name=font; run.font.size=Pt(max(1,min(span.size,400)))
            run.bold=span.bold; run.italic=span.italic; run.font.superscript=span.superscript
            try: run.font.color.rgb=RGBColor.from_string(span.color)
            except ValueError: pass
            if notice and substitutions is not None: substitutions.add(notice)
    else:
        run=paragraph.add_run(clean_xml_text(region.text))
        run.font.name="Arial"; run.font.size=Pt(size)
    return paragraph

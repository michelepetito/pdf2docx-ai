from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def set_columns(section, count: int, gap_pt: float = 18):
    cols=section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols=OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"),str(count))
    cols.set(qn("w:space"),str(round(gap_pt*20)))
    cols.set(qn("w:equalWidth"),"1")


def page_number(paragraph):
    run=paragraph.add_run()
    field=OxmlElement("w:fldSimple")
    field.set(qn("w:instr"),"PAGE")
    run._r.addnext(field)


def table_borders(table):
    props=table._tbl.tblPr
    borders=OxmlElement("w:tblBorders")
    for edge in ("top","left","bottom","right","insideH","insideV"):
        e=OxmlElement("w:"+edge)
        for key,val in (("val","single"),("sz","4"),("color","808080")):
            e.set(qn("w:"+key),val)
        borders.append(e)
    props.append(borders)


def anchor_picture(inline, x_pt: float, y_pt: float):
    """Promote a DrawingML picture to a page-relative, non-wrapping anchor."""
    anchor=OxmlElement("wp:anchor")
    for key,value in dict(distT="0",distB="0",distL="0",distR="0",simplePos="0",
                          relativeHeight="0",behindDoc="0",locked="0",layoutInCell="1",allowOverlap="1").items():
        anchor.set(key,value)
    simple=OxmlElement("wp:simplePos"); simple.set("x","0"); simple.set("y","0"); anchor.append(simple)
    for tag,offset in (("H",x_pt),("V",y_pt)):
        pos=OxmlElement("wp:position"+tag); pos.set("relativeFrom","page")
        value=OxmlElement("wp:posOffset"); value.text=str(round(offset*12700)); pos.append(value); anchor.append(pos)
    for child in list(inline):
        if child.tag in (qn("wp:extent"),qn("wp:effectExtent")):
            anchor.append(child)
    anchor.append(OxmlElement("wp:wrapNone"))
    for child in list(inline):
        anchor.append(child)
    inline.getparent().replace(inline,anchor)


def simple_math(paragraph, text: str):
    """Lossless Unicode math run. Does not pretend to infer fractions/LaTeX semantics."""
    math=OxmlElement("m:oMath")
    r=OxmlElement("m:r"); t=OxmlElement("m:t"); t.text=text; r.append(t); math.append(r)
    paragraph._p.append(math)

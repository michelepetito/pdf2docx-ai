from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from .ooxml import table_borders
from .paragraphs import clean_xml_text
from .fonts import word_font
from docx.shared import RGBColor


def add_table(doc, region, available_width: float):
    rows,cols=region.rows,region.cols
    if not 0<rows<=1000 or not 0<cols<=100 or rows*cols>20000:
        raise ValueError("Tabella oltre il limite di celle o senza struttura valida")
    table=doc.add_table(rows=rows,cols=cols)
    table.autofit=False; table.alignment=WD_TABLE_ALIGNMENT.LEFT
    width=min(available_width,region.bbox.width)
    xs=region.metadata.get("grid_x",[])
    col_widths=[(xs[i+1]-xs[i]) for i in range(cols)] if len(xs)==cols+1 else [width/cols]*cols
    scale=width/max(sum(col_widths),1)
    for i,c in enumerate(table.columns): c.width=Pt(max(1,col_widths[i]*scale))
    table_borders(table)
    # Small cell padding avoids widening fixed PDF table geometry.
    margins=OxmlElement("w:tblCellMar")
    for side in ("top","bottom","left","right"):
        element=OxmlElement("w:"+side);element.set(qn("w:w"),"40");element.set(qn("w:type"),"dxa");margins.append(element)
    table._tbl.tblPr.append(margins)
    for cell in region.cells:
        if cell.row>=rows or cell.col>=cols: continue
        target=table.cell(cell.row,cell.col)
        if cell.rowspan>1 or cell.colspan>1:
            target=target.merge(table.cell(min(rows-1,cell.row+cell.rowspan-1),min(cols-1,cell.col+cell.colspan-1)))
        target.text=clean_xml_text(cell.text)
        target.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER if cell.vertical_alignment=="center" else WD_CELL_VERTICAL_ALIGNMENT.TOP
        if cell.spans:
            paragraph=target.paragraphs[0]
            paragraph.clear()
            last=None
            for span in cell.spans:
                if last and span.bbox.y0>last.bbox.y0+span.size*.5: paragraph.add_run("\n")
                run=paragraph.add_run(clean_xml_text(span.text))
                run.font.name=word_font(span.font)[0];run.font.size=Pt(span.size);run.bold=span.bold;run.italic=span.italic
                try: run.font.color.rgb=RGBColor.from_string(span.color)
                except ValueError: pass
                last=span
        for p in target.paragraphs:
            p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0)
            for run in p.runs:
                if not run.font.name: run.font.name="Arial"
                if not run.font.size: run.font.size=Pt(region.metadata.get("font_size",10))
    ys=region.metadata.get("grid_y",[])
    if len(ys)==rows+1:
        for i,row in enumerate(table.rows):
            row.height=Pt(max(1,ys[i+1]-ys[i]));row.height_rule=WD_ROW_HEIGHT_RULE.AT_LEAST
    for row in table.rows:
        props=row._tr.get_or_add_trPr();props.append(OxmlElement("w:cantSplit"))
    return table

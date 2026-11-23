from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from .ooxml import table_borders
from .paragraphs import clean_xml_text
from .fonts import word_font
from docx.shared import RGBColor


def add_table(doc, region, available_width: float, *,left_origin=None,adjustment=None,resolver=None,substitutions=None):
    rows,cols=region.rows,region.cols
    if not 0<rows<=1000 or not 0<cols<=100 or rows*cols>20000:
        raise ValueError("Tabella oltre il limite di celle o senza struttura valida")
    table=doc.add_table(rows=rows,cols=cols)
    table.autofit=False; table.alignment=WD_TABLE_ALIGNMENT.LEFT
    adjustment=adjustment or {}
    if left_origin is not None:
        indent=OxmlElement('w:tblInd');indent.set(qn('w:type'),'dxa')
        first=next((c for c in region.cells if c.col==0 and c.bbox and c.spans),None)
        padding=max(0,min(s.bbox.x0 for s in first.spans)-first.bbox.x0) if first else 2
        indent.set(qn('w:w'),str(round((region.bbox.x0-left_origin+padding+adjustment.get('left',0))*20)))
        table._tbl.tblPr.append(indent)
    width=min(available_width,region.bbox.width)
    xs=region.metadata.get("grid_x",[])
    col_widths=[(xs[i+1]-xs[i]) for i in range(cols)] if len(xs)==cols+1 else [width/cols]*cols
    scale=width/max(sum(col_widths),1)
    for i,c in enumerate(table.columns): c.width=Pt(max(1,col_widths[i]*scale))
    for row in table.rows:
        for i,cell in enumerate(row.cells):cell.width=Pt(max(1,col_widths[i]*scale))
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
        if cell.background:
            shading=OxmlElement('w:shd');shading.set(qn('w:fill'),cell.background);target._tc.get_or_add_tcPr().append(shading)
        target.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER if cell.vertical_alignment=="center" else WD_CELL_VERTICAL_ALIGNMENT.TOP
        if cell.spans:
            paragraph=target.paragraphs[0]
            paragraph.clear()
            last=None
            for span in cell.spans:
                if last and span.bbox.y0>last.bbox.y0+span.size*.5: paragraph.add_run("\n")
                run=paragraph.add_run(clean_xml_text(span.text))
                family,tracking,notice=resolver.resolve(span) if resolver else (word_font(span.font)[0],0,None)
                run.font.name=family;run.font.size=Pt(span.size);run.bold=span.bold;run.italic=span.italic
                if notice and substitutions is not None:substitutions.add(notice)
                if abs(tracking)>.005:
                    spacing=OxmlElement('w:spacing');spacing.set(qn('w:val'),str(round(tracking*20)));run._r.get_or_add_rPr().append(spacing)
                try: run.font.color.rgb=RGBColor.from_string(span.color)
                except ValueError: pass
                last=span
            size=max(s.size for s in cell.spans)
            baselines=sorted({round(s.baseline[1],2) for s in cell.spans if s.baseline})
            from statistics import median
            pitch=median([b-a for a,b in zip(baselines,baselines[1:]) if b-a>1]) if len(baselines)>1 else size*1.15
            paragraph.paragraph_format.line_spacing=Pt(pitch)
            if cell.bbox and baselines:
                target.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
                mar=OxmlElement('w:tcMar')
                offsets={'top':max(0,baselines[0]-cell.bbox.y0-.8*pitch),'bottom':0,
                         'left':max(0,min(s.bbox.x0 for s in cell.spans)-cell.bbox.x0),'right':0}
                for side,value in offsets.items():
                    node=OxmlElement('w:'+side);node.set(qn('w:w'),str(round(value*20)));node.set(qn('w:type'),'dxa');mar.append(node)
                target._tc.get_or_add_tcPr().append(mar)
        for p in target.paragraphs:
            p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0)
            for run in p.runs:
                if not run.font.name: run.font.name="Arial"
                if not run.font.size: run.font.size=Pt(region.metadata.get("font_size",10))
    ys=region.metadata.get("grid_y",[])
    if len(ys)==rows+1:
        for i,row in enumerate(table.rows):
            height=max(1,ys[i+1]-ys[i]);required=0
            for cell in (c for c in region.cells if c.row==i and c.rowspan==1 and c.spans and c.bbox):
                bases=sorted({s.baseline[1] for s in cell.spans if s.baseline})
                if bases:required=max(required,bases[-1]-cell.bbox.y0+max(s.size for s in cell.spans)*.3)
            row.height=Pt(height)
            row.height_rule=WD_ROW_HEIGHT_RULE.EXACTLY if required<=height-.25 else WD_ROW_HEIGHT_RULE.AT_LEAST
    for row in table.rows:
        props=row._tr.get_or_add_trPr();props.append(OxmlElement("w:cantSplit"))
    return table

from pathlib import Path
import re
import statistics
import pymupdf
from ..document.models import BBox, Page, Region, TextSpan, TableCell
from ..document.geometry import displayed_box
from .inspector import classify_page
from .renderer import crop_region


def extract_page(page, number: int, image, transform, assets: Path) -> Page:
    result = Page(number=number, width=page.rect.width, height=page.rect.height,
                  rotation=page.rotation, cropbox=BBox(**dict(zip(("x0","y0","x1","y1"),page.cropbox))),
                  classification=classify_page(page))
    result.metadata["coordinate_system"] = "displayed crop-relative PDF points, origin top-left"
    result.metadata["fonts"]=[dict(xref=f[0],extension=f[1],type=f[2],basefont=f[3],resource=f[4],encoding=f[5]) for f in page.get_fonts(full=True)]
    raw = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
    raw_spans=[s for b in raw["blocks"] if b["type"]==0 for l in b["lines"] for s in l["spans"]]
    table_boxes = []
    try:
        # PyMuPDF 1.26.7 may change the cropbox inside find_tables on rotated
        # pages. Preserve source geometry; this combination is explicitly deferred.
        if page.rotation or page.cropbox != page.mediabox:
            tables=[]
            result.warnings.append("Tabelle automatiche non analizzate su pagina ruotata/ritagliata; testo conservato.")
        else:
            tables = page.find_tables().tables
    except Exception as exc:
        tables = []
        result.warnings.append(f"Rilevamento tabelle non disponibile: {type(exc).__name__}")
    for tab in tables:
        box = displayed_box(tab.bbox, page)
        table_boxes.append(box)
        data = tab.extract()
        cells = []
        # Unique cell rectangles encode horizontal and vertical merges.
        xs = sorted({round(c[0],2) for c in tab.cells if c} | {round(c[2],2) for c in tab.cells if c})
        ys = sorted({round(c[1],2) for c in tab.cells if c} | {round(c[3],2) for c in tab.cells if c})
        for row_index, row in enumerate(tab.rows):
            for col_index, rect in enumerate(row.cells):
                if not rect:
                    continue
                c = displayed_box(rect, page)
                x0,y0,x1,y1 = [round(v,2) for v in rect]
                col, rr = xs.index(x0), ys.index(y0)
                text = data[row_index][col_index] if row_index < len(data) and col_index < len(data[row_index]) else ""
                items=[s for s in raw_spans if displayed_box(s["bbox"],page).coverage(c)>.6]
                spans=[TextSpan(text=s["text"],bbox=displayed_box(s["bbox"],page),font=s["font"],size=s["size"],
                                bold=bool(s["flags"]&16),italic=bool(s["flags"]&2),color=f'{s["color"]:06X}') for s in items]
                center_y=(min(s.bbox.y0 for s in spans)+max(s.bbox.y1 for s in spans))/2 if spans else c.y0
                cells.append(TableCell(row=rr,col=col,text=text or "",bbox=c,spans=spans,
                                       vertical_alignment="center" if abs(center_y-(c.y0+c.y1)/2)<4 else "top",
                                       rowspan=max(1,ys.index(y1)-rr),colspan=max(1,xs.index(x1)-col)))
        result.regions.append(Region(page_number=number,kind="table",bbox=box,cells=cells,
                                     rows=max(len(ys)-1,tab.row_count),cols=max(len(xs)-1,tab.col_count),
                                     text="\n".join("\t".join(c or "" for c in row) for row in data),
                                     metadata={"borders":"detected grid","grid_x":xs,"grid_y":ys,
                                               "font_size":statistics.median([s.size for c in cells for s in c.spans]) if any(c.spans for c in cells) else 10}))
    sizes=[]
    blocks=[]
    for block in raw["blocks"]:
        if block["type"]==0:
            mid=page.cropbox.width/2
            ll=[l for l in block["lines"] if l["bbox"][2]<=mid+8]
            rr=[l for l in block["lines"] if l["bbox"][0]>=mid-8]
            overlapping=any(min(a["bbox"][3],b["bbox"][3])-max(a["bbox"][1],b["bbox"][1])>4 for a in ll for b in rr)
            if ll and rr and overlapping:
                # MuPDF sometimes groups two columns on the same baseline into one block.
                blocks.extend([{**block,"lines":group} for group in (ll,rr)])
                rest=[l for l in block["lines"] if l not in ll and l not in rr]
                if rest: blocks.append({**block,"lines":rest})
                continue
        blocks.append(block)
    for block in blocks:
        if block["type"] != 0:
            continue
        spans=[]
        lines=[]
        for line in block["lines"]:
            line_spans=[]
            for item in line["spans"]:
                box=displayed_box(item["bbox"],page)
                if any(box.coverage(t) > .6 for t in table_boxes):
                    continue
                text=item["text"]
                if not text.strip():
                    if not line_spans:
                        continue
                flags=item["flags"]
                span=TextSpan(text=text,bbox=box,font=re.sub(r"^[A-Z]{6}\+","",item["font"]),
                              size=item["size"],bold=bool(flags & 16),italic=bool(flags & 2),
                              superscript=bool(flags & 1),color=f'{item["color"]:06X}')
                line_spans.append(span)
                sizes.append(span.size)
            if line_spans:
                if spans:
                    # Keep explicit source line breaks, without inventing prose.
                    line_spans[0].text="\n"+line_spans[0].text
                spans.extend(line_spans)
                lines.append("".join(s.text for s in line_spans).lstrip("\n"))
        if not spans:
            continue
        box=BBox(x0=min(s.bbox.x0 for s in spans),y0=min(s.bbox.y0 for s in spans),
                 x1=max(s.bbox.x1 for s in spans),y1=max(s.bbox.y1 for s in spans))
        text="\n".join(lines)
        kind="list" if re.match(r"^\s*(?:[•●▪]|\d+[.)])\s",text) else "text"
        if box.y0 > result.height*.90:
            kind="footer"
        region=Region(page_number=number,bbox=box,text=text,spans=spans,kind=kind,
                      metadata={"line_count":len(lines),"rotation_normalized":page.rotation})
        result.regions.append(region)
    median=statistics.median(sizes) if sizes else 11
    for r in result.regions:
        if r.kind=="text" and r.spans and max(s.size for s in r.spans)>median*1.25:
            r.kind="title"
        if r.kind=="text" and any(c in r.text for c in "∫∑√∂∞"):
            r.kind="formula"
            r.metadata["formula_representation"]="editable source Unicode, no inferred semantics"
    for i,info in enumerate(page.get_image_info()):
        box=displayed_box(info["bbox"],page)
        if box.width<2 or box.height<2:
            continue
        if any(box.coverage(t)>.9 for t in table_boxes):
            continue
        path=assets/f"p{number:04d}-image{i:03d}.png"
        crop_region(image,box,transform,path)
        result.regions.append(Region(page_number=number,kind="image",bbox=box,image_path=str(path),
                                     crop_path=str(path),source="raster",metadata={"xref":info.get("xref",0)}))
    if result.rotation:
        result.warnings.append("Rotazione normalizzata nelle coordinate; testo inclinato ricostruito a flusso.")
    return result

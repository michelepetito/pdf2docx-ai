from pathlib import Path
from io import BytesIO
import re
import statistics
import pymupdf
from ..document.models import BBox, Page, Region, TextSpan, TextLine, TableCell
from ..document.geometry import displayed_box,displayed_point
from .inspector import classify_page
from .renderer import crop_region


def extract_page(page, number: int, image, transform, assets: Path) -> Page:
    result = Page(number=number, width=page.rect.width, height=page.rect.height,
                  rotation=page.rotation, cropbox=BBox(**dict(zip(("x0","y0","x1","y1"),page.cropbox))),
                  classification=classify_page(page))
    result.metadata["coordinate_system"] = "displayed crop-relative PDF points, origin top-left"
    result.metadata["mediabox"]=list(page.mediabox)
    result.metadata["fonts"]=[dict(xref=f[0],extension=f[1],type=f[2],basefont=f[3],resource=f[4],encoding=f[5]) for f in page.get_fonts(full=True)]
    from ..reconstruction.fonts import embedding_flags
    for font in result.metadata['fonts']:
        if font['xref'] and font['extension'] in ('ttf','otf'):
            try:font['embedding_permissions']=embedding_flags(page.parent.extract_font(font['xref'])[3])
            except Exception:font['embedding_permissions']={'embedding_performed':False,'license_status':'undetermined'}
    raw = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
    raw_spans=[s for b in raw["blocks"] if b["type"]==0 for l in b["lines"] for s in l["spans"]]
    fills=[d for d in page.get_drawings() if d.get('fill') is not None]
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
                                bold=bool(s["flags"]&16),italic=bool(s["flags"]&2),color=f'{s["color"]:06X}',
                                baseline=displayed_point(s["origin"],page),ascender=s.get('ascender'),descender=s.get('descender'),advance_width=s['bbox'][2]-s['bbox'][0]) for s in items]
                center_y=(min(s.bbox.y0 for s in spans)+max(s.bbox.y1 for s in spans))/2 if spans else c.y0
                backgrounds=[d for d in fills if c.coverage(displayed_box(d['rect'],page))>.95]
                fill=min(backgrounds,key=lambda d:pymupdf.Rect(d['rect']).get_area())['fill'] if backgrounds else None
                background=''.join(f'{max(0,min(255,round(v*255))):02X}' for v in fill[:3]) if fill and len(fill)>=3 else None
                cells.append(TableCell(row=rr,col=col,text=text or "",bbox=c,spans=spans,
                                       background=background,
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
        measured_lines=[]
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
                              superscript=bool(flags & 1),color=f'{item["color"]:06X}',
                              baseline=displayed_point(item["origin"],page),ascender=item.get("ascender"),
                              descender=item.get("descender"),advance_width=(item['bbox'][2]-item['bbox'][0] if abs(line.get('dir',(1,0))[1])<.01 else item['bbox'][3]-item['bbox'][1] if abs(line.get('dir',(1,0))[0])<.01 else None))
                line_spans.append(span)
                sizes.append(span.size)
            if line_spans:
                clean_spans=[s.model_copy(deep=True) for s in line_spans]
                lb=BBox(x0=min(s.bbox.x0 for s in clean_spans),y0=min(s.bbox.y0 for s in clean_spans),
                        x1=max(s.bbox.x1 for s in clean_spans),y1=max(s.bbox.y1 for s in clean_spans))
                origin=max(clean_spans,key=lambda s:s.size).baseline
                direction=line.get("dir",(1.,0.))
                if page.rotation:
                    a=displayed_point((0,0),page);b=displayed_point(direction,page)
                    direction=(b[0]-a[0],b[1]-a[1])
                measured_lines.append(TextLine(text="".join(s.text for s in clean_spans),bbox=lb,
                                               baseline=origin,direction=direction,spans=clean_spans))
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
        if box.y0 > result.height*.85 and re.fullmatch(r"\s*(?:Pagina\s+|Page\s+)?\d+(?:\s*/\s*\d+)?\s*",text,re.I):
            kind="footer"
        region=Region(page_number=number,bbox=box,text=text,spans=spans,lines=measured_lines,kind=kind,
                      metadata={"line_count":len(lines),"rotation_normalized":page.rotation})
        result.regions.append(region)
    median=statistics.median(sizes) if sizes else 11
    for r in result.regions:
        if r.kind=="text" and r.spans and max(s.size for s in r.spans)>median*1.25:
            r.kind="title"
        if r.kind=='text' and r.spans and any(s.bold for s in r.spans) and len(r.text)<90 and sum(c.isalpha() for c in r.text)>4 and r.text.upper()==r.text:
            r.kind='title'
        if r.kind=="text" and any(c in r.text for c in "∫∑√∂∞"):
            r.kind="formula"
            r.metadata["formula_representation"]="editable source Unicode, no inferred semantics"
    for i,info in enumerate(page.get_image_info(xrefs=True)):
        box=displayed_box(info["bbox"],page)
        if box.width<2 or box.height<2:
            continue
        if any(box.coverage(t)>.9 for t in table_boxes):
            continue
        path=assets/f"p{number:04d}-image{i:03d}.png"
        native=False;decoded=False;reason="transformation, clipping or alpha requires rendered crop"
        xref=info.get("xref",0)
        matrix=info.get("transform",(1,0,0,1,0,0))
        if xref and not page.rotation and abs(matrix[1])+abs(matrix[2])<1e-5 and matrix[0]>0 and matrix[3]>0 and box.x0>=0 and box.y0>=0 and box.x1<=result.width+.1 and box.y1<=result.height+.1:
            extracted=page.parent.extract_image(xref)
            if extracted and not extracted.get("smask") and extracted.get("ext") in ("png","jpeg","jpg","bmp","tiff","gif"):
                path=path.with_suffix("."+extracted["ext"]);path.write_bytes(extracted["image"]);native=True;reason="original image bytes"
                # python-docx only recognizes some JPEG headers (JFIF/Exif).
                # Adobe/CMYK JPEG is valid PDF imagery but can fail here. Keep
                # the original asset and decode once to a lossless PNG at its
                # original resolution, rather than rasterizing the whole page.
                from docx.image.image import Image as WordImage
                from docx.image.exceptions import UnrecognizedImageError
                try:WordImage.from_blob(extracted['image'])
                except UnrecognizedImageError:
                    from PIL import Image
                    with Image.open(BytesIO(extracted['image'])) as original:
                        path=path.with_suffix('.png');original.convert('RGB').save(path)
                    native=False;decoded=True;reason='lossless PNG from source pixels; JPEG header unsupported by python-docx'
                    result.warnings.append('Immagine nativa decodificata in PNG per compatibilità DOCX; originale conservato negli asset.')
        if not native and not decoded: crop_region(image,box,transform,path).close()
        result.regions.append(Region(page_number=number,kind="image",bbox=box,image_path=str(path),
                                     crop_path=str(path),source="raster",metadata={"xref":xref,"native_image_bytes":native,"image_representation":reason}))
    if result.rotation:
        result.warnings.append("Rotazione normalizzata nelle coordinate; testo inclinato ricostruito a flusso.")
    def rgb(color):
        return ''.join(f'{max(0,min(255,round(v*255))):02X}' for v in color[:3]) if color and len(color)>=3 else None
    unsupported=0
    for drawing in page.get_drawings()[:5000]:
        drawbox=displayed_box(drawing['rect'],page)
        if any(drawbox.coverage(t)>.7 or (drawbox.area<.01 and t.x0-.5<=drawbox.x0<=t.x1+.5 and t.y0-.5<=drawbox.y0<=t.y1+.5) for t in table_boxes):continue
        for item in drawing['items']:
            fill=rgb(drawing.get('fill'));stroke=rgb(drawing.get('color'));width=drawing.get('width') or .5
            if item[0]=='re':box=displayed_box(item[1],page)
            elif item[0]=='l':
                a=displayed_point(item[1],page);b=displayed_point(item[2],page)
                if abs(a[0]-b[0])>.1 and abs(a[1]-b[1])>.1:unsupported+=1;continue
                box=BBox(x0=min(a[0],b[0])-width/2,y0=min(a[1],b[1])-width/2,x1=max(a[0],b[0])+width/2,y1=max(a[1],b[1])+width/2)
                fill=stroke;stroke=None
            else:unsupported+=1;continue
            if box.area<=0:continue
            result.regions.append(Region(page_number=number,kind='graphic',bbox=box,metadata={
                'source_primitive':item[0],'fill':fill,'stroke':stroke,'stroke_width':width,'decorative_source_only':True}))
    if unsupported:result.warnings.append(f'{unsupported} primitive grafiche curve/oblique non ricostruite come forme native.')
    return result

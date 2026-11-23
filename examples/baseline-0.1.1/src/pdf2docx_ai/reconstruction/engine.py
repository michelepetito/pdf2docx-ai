from pathlib import Path
from docx import Document as WordDocument
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_BREAK
from docx.shared import Pt
from .sections import configure_section
from .ooxml import set_columns
from .paragraphs import fill_paragraph
from .tables import add_table
from .images import add_image


class DocumentReconstructionEngine:
    def __init__(self):
        self.substitutions=set()
        self.non_editable=[]
        self.warnings=[]

    def reconstruct(self, model, output_path: Path, mode: str="editable"):
        doc=WordDocument()
        doc.core_properties.title="PDF2DOCX AI Fidelity"
        doc.core_properties.author="PDF2DOCX AI Fidelity"
        normal=doc.styles["Normal"];normal.font.name="Arial";normal.font.size=Pt(11)
        normal.paragraph_format.space_after=Pt(0)
        # Do not allow Word to silently compress source spacing to grid multiples.
        for index,page in enumerate(model.pages):
            section=doc.sections[0] if index==0 else doc.add_section(WD_SECTION_START.NEW_PAGE)
            left,right,top,bottom=configure_section(section,page,visual=mode=="visual")
            width=page.width-left-right
            if mode=="visual":
                if not page.preview_path: raise ValueError("Anteprima sorgente assente")
                from ..document.models import Region,BBox
                r=Region(page_number=page.number,kind="image",bbox=BBox(x0=0,y0=0,x1=page.width,y1=page.height),image_path=page.preview_path)
                p=add_image(doc,r,page.width,anchored=True)
                p.paragraph_format.line_spacing=Pt(1)
                self.non_editable.append(dict(page=page.number,kind="page",reason="Modalità visual: intera pagina rasterizzata"))
                continue
            body=[r for r in page.regions if r.kind not in ("header","footer") and not r.metadata.get("omit_editable")]
            prev_y=top;prev_col=0;current_cols=1
            for r in body:
                desired=2 if page.columns==2 and r.column>=0 else 1
                if desired!=current_cols:
                    # A continuous section allows spanning titles around true columns.
                    if current_cols==1 and not any(e.tag.endswith("}p") or e.tag.endswith("}tbl") for e in doc.element.body[:-1]):
                        set_columns(section,desired)
                    else:
                        section=doc.add_section(WD_SECTION_START.CONTINUOUS)
                        configure_section(section,page,columns=desired)
                    current_cols=desired;prev_col=0;prev_y=max(top,r.bbox.y0)
                if current_cols==2 and r.column>prev_col:
                    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=Pt(1)
                    p.add_run().add_break(WD_BREAK.COLUMN)
                    prev_y=top;prev_col=r.column
                col_width=(width-18)/2 if current_cols==2 else width
                col_left=left+(col_width+18)*max(0,r.column) if current_cols==2 else left
                gap=max(0,r.bbox.y0-prev_y)
                if r.kind=="table":
                    if gap>3:
                        p=doc.add_paragraph();p.paragraph_format.line_spacing=Pt(max(1,gap));p.paragraph_format.space_after=Pt(0)
                    add_table(doc,r,col_width)
                elif r.kind=="image":
                    p=add_image(doc,r,col_width)
                    if p: p.paragraph_format.space_before=Pt(gap)
                    self.non_editable.append(dict(page=page.number,region=r.id,kind="image",reason="Immagine sorgente raster"))
                elif r.kind=="formula" and r.metadata.get("ocr_format")=="latex":
                    # Unsupported LaTeX is shown from its original crop, with source retained in JSON.
                    if r.crop_path:
                        add_image(doc,r,col_width)
                        self.non_editable.append(dict(page=page.number,region=r.id,kind="formula",reason="LaTeX→Office Math non verificato; ritaglio originale"))
                    else:
                        fill_paragraph(doc.add_paragraph(),r,col_left,col_width,gap,self.substitutions)
                else:
                    fill_paragraph(doc.add_paragraph(),r,col_left,col_width,gap,self.substitutions)
                prev_y=max(prev_y,r.bbox.y1)
            if not body: doc.add_paragraph()
        doc.save(output_path)
        # Round-trip package parsing catches malformed OOXML/relationships.
        WordDocument(output_path)
        return dict(font_substitutions=sorted(self.substitutions),non_editable=self.non_editable,warnings=self.warnings)

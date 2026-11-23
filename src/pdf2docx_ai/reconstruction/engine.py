"""Native-flow geometric reconstruction: paragraphs, tabs, sections, true tables."""
from pathlib import Path
from docx import Document as WordDocument
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_BREAK
from docx.shared import Pt
from .sections import configure_section
from .ooxml import set_columns
from .paragraphs import fill_paragraph
from .layout import paragraph_geometry,column_geometry
from .fonts import FontResolver
from .tables import add_table
from .images import add_image
from .graphics import add_graphic


def _carrier(paragraph):
    fmt=paragraph.paragraph_format
    fmt.space_after=Pt(0);fmt.space_before=Pt(0);fmt.line_spacing=Pt(1)
    fmt.keep_with_next=False;fmt.widow_control=False
    for run in paragraph.runs:run.font.size=Pt(1)
    return paragraph


class GeometricLayoutReconstructionEngine:
    def __init__(self,font_policy='requested'):
        self.substitutions=set();self.non_editable=[];self.warnings=[]
        self.font_resolver=FontResolver(use_metric_fallback=font_policy=='metric');self.layout_trace=[]

    def reconstruct(self,model,output_path:Path,mode='editable',adjustments=None):
        adjustments=adjustments or {};doc=WordDocument()
        self.font_resolver.plan(model)
        doc.core_properties.title='PDF2DOCX AI Fidelity';doc.core_properties.author='PDF2DOCX AI Fidelity'
        normal=doc.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
        normal.paragraph_format.space_after=Pt(0);normal.paragraph_format.space_before=Pt(0)
        for index,page in enumerate(model.pages):
            if index:
                section=doc.add_section(WD_SECTION_START.NEW_PAGE)
                # A section break is structural, never an extra 11pt blank row.
                from docx.text.paragraph import Paragraph
                _carrier(Paragraph(doc.element.body[-2],doc))
            else:section=doc.sections[0]
            left,right,top,bottom=configure_section(section,page,visual=mode=='visual',resolver=self.font_resolver,adjustments=adjustments)
            if mode=='visual':
                from ..document.models import Region,BBox
                if not page.preview_path:raise ValueError('Anteprima sorgente assente')
                r=Region(page_number=page.number,kind='image',bbox=BBox(x0=0,y0=0,x1=page.width,y1=page.height),image_path=page.preview_path)
                _carrier(add_image(doc,r,page.width,anchored=True))
                self.non_editable.append(dict(page=page.number,kind='page',reason='Modalità visual: intera pagina rasterizzata'))
                continue
            pictures=[r for r in page.regions if r.kind=='image' and not r.metadata.get('omit_editable')]
            body=[r for r in page.regions if r.kind not in ('header','footer','image','graphic') and not r.metadata.get('omit_editable')]
            cols=column_geometry(page,left,right);current_columns=1;current_col=0;cursor=top;column_top=top;band_bottom=top
            first_paragraph=None;last_paragraph=None
            for region in body:
                desired=len(cols) if len(cols)>1 and region.column>=0 else 1
                if desired!=current_columns:
                    if current_columns>1:cursor=max(cursor,band_bottom)
                    if first_paragraph is None:
                        set_columns(section,desired,geometry=cols if desired>1 else None)
                    else:
                        section=doc.add_section(WD_SECTION_START.CONTINUOUS)
                        from docx.text.paragraph import Paragraph
                        _carrier(Paragraph(doc.element.body[-2],doc))
                        configure_section(section,page,columns=desired,geometry=cols if desired>1 else None,continuous=True,adjustments=adjustments)
                    current_columns=desired;current_col=0;column_top=cursor;band_bottom=cursor
                if desired>1 and region.column>current_col:
                    # A column break inside a body paragraph carries that
                    # paragraph's full line height into the next column.
                    _carrier(doc.add_paragraph()).add_run().add_break(WD_BREAK.COLUMN)
                    current_col=region.column;cursor=column_top
                col_left,col_right=cols[max(0,region.column)] if desired>1 else (left,page.width-right)
                available=col_right-col_left
                adjustment=adjustments.get(region.id,{})
                if region.kind=='table':
                    gap=max(0,region.bbox.y0+adjustment.get('y',0)-cursor+adjustment.get('before',0))
                    if last_paragraph is not None:last_paragraph.paragraph_format.space_after=Pt(gap)
                    elif gap>.5:
                        spacer=doc.add_paragraph();_carrier(spacer);spacer.paragraph_format.line_spacing=Pt(gap)
                        first_paragraph=first_paragraph or spacer
                    add_table(doc,region,available,left_origin=col_left,adjustment=adjustment,
                              resolver=self.font_resolver,substitutions=self.substitutions)
                    cursor=region.bbox.y1+adjustment.get('y',0);last_paragraph=None
                    band_bottom=max(band_bottom,cursor)
                    continue
                if region.kind=='formula' and region.metadata.get('ocr_format')=='latex' and region.crop_path:
                    pictures.append(region)
                    self.non_editable.append(dict(page=page.number,region=region.id,kind='formula',reason='LaTeX→Office Math non verificato; ritaglio originale'))
                    continue
                g=paragraph_geometry(region)
                if region.metadata.get('rotation_normalized'):
                    g['baseline']=region.bbox.y0+g['offset']
                gap=max(0,g['baseline']+adjustment.get('y',0)-g['offset']-cursor)
                p=doc.add_paragraph()
                fill_paragraph(p,region,col_left,available,gap,self.substitutions,resolver=self.font_resolver,geometry=g,adjustment=adjustment)
                first_paragraph=first_paragraph if first_paragraph is not None else p;last_paragraph=p
                actual_gap=max(0,gap+adjustment.get('before',0));pitch=g['pitch']+adjustment.get('pitch',0)
                cursor+=actual_gap+pitch*max(1,len(g['lines']) or region.text.count('\n')+1)
                band_bottom=max(band_bottom,cursor)
                self.layout_trace.append(dict(region=region.id,page=page.number,kind=region.kind,source_baseline=g['baseline'],
                    source_x=g['first_x'],gap_pt=gap,pitch_pt=g['pitch'],column=current_col,lines=len(g['lines']) or 1))
            if first_paragraph is None:
                first_paragraph=doc.add_paragraph();_carrier(first_paragraph)
            for picture in pictures:
                add_image(doc,picture,page.width,anchored=True,paragraph=first_paragraph)
                self.non_editable.append(dict(page=page.number,region=picture.id,kind=picture.kind,
                    reason='Immagine autonoma ancorata; testo principale Word modificabile',
                    source_bytes_preserved=bool(picture.metadata.get('native_image_bytes'))))
            # Allocate once: next_id scans the full XML tree, so doing it for
            # each source path makes a page with many rules quadratic.
            next_shape_id=first_paragraph.part.next_id
            for i,graphic in enumerate(r for r in page.regions if r.kind=='graphic'):
                add_graphic(first_paragraph,graphic,shape_id=next_shape_id+i)
        doc.save(output_path);WordDocument(output_path)
        return dict(font_substitutions=sorted(self.substitutions),font_matching=list(self.font_resolver.observations.values()),
                    non_editable=self.non_editable,warnings=self.warnings,layout_trace=self.layout_trace,
                    reconstruction_engine='Geometric Layout Reconstruction Engine')


# Public API preserved for CLI, GUI and integrations.
DocumentReconstructionEngine=GeometricLayoutReconstructionEngine

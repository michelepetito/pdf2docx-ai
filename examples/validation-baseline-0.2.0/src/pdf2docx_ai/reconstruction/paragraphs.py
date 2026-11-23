from docx.shared import Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_BREAK,WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from .fonts import FontResolver
from .layout import paragraph_geometry
from .ooxml import simple_math


def clean_xml_text(text):
    return ''.join(c for c in text if c in '\t\n\r' or (ord(c)>=32 and not 0xD800<=ord(c)<=0xDFFF))


def _flag(parent,name,value='0'):
    node=parent.find(qn(name))
    if node is None: node=OxmlElement(name);parent.append(node)
    node.set(qn('w:val'),value)


def _run(paragraph,span,resolver,substitutions,baseline=None):
    run=paragraph.add_run(clean_xml_text(span.text.lstrip('\n')))
    family,tracking,notice=resolver.resolve(span)
    run.font.name=family;run.font.size=Pt(max(1,min(span.size,400)))
    run.bold=span.bold;run.italic=span.italic
    # PDF has already reduced superscript size. Word vertAlign would shrink it
    # a second time: preserve the measured size and apply native baseline shift.
    run.font.superscript=span.superscript if span.baseline is None else False
    try:run.font.color.rgb=RGBColor.from_string(span.color)
    except ValueError:pass
    props=run._r.get_or_add_rPr();_flag(props,'w:snapToGrid')
    if baseline is not None and span.baseline is not None:
        shift=baseline-span.baseline[1]
        if abs(shift)>.25:
            position=OxmlElement('w:position');position.set(qn('w:val'),str(round(shift*2)));props.append(position)
    if abs(tracking)>.005:
        spacing=OxmlElement('w:spacing');spacing.set(qn('w:val'),str(round(tracking*20)));props.append(spacing)
    if notice and substitutions is not None:substitutions.add(notice)
    return run


def fill_paragraph(paragraph,region,left_origin,width,gap=0,substitutions=None,*,resolver=None,geometry=None,adjustment=None):
    resolver=resolver or FontResolver();g=geometry or paragraph_geometry(region);adjustment=adjustment or {}
    fmt=paragraph.paragraph_format
    # Explicit properties avoid inherited Heading/List spacing and document grid.
    paragraph.style='Heading 1' if region.kind=='title' and g['size']>17 else 'Heading 2' if region.kind=='title' else 'List Number' if region.kind=='list' and region.text.lstrip()[:1].isdigit() else 'List Bullet' if region.kind=='list' else 'Normal'
    fmt.space_before=Pt(max(0,min(gap+adjustment.get('before',0),1000)));fmt.space_after=Pt(0)
    rotated=bool(region.metadata.get('rotation_normalized'))
    indent=0 if rotated else g['x']-left_origin+adjustment.get('left',0)
    fmt.left_indent=Pt(max(-36,indent));fmt.first_line_indent=Pt(0 if rotated else g['first_x']-g['x'])
    # A PDF ink edge is a lower bound for the original paragraph width. Allow
    # two points of native paragraph overhang only when it touches that bound,
    # accommodating twip/font rounding without changing glyph size or spacing.
    near_edge = not rotated and g['lines'] and max(l.bbox.x1-left_origin for l in g['lines']) >= width-1
    fmt.right_indent=Pt(-2 if near_edge else 0)
    fmt.widow_control=False;fmt.keep_together=False;fmt.keep_with_next=False
    fmt.page_break_before=False;fmt.line_spacing=Pt(max(1,g['pitch']+adjustment.get('pitch',0)))
    fmt.alignment={'left':WD_ALIGN_PARAGRAPH.LEFT,'right':WD_ALIGN_PARAGRAPH.RIGHT,'center':WD_ALIGN_PARAGRAPH.CENTER,'justify':WD_ALIGN_PARAGRAPH.JUSTIFY}[region.alignment]
    props=paragraph._p.get_or_add_pPr();_flag(props,'w:snapToGrid');_flag(props,'w:contextualSpacing')
    if region.kind=='list':
        num=OxmlElement('w:numPr');n=OxmlElement('w:numId');n.set(qn('w:val'),'0');num.append(n);props.append(num)
    lines=g['lines']
    if region.kind=='formula' and region.metadata.get('formula_representation')=='simple_unicode_math':
        simple_math(paragraph,clean_xml_text(region.text))
    elif lines:
        for index,line in enumerate(lines):
            if index:paragraph.add_run().add_break(WD_BREAK.LINE)
            previous=None
            for span in line.spans:
                if previous:
                    delta=span.bbox.x0-previous.bbox.x1
                    if delta>max(10,span.size):
                        stop=span.bbox.x0-left_origin+adjustment.get('left',0)
                        if stop>0:fmt.tab_stops.add_tab_stop(Pt(stop),WD_TAB_ALIGNMENT.LEFT);paragraph.add_run('\t')
                _run(paragraph,span,resolver,substitutions,line.baseline[1]);previous=span
    elif region.spans:
        for span in region.spans:
            # Old JSON checkpoints remain readable; explicit original line breaks
            # are preserved when typed line geometry is unavailable.
            if span.text.startswith('\n'):paragraph.add_run('\n')
            _run(paragraph,span,resolver,substitutions)
    else:
        run=paragraph.add_run(clean_xml_text(region.text));run.font.name='Arial';run.font.size=Pt(g['size'])
    return paragraph

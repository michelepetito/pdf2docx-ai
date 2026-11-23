"""Editable DrawingML rectangles for actual source rules/background decoration.

Never used as containers for text or as a generic layout grid.
"""
from docx.oxml import OxmlElement
from lxml import etree

WPS='http://schemas.microsoft.com/office/word/2010/wordprocessingShape'


def add_graphic(paragraph,region,shape_id=None):
    drawing=OxmlElement('w:drawing');anchor=OxmlElement('wp:anchor')
    for key,value in dict(distT='0',distB='0',distL='0',distR='0',simplePos='0',relativeHeight='0',behindDoc='1',locked='0',layoutInCell='1',allowOverlap='1').items():anchor.set(key,value)
    simple=OxmlElement('wp:simplePos');simple.set('x','0');simple.set('y','0');anchor.append(simple)
    for tag,offset in [('H',region.bbox.x0),('V',region.bbox.y0)]:
        pos=OxmlElement('wp:position'+tag);pos.set('relativeFrom','page')
        off=OxmlElement('wp:posOffset');off.text=str(round(offset*12700));pos.append(off);anchor.append(pos)
    width=max(1,round(region.bbox.width*12700));height=max(1,round(region.bbox.height*12700))
    extent=OxmlElement('wp:extent');extent.set('cx',str(width));extent.set('cy',str(height));anchor.append(extent)
    anchor.append(OxmlElement('wp:wrapNone'))
    props=OxmlElement('wp:docPr');props.set('id',str(shape_id if shape_id is not None else paragraph.part.next_id));props.set('name','Source decoration '+region.id);anchor.append(props)
    graphic=OxmlElement('a:graphic');data=OxmlElement('a:graphicData');data.set('uri',WPS)
    shape=etree.Element('{'+WPS+'}wsp');shape.append(etree.Element('{'+WPS+'}cNvSpPr'))
    sp=etree.Element('{'+WPS+'}spPr');xfrm=OxmlElement('a:xfrm')
    off=OxmlElement('a:off');off.set('x','0');off.set('y','0');xfrm.append(off)
    ext=OxmlElement('a:ext');ext.set('cx',str(width));ext.set('cy',str(height));xfrm.append(ext);sp.append(xfrm)
    geometry=OxmlElement('a:prstGeom');geometry.set('prst','rect');geometry.append(OxmlElement('a:avLst'));sp.append(geometry)
    fill=region.metadata.get('fill')
    if fill:
        f=OxmlElement('a:solidFill');c=OxmlElement('a:srgbClr');c.set('val',fill);f.append(c);sp.append(f)
    else:sp.append(OxmlElement('a:noFill'))
    line=OxmlElement('a:ln');line.set('w',str(round((region.metadata.get('stroke_width') or .5)*12700)))
    stroke=region.metadata.get('stroke')
    if stroke:
        f=OxmlElement('a:solidFill');c=OxmlElement('a:srgbClr');c.set('val',stroke);f.append(c);line.append(f)
    else:line.append(OxmlElement('a:noFill'))
    sp.append(line);shape.append(sp);shape.append(etree.Element('{'+WPS+'}bodyPr'))
    data.append(shape);graphic.append(data);anchor.append(graphic);drawing.append(anchor);paragraph.add_run()._r.append(drawing)

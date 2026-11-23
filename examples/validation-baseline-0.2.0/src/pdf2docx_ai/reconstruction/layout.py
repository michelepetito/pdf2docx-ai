"""Recover native flow rules from physical lines, rather than glyph boxes."""
from __future__ import annotations
from copy import deepcopy
from statistics import median
from ..document.models import BBox,TextLine


def physical_lines(region):
    lines=deepcopy(region.lines)
    if not lines: return []
    # PDF text extraction can emit a separate line per tab-aligned fragment.
    rows=[]
    for line in sorted(lines,key=lambda l:(round(l.baseline[1],1),l.bbox.x0)):
        if rows and abs(rows[-1][0].baseline[1]-line.baseline[1])<.8 and abs(line.direction[1])<.05:
            rows[-1].append(line)
        else: rows.append([line])
    result=[]
    for row in rows:
        spans=sorted([s for l in row for s in l.spans],key=lambda s:s.bbox.x0)
        b=BBox(x0=min(l.bbox.x0 for l in row),y0=min(l.bbox.y0 for l in row),x1=max(l.bbox.x1 for l in row),y1=max(l.bbox.y1 for l in row))
        result.append(TextLine(id=row[0].id,text=''.join(s.text for s in spans),bbox=b,
            baseline=max(row,key=lambda l:max((s.size for s in l.spans),default=0)).baseline,
            direction=row[0].direction,spans=spans,provenance=row[0].provenance))
    return result


def paragraph_geometry(region):
    lines=physical_lines(region)
    size=max((s.size for s in region.spans),default=region.metadata.get('font_size',11))
    if lines:
        advances=[b.baseline[1]-a.baseline[1] for a,b in zip(lines,lines[1:]) if b.baseline[1]-a.baseline[1]>1]
        pitch=median(advances) if advances else size*1.15
        pitch=max(size*.95,min(pitch,size*3))
        first=lines[0].baseline[1]
        # Empirical baseline fraction for exact Word line boxes. The iterative
        # renderer corrects font/renderer-specific deviations, within bounds.
        offset=.8*pitch
        first_x=lines[0].bbox.x0
        continuation=median([l.bbox.x0 for l in lines[1:]]) if len(lines)>1 else first_x
        return dict(lines=lines,size=size,pitch=pitch,baseline=first,offset=offset,
                    x=continuation,first_x=first_x,height=pitch*len(lines))
    count=max(1,region.text.count('\n')+1)
    pitch=max(size*1.15,min(region.bbox.height/count,size*1.6))
    return dict(lines=[],size=size,pitch=pitch,baseline=region.bbox.y0+.8*pitch,offset=.8*pitch,
                x=region.bbox.x0,first_x=region.bbox.x0,height=pitch*count)


def page_margins(page):
    text=[r for r in page.regions if r.kind not in ('header','footer','image','graphic') and not r.metadata.get('omit_editable')]
    if not text: return (36.,36.,36.,36.)
    normal=[r for r in text if not r.metadata.get('rotation_normalized')]
    if not normal:
        # The narrow displayed glyph box of vertical text is not a horizontal
        # Word text area. The documented readable-flow fallback needs room for
        # the original unrotated advance, without wrapping every few letters.
        inset=min(36.,page.width*.06)
        return inset,inset,max(0,min(r.bbox.y0 for r in text)),8.
    text=normal
    left=max(0,min(r.bbox.x0 for r in text))
    right=max(0,min(left,page.width-max(r.bbox.x1 for r in text)))
    first=min(text,key=lambda r:r.bbox.y0)
    g=paragraph_geometry(first)
    top=max(0,g['baseline']-g['offset'])
    # Keep the section-break carrier inside the source page. Sparse pages have
    # no evidence for a large bottom margin: do not invent one from last text.
    return left,right,top,8.


def column_geometry(page,left,right):
    if page.columns<2: return [(left,page.width-right)]
    measured=page.metadata.get('column_geometry')
    if measured and len(measured)==page.columns:return [tuple(pair) for pair in measured]
    groups=[]
    for column in range(page.columns):
        items=[r for r in page.regions if r.column==column and r.kind not in ('header','footer','image','graphic') and not r.metadata.get('omit_editable')]
        if items: groups.append((min(r.bbox.x0 for r in items),max(r.bbox.x1 for r in items)))
    if len(groups)<2: return [(left,page.width-right)]
    # Infer the gutter from persistent text edges, then retain unequal widths.
    result=[]
    for i,(start,end) in enumerate(groups):
        boundary=groups[i+1][0]-max(8,min(24,groups[i+1][0]-end)) if i+1<len(groups) else page.width-right
        result.append((start,max(end,boundary)))
    return result

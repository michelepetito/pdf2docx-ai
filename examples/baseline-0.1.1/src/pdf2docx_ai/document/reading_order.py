from .models import Page, Region


def order_regions(page: Page) -> Page:
    """Conservative two-column split, separated by full-width bands."""
    regions = page.regions
    body = [r for r in regions if r.kind not in ("header", "footer")]
    text = [r for r in body if r.kind in ("text", "list", "title", "caption", "formula")]
    mid = page.width / 2
    left = [r for r in text if r.bbox.x1 <= mid + 8 and r.bbox.x0 < page.width*.35]
    right = [r for r in text if r.bbox.x0 >= mid - 8]
    # Require vertically overlapping blocks, not two unrelated short paragraphs.
    overlap = any(min(a.bbox.y1,b.bbox.y1)-max(a.bbox.y0,b.bbox.y0)>4 for a in left for b in right)
    two = bool(left and right and overlap)
    page.columns = 2 if two else 1
    if not two:
        ordered = sorted(regions, key=lambda r:(r.bbox.y0, r.bbox.x0))
    else:
        wide = sorted([r for r in body if r.bbox.x0 < mid-8 and r.bbox.x1 > mid+8], key=lambda r:r.bbox.y0)
        pending = [r for r in body if r not in wide]
        ordered = sorted([r for r in regions if r.kind == "header"], key=lambda r:r.bbox.y0)
        for separator in [*wide, None]:
            bound = separator.bbox.y0 if separator else float("inf")
            band = [r for r in pending if r.bbox.y0 < bound]
            for r in band:
                r.column = 1 if (r.bbox.x0+r.bbox.x1)/2 > mid else 0
            ordered.extend(sorted(band,key=lambda r:(r.column,r.bbox.y0,r.bbox.x0)))
            pending = [r for r in pending if r not in band]
            if separator:
                separator.column = -1  # Spanning band.
                ordered.append(separator)
        ordered.extend(sorted([r for r in regions if r.kind == "footer"], key=lambda r:r.bbox.y0))
    for i,r in enumerate(ordered):
        r.reading_order = i
    page.regions = ordered
    return page

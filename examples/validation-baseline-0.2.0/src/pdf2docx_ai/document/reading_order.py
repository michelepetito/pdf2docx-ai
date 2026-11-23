"""Infer persistent text lanes, preserving full-width bands and tabular rows."""
from bisect import bisect_right
from itertools import combinations
from statistics import median
from uuid import uuid4

from .models import BBox, Page


_OUT_OF_FLOW = {"header", "footer", "image", "graphic"}


def _atoms(regions):
    """Measured lines allow detection even when MuPDF joins adjacent columns."""
    result = []
    for region in regions:
        lines = [line for line in region.lines if abs(line.direction[1]) < .1]
        for line in lines:
            result.append((line.bbox, region, line.baseline[1]))
        if not lines:
            result.append((region.bbox, region, region.bbox.y0))
    return result


def _overlap(a, b):
    return min(a.y1, b.y1) - max(a.y0, b.y0)


def _infer_columns(atoms, em):
    if len(atoms) < 2:
        return None
    content_left = min(a[0].x0 for a in atoms)
    content_right = max(a[0].x1 for a in atoms)
    content_width = content_right - content_left
    tolerance = max(3., min(12., em))
    minimum_width = max(48., content_width * .14)
    minimum_gap = max(8., em * .7)
    clusters = []
    for atom in sorted(atoms, key=lambda a: a[0].x0):
        if clusters and atom[0].x0 - clusters[-1][0][0].x0 <= tolerance:
            clusters[-1].append(atom)
        else:
            clusters.append([atom])
    clusters = sorted(sorted(clusters, key=len, reverse=True)[:10], key=lambda c: c[0][0].x0)
    best = None
    for count in (2, 3):
        for chosen in combinations(clusters, count):
            starts = [min(a[0].x0 for a in cluster) for cluster in chosen]
            if any(b - a < minimum_width + minimum_gap for a, b in zip(starts, starts[1:])):
                continue
            lanes = []
            for i, cluster in enumerate(chosen):
                end = starts[i + 1] - minimum_gap if i + 1 < count else float("inf")
                lanes.append([a for a in cluster if a[0].x1 <= end and a[0].width >= minimum_width])
            if any(not lane or sum(a[0].height for a in lane) < em * 1.7 for lane in lanes):
                continue
            # Short date/label rows beside a broad paragraph are native tabs,
            # unless a narrow lane has genuine multiline paragraph evidence.
            label_lane = False
            for lane in lanes[:-1]:
                if max(a[0].width for a in lane) >= content_width * .24:
                    continue
                owners = {a[1].id: a[1] for a in lane}
                multiline = any(len({round(l.baseline[1], 1) for l in r.lines}) > 1
                                or (not r.lines and r.bbox.height >= em * 2)
                                for r in owners.values())
                if not multiline:
                    label_lane = True
            if label_lane:
                continue
            # An indentation alone is insufficient: adjacent lanes must contain
            # vertically overlapping text, across a persistent horizontal gap.
            if any(not any(_overlap(a[0], b[0]) > min(4., em * .3)
                               for a in left for b in right)
                   for left, right in zip(lanes, lanes[1:])):
                continue
            score = sum(len(lane) for lane in lanes)
            if best is None or score > best[0]:
                geometry = []
                for i, lane in enumerate(lanes):
                    end = max(a[0].x1 for a in lane)
                    if i + 1 < count:
                        gap = max(minimum_gap, min(24., starts[i + 1] - end))
                        end = max(end, starts[i + 1] - gap)
                    else:
                        end = max(end, content_right)
                    geometry.append((starts[i], end))
                best = (score, geometry)
    return best[1] if best else None


def _lane(box, cuts):
    if any(box.x0 < cut - 1 and box.x1 > cut + 1 for cut in cuts):
        return -1
    return bisect_right(cuts, (box.x0 + box.x1) / 2)


def _split_joined_regions(regions, cuts):
    result = []
    for region in regions:
        groups = {}
        for line in region.lines:
            groups.setdefault(_lane(line.bbox, cuts), []).append(line)
        if len(groups) < 2 or -1 in groups or not any(
                _overlap(a.bbox, b.bbox) > 4
                for i, left in groups.items() for j, right in groups.items() if i < j
                for a in left for b in right):
            result.append(region)
            continue
        for i, lines in sorted(groups.items()):
            lines = sorted(lines, key=lambda l: (l.baseline[1], l.bbox.x0))
            spans = []
            for line in lines:
                copies = [s.model_copy(deep=True) for s in line.spans]
                if spans and copies:
                    copies[0].text = "\n" + copies[0].text
                spans.extend(copies)
            box = BBox(x0=min(l.bbox.x0 for l in lines), y0=min(l.bbox.y0 for l in lines),
                       x1=max(l.bbox.x1 for l in lines), y1=max(l.bbox.y1 for l in lines))
            result.append(region.model_copy(update={"id": region.id if i == min(groups) else uuid4().hex,
                "bbox": box, "lines": lines, "spans": spans, "text": "\n".join(l.text for l in lines),
                "metadata": {**region.metadata, "split_from_region": region.id, "line_count": len(lines)}}))
    return result


def _join_tab_rows(regions):
    """Join independent, single-line fragments that share a measured baseline.

    MuPDF may split a right-aligned date from the left-hand invoice number.
    Keeping them as separate paragraphs necessarily consumes another line.
    Multiline blocks and true column lanes are deliberately left alone.
    """
    result = []
    supported=("text", "title", "list", "caption", "header", "footer")
    for region in regions:
        if len(region.lines) != 1 or region.kind not in supported:
            result.append(region)
            continue
        line = region.lines[0]
        match = next((r for r in reversed(result)
            if r.column == region.column and r.kind in supported
            and r.lines and all(abs(l.baseline[1] - line.baseline[1]) < .6 for l in r.lines)
            and abs(line.direction[1]) < .05
            and r.bbox.x1 + 4 < region.bbox.x0), None)
        if match is None:
            result.append(region)
            continue
        match.lines.extend(region.lines)
        match.spans.extend(region.spans)
        match.text += "\t" + region.text
        match.bbox = BBox(x0=min(match.bbox.x0, region.bbox.x0), y0=min(match.bbox.y0, region.bbox.y0),
                          x1=max(match.bbox.x1, region.bbox.x1), y1=max(match.bbox.y1, region.bbox.y1))
        match.alignment = "left"
        match.metadata["tab_joined_regions"] = [*match.metadata.get("tab_joined_regions", []), region.id]
    return result


def order_regions(page: Page) -> Page:
    """Recover 1-3 native text columns without treating decoration as flow."""
    row_key=lambda r:(round(min((l.baseline[1] for l in r.lines),default=r.bbox.y0),1),r.bbox.x0)
    headers = sorted((r for r in page.regions if r.kind == "header"), key=row_key)
    footers = sorted((r for r in page.regions if r.kind == "footer"), key=row_key)
    decoration = [r for r in page.regions if r.kind in ("image", "graphic") or r.metadata.get("omit_editable")]
    body = [r for r in page.regions if r.kind not in _OUT_OF_FLOW and not r.metadata.get("omit_editable")]
    decoration = [r for r in decoration if r.kind not in ("header", "footer")]
    atoms = _atoms(body)
    em = median([s.size for r in body for s in r.spans]) if any(r.spans for r in body) else 11.
    geometry = _infer_columns(atoms, em)
    page.metadata.pop("column_geometry", None)
    for region in page.regions:
        region.column = -1 if region.kind in _OUT_OF_FLOW else 0
    if geometry is None:
        page.columns = 1
        paired = any(abs(a[2] - b[2]) < 1.2 and a[0].x1 + em < b[0].x0
                     for a in atoms for b in atoms)
        page.metadata["reading_order_mode"] = "tabs" if paired else "single-column"
        ordered_body = sorted(body, key=lambda r: (r.bbox.y0, r.bbox.x0))
    else:
        page.columns = len(geometry)
        page.metadata["column_geometry"] = [list(pair) for pair in geometry]
        page.metadata["reading_order_mode"] = "native-columns"
        cuts = [(a[1] + b[0]) / 2 for a, b in zip(geometry, geometry[1:])]
        body = _split_joined_regions(body, cuts)
        spanning = sorted((r for r in body if _lane(r.bbox, cuts) < 0), key=lambda r: (r.bbox.y0, r.bbox.x0))
        pending = [r for r in body if r not in spanning]
        ordered_body = []
        for separator in [*spanning, None]:
            bound = separator.bbox.y0 if separator else float("inf")
            band = [r for r in pending if r.bbox.y0 < bound]
            lanes = {_lane(r.bbox, cuts) for r in band}
            active = len(lanes) > 1 and any(
                _lane(a.bbox, cuts) != _lane(b.bbox, cuts) and _overlap(a.bbox, b.bbox) > 4
                for a in band for b in band)
            for region in band:
                region.column = _lane(region.bbox, cuts) if active else -1
            ordered_body.extend(sorted(band, key=lambda r: (r.column, r.bbox.y0, r.bbox.x0)))
            pending = [r for r in pending if r not in band]
            if separator:
                separator.column = -1
                ordered_body.append(separator)
    page.regions = [*_join_tab_rows(headers), *_join_tab_rows(ordered_body), *decoration, *_join_tab_rows(footers)]
    for i, region in enumerate(page.regions):
        region.reading_order = i
    return page

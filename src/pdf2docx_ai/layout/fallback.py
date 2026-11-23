"""Projection-based segmentation, not an AI semantic layout model."""
from __future__ import annotations
import numpy as np
from PIL import Image
from pdf2docx_ai.document.models import BBox, Region
from .base import LayoutDetector


def _runs(indices, gap):
    if len(indices) == 0:
        return []
    splits = np.flatnonzero(np.diff(indices) > gap) + 1
    return [(int(x[0]), int(x[-1]) + 1) for x in np.split(indices, splits) if len(x)]


class GeometricLayoutDetector(LayoutDetector):
    name = "geometric"

    def detect(self, image: Image.Image, page_number: int = 1) -> list[Region]:
        # Work at bounded resolution so segmentation is independent of scan size.
        gray = image.convert("L")
        scale = min(1, 1400 / max(gray.size))
        if scale < 1:
            gray = gray.resize((round(gray.width * scale), round(gray.height * scale)))
        ink = np.asarray(gray) < 190
        ys, xs = np.nonzero(ink)
        if len(xs) < 4:
            return []
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        # Conservative whitespace columns. Running headers may mask the gutter;
        # ambiguity leaves one region rather than claiming semantic certainty.
        active = ink[y0:y1, x0:x1]
        density = active.mean(axis=0)
        middle0, middle1 = int(active.shape[1] * .3), int(active.shape[1] * .7)
        gaps = _runs(np.flatnonzero(density[middle0:middle1] < .003) + middle0,
                     gap=1)
        gaps = [(a, b) for a, b in gaps if b - a > max(12, active.shape[1] * .025)]
        columns = [(int(x0), int(x1))]
        if gaps:
            a, b = max(gaps, key=lambda p: p[1] - p[0])
            left, right = active[:, :a], active[:, b:]
            if left.size and right.size and left.mean() > .01 and right.mean() > .01:
                columns = [(int(x0), int(x0 + a)), (int(x0 + b), int(x1))]
        regions = []
        for col, (left, right) in enumerate(columns):
            occupied_rows = np.flatnonzero(ink[:, left:right].any(axis=1))
            for top, bottom in _runs(occupied_rows, max(12, int(gray.height * .012))):
                sub = ink[top:bottom, left:right]
                occupied_cols = np.flatnonzero(sub.any(axis=0))
                if len(occupied_cols) == 0 or bottom - top < 2:
                    continue
                margin = 3
                box = BBox(x0=max(0, (left + occupied_cols.min() - margin) / scale),
                           y0=max(0, (top - margin) / scale),
                           x1=min(image.width, (left + occupied_cols.max() + 1 + margin) / scale),
                           y1=min(image.height, (bottom + margin) / scale))
                regions.append(Region(page_number=page_number, bbox=box, kind="text", source="ocr",
                                      reading_order=len(regions), column=col,
                                      metadata={"layout_detector": self.name, "coordinate_space": "pixels",
                                                "semantic_classification": False}))
        return regions


# Friendly alias for integrations written before the detector name was settled.
FallbackLayoutDetector = GeometricLayoutDetector


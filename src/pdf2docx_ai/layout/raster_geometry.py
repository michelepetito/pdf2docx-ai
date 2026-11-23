"""Conservative raster evidence, separate from OCR/model-provided coordinates."""
import numpy as np
from .fallback import GeometricLayoutDetector
from ..document.models import OCRWord


def text_regions(image):
    ink=np.asarray(image.convert('L'))<190
    # A plan/chart is an independent graphic even when OCR can read its labels.
    # Long rules are strong evidence against replacing it with plain text.
    # Whole-page scan recognition does not use this gate.
    if (np.any(ink.mean(axis=1)>.55) or np.any(ink.mean(axis=0)>.55)):
        return []
    regions=GeometricLayoutDetector().detect(image)
    density=float(ink.mean())
    candidates=[r for r in regions if r.bbox.width>image.width*.08 and r.bbox.height<image.height*.30]
    if len(candidates)>=2:return candidates
    if density<.30 and len(regions)==1:return regions
    return []


def align_plain_text(result,image):
    if result.words or result.format!='text':return result
    lines=[line.strip() for line in result.text.splitlines() if line.strip()]
    regions=text_regions(image)
    if not lines or len(lines)!=len(regions):return result
    regions.sort(key=lambda r:(r.column,r.bbox.y0,r.bbox.x0))
    words=[OCRWord(text=text,bbox=region.bbox,line=str(i),confidence=None) for i,(text,region) in enumerate(zip(lines,regions))]
    return result.model_copy(update={'words':words,'warnings':result.warnings+[
        'Box di riga stimati dalla segmentazione raster con corrispondenza numerica; non forniti dal modello OCR.']})

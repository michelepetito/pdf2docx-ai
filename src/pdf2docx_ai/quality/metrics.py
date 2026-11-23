import numpy as np
from rapidfuzz.distance import Levenshtein


def edit_distance(reference, hypothesis) -> int:
    # No cutoff, fuzzy/token-sort ratio, or max-length denominator. CER/WER
    # remain exact edit counts divided by the reference length, possibly >1.
    return Levenshtein.distance(reference,hypothesis,weights=(1,1,1),processor=None)


def text_metrics(reference: str, hypothesis: str) -> dict:
    # Preserve accents and case; only collapse whitespace, explicitly reported.
    ref=" ".join(reference.split());hyp=" ".join(hypothesis.split())
    rw,hw=ref.split(),hyp.split()
    return dict(cer=edit_distance(ref,hyp)/max(1,len(ref)),wer=edit_distance(rw,hw)/max(1,len(rw)),
                reference_characters=len(ref),reference_words=len(rw),normalization="whitespace only")


def _mean7(a):
    p=np.pad(a,3,mode="reflect")
    integral=np.pad(p,((1,0),(1,0))).cumsum(0).cumsum(1)
    return (integral[7:,7:]-integral[:-7,7:]-integral[7:,:-7]+integral[:-7,:-7])/49


def ssim_map(original, result):
    """Wang SSIM, grayscale 8-bit, uniform 7x7 window, sample covariance.

    This measures rendered appearance, never OCR correctness.
    """
    a=np.asarray(original.convert("L"),dtype=np.float64)
    b=np.asarray(result.convert("L"),dtype=np.float64)
    if a.shape!=b.shape or min(a.shape)<7: raise ValueError("SSIM richiede canvas uguali e almeno 7 pixel")
    ma,mb=_mean7(a),_mean7(b)
    va=(_mean7(a*a)-ma*ma)*49/48
    vb=(_mean7(b*b)-mb*mb)*49/48
    cov=(_mean7(a*b)-ma*mb)*49/48
    score=((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))
    return np.clip(score,-1,1)


def ssim(original, result) -> float:
    return float(ssim_map(original,result)[3:-3,3:-3].mean())

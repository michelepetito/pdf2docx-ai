from types import SimpleNamespace
import re
import pymupdf
import pytest
from pdf2docx_ai.document.models import BBox, TextSpan
from pdf2docx_ai.reconstruction.fonts import FontResolver,installed_font,word_font
from pdf2docx_ai.reconstruction import fonts


@pytest.mark.parametrize('family',['Times New Roman','Courier New'])
@pytest.mark.parametrize('metric_origin',['system','fontconfig'])
def test_missing_family_uses_the_same_measured_fallback_in_word(family,metric_origin,monkeypatch):
    path,_=installed_font(family)
    if not path:pytest.skip('Requires an installed metric font')
    font=pymupdf.Font(fontfile=path)
    allowed={'Times New Roman':('timesnewroman','liberationserif'),
             'Courier New':('couriernew','liberationmono')}
    if not re.sub('[^a-z0-9]','',font.name.lower()).startswith(allowed[family]):
        pytest.skip('The system returned an unrelated fallback; install the documented metric fonts')
    if metric_origin=='fontconfig':
        # Exercise Linux-style fontconfig evidence even on a Mac with bundled
        # fonts: the measured file is unchanged, only its provenance differs.
        def detected(candidate,bold=False,italic=False):
            found,actual=installed_font(candidate,bold,italic)
            if found and candidate in ('Times New Roman','Courier New'):
                actual={'Times New Roman':'Liberation Serif','Courier New':'Liberation Mono'}[candidate]
            return found,actual
        monkeypatch.setattr(fonts,'installed_font',detected)
    spans=[]
    for text in ['Narrow iii and wide WWW 12345','A measured paragraph with words','Totals 98.76: project reference']:
        width=font.text_length(text,fontsize=12)
        spans.append(TextSpan(text=text,font='AbsentScientificFamily-XYZ',size=12,advance_width=width,
                              bbox=BBox(x0=50,y0=50,x1=50+width,y1=65)))
    resolver=FontResolver()
    resolver.plan(SimpleNamespace(pages=[SimpleNamespace(regions=[SimpleNamespace(spans=spans,cells=[])])]))
    for span in spans:
        selected,tracking,notice=resolver.resolve(span)
        assert selected==family
        assert abs(tracking)<.005
        assert 'unavailable' in notice
    observation=next(iter(resolver.observations.values()))
    assert observation['available'] is False
    assert observation['resolved_family_available'] is True
    assert observation['aggregate_width_error']<.001
    assert observation['selection_samples']==3


def test_condensed_helvetica_preserves_narrow_family():
    assert word_font('Helvetica-Condensed-Bold')[0]=='Arial Narrow'

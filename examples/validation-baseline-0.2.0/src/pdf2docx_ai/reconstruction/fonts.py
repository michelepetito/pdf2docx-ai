"""Metric-aware installed font resolution; PDF fonts are never redistributed."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import re,shutil,struct,subprocess
from collections import defaultdict
import pymupdf

_ALIASES=(("helveticacondensed","Arial Narrow"),("helveticanarrow","Arial Narrow"),
          ("helvetica","Arial"),("liberationsansnarrow","Arial Narrow"),("liberationsans","Arial"),
          ("timesnewroman","Times New Roman"),("liberationserif","Times New Roman"),("times","Times New Roman"),
          ("couriernew","Courier New"),("liberationmono","Courier New"),("courier","Courier New"),
          ("carlito","Calibri"),("calibri","Calibri"),("dejavusans","DejaVu Sans"),
          ("dejavuserif","DejaVu Serif"),("notosans","Noto Sans"),("notoserif","Noto Serif"))


def word_font(pdf_font: str) -> tuple[str,str|None]:
    base=re.sub(r"^[A-Z]{6}\+","",pdf_font)
    key=re.sub(r"[-,_\s]","",base.lower())
    family=None
    for prefix,target in _ALIASES:
        if key.startswith(prefix): family=target;break
    family=family or re.sub(r"[-,]?(?:BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular|PSMT|MT)$","",base,flags=re.I)
    return family, f"{pdf_font} → {family}" if family!=base else None


def embedding_flags(data: bytes) -> dict:
    """Inspect OS/2.fsType. This is technical metadata, not a license grant."""
    try:
        offset=struct.unpack_from('>I',data,12)[0] if data[:4]==b'ttcf' else 0
        count=struct.unpack_from('>H',data,offset+4)[0]
        for i in range(count):
            tag,_,table,length=struct.unpack_from('>4sIII',data,offset+12+i*16)
            if tag==b'OS/2' and length>=10:
                value=struct.unpack_from('>H',data,table+8)[0]
                return dict(fs_type=value,restricted=bool(value&2),preview_print_only=bool(value&4),
                            editable_embedding=bool(value&8),no_subsetting=bool(value&256),
                            bitmap_only=bool(value&512),embedding_performed=False,
                            license_status='technical flags only; separate license not inferred')
    except (ValueError,struct.error): pass
    return dict(fs_type=None,embedding_performed=False,license_status='not determined; embedding disabled')


def _bundled_fonts():
    executable=shutil.which('soffice')
    if executable:
        p=Path(executable)
        if len(p.parents)>2:
            path=p.parents[2]/'native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype'
            if path.is_dir(): return path
    return Path('/Applications/LibreOffice.app/Contents/Resources/fonts/truetype')


@lru_cache(maxsize=128)
def installed_font(family: str,bold=False,italic=False):
    style='BoldItalic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular'
    mapped={'Arial':'LiberationSans','Arial Narrow':'LiberationSansNarrow','Times New Roman':'LiberationSerif','Courier New':'LiberationMono','Calibri':'Carlito'}
    bundled=_bundled_fonts()/(mapped.get(family,family.replace(' ',''))+'-'+style+'.ttf')
    if bundled.is_file():
        return str(bundled),'renderer bundled metric-compatible family'
    fc=shutil.which('fc-match')
    if fc:
        query=family+':style='+('Bold Italic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular')
        try:
            run=subprocess.run([fc,'-f','%{file}\n%{family}',query],capture_output=True,text=True,timeout=3)
            pieces=run.stdout.splitlines()
            if pieces and Path(pieces[0]).is_file(): return pieces[0],pieces[1] if len(pieces)>1 else 'fontconfig match'
        except (OSError,subprocess.TimeoutExpired): pass
    return None,'font availability unverified'


@lru_cache(maxsize=128)
def _metric_font(path):
    try: return pymupdf.Font(fontfile=path) if path else None
    except Exception: return None


class FontResolver:
    def __init__(self,use_metric_fallback=True):
        self.observations={};self.selections={};self.use_metric_fallback=use_metric_fallback

    @staticmethod
    def _key(span):return (span.font,span.bold,span.italic)

    @staticmethod
    def _exact_family(family,availability):
        normalize=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        return availability.startswith('renderer bundled') or normalize(family) in {
            normalize(s) for s in availability.split(',')}

    def _select(self,spans):
        first=spans[0];family,notice=word_font(first.font)
        path,availability=installed_font(family,first.bold,first.italic)
        exact=bool(path) and self._exact_family(family,availability)
        if exact:
            return dict(family=family,path=path,availability=availability,source_family_available=True,
                        method='installed family or explicit metric-compatible alias',score=None,samples=len(spans))
        if not self.use_metric_fallback:
            return dict(family=family,path=None,availability='requested family unavailable; renderer resolution unverified',
                        source_family_available=False,method='retain requested family without assuming substitute metrics',
                        score=None,samples=len(spans))
        # fc-match always returns something, even for a missing family. Measure
        # a consistent fallback across representative source lines and emit
        # exactly that font in Word, rather than measuring Verdana while asking
        # Word to resolve an unavailable proprietary name independently.
        candidates=[]
        measured=[s for s in spans if s.text.strip() and (s.advance_width or 0)>0][:100]
        if not measured:
            return dict(family=family,path=None,availability='no reliable source advance for fallback selection',
                        source_family_available=False,method='retain requested family without measured advance',score=None,samples=0)
        for candidate in ('Arial','Times New Roman','Calibri','Courier New','Georgia','Palatino'):
            candidate_path,actual=installed_font(candidate,first.bold,first.italic)
            if not candidate_path or not self._exact_family(candidate,actual):continue
            metric=_metric_font(candidate_path)
            if metric is None:continue
            total=sum(s.advance_width for s in measured)
            score=(sum(abs(metric.text_length(s.text.strip('\n\r'),fontsize=s.size)-s.advance_width)
                       for s in measured)/total) if total else 1.
            candidates.append((score,candidate,candidate_path,actual))
        if candidates:
            score,family,path,availability=min(candidates,key=lambda item:item[0])
        else:score=None;family='Arial';path=None;availability='font availability unverified'
        return dict(family=family,path=path,availability=availability,source_family_available=False,
                    method='minimum aggregate source advance error among installed fallback families',
                    score=score,samples=len(measured))

    def plan(self,model):
        samples=defaultdict(dict)
        for page in model.pages:
            for region in page.regions:
                for span in [*region.spans,*(s for cell in region.cells for s in cell.spans)]:
                    key=self._key(span)
                    if len(samples[key])<100:
                        samples[key][(span.text,span.size,span.advance_width)]=span
        for key,spans in samples.items():self.selections[key]=self._select(list(spans.values()))

    def resolve(self,span):
        key=self._key(span)
        if key not in self.selections:self.selections[key]=self._select([span])
        selected=self.selections[key]
        family,path,availability=(selected[k] for k in ('family','path','availability'))
        _,notice=word_font(span.font)
        if not selected['source_family_available']:
            notice=f'{span.font} → {family} (source family unavailable; '+('measured fallback' if path else 'renderer resolution unverified')+')'
        metric=_metric_font(path)
        text=span.text.strip('\n\r')
        target=span.advance_width or span.bbox.width
        natural=metric.text_length(text,fontsize=span.size) if metric and text else None
        relative=abs(natural-target)/max(target,1) if natural else None
        tracking=0.
        # Physical tracking only, bounded to 0.15pt/character and 1.5% em.
        # Large discrepancies are reported; never squeeze glyphs to improve SSIM.
        if natural and len(text)>1 and relative<.04:
            tracking=max(-min(.15,span.size*.015),min(min(.15,span.size*.015),(target-natural)/(len(text)-1)))
        observation_key=f'{span.font}|{span.bold}|{span.italic}'
        if observation_key not in self.observations:
            self.observations[observation_key]=dict(source=span.font,word_family=family,available=selected['source_family_available'],
                resolved_family_available=bool(path),selection_method=selected['method'],
                aggregate_width_error=selected['score'],selection_samples=selected['samples'],
                metric_file=path,availability=availability,relative_width_error=relative,
                applied_tracking_pt=tracking,embedding_performed=False,substitution=notice)
        return family,tracking,notice

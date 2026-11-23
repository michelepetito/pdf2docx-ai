import re


class QualityEnhancer:
    """Conservative review flags; no semantic rewriting or invented confidence."""
    def inspect(self,page) -> list[dict]:
        issues=[]
        text=[r for r in page.regions if r.text and r.kind!="table"]
        for r in text:
            reasons=[]
            if "\ufffd" in r.text: reasons.append("Carattere Unicode sostitutivo")
            if r.confidence is not None and r.confidence<.65: reasons.append("Confidenza OCR inferiore a 0.65")
            if re.search(r"\d[OIl]\d",r.text): reasons.append("Sequenza mista cifra/lettera da verificare")
            if not r.text.strip(): reasons.append("Testo potenzialmente mancante")
            for reason in reasons: issues.append(dict(page=page.number,region=r.id,reason=reason))
        for i,a in enumerate(text):
            for b in text[i+1:]:
                if a.bbox.coverage(b.bbox)>.65:
                    issues.append(dict(page=page.number,region=a.id,reason="Regioni testuali sovrapposte",other=b.id))
        for r in page.regions:
            if r.kind=="table" and (not r.cells or not r.rows or not r.cols):
                issues.append(dict(page=page.number,region=r.id,reason="Tabella priva di struttura completa"))
        return issues

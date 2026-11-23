import re


def word_font(pdf_font: str) -> tuple[str, str | None]:
    base=re.sub(r"^[A-Z]{6}\+", "", pdf_font)
    aliases={"helvetica":"Arial", "times":"Times New Roman", "courier":"Courier New",
             "dejavusans":"DejaVu Sans", "symbol":"Symbol", "zapfdingbats":"Wingdings"}
    key=re.sub(r"[-,_\s]", "", base.lower())
    for prefix,target in aliases.items():
        if key.startswith(prefix):
            return target, f"{pdf_font} → {target}" if base!=target else None
    # Word resolves absent fonts. We preserve the family and report that availability is unverified.
    return re.sub(r"[-,](BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular)$", "", base, flags=re.I), None

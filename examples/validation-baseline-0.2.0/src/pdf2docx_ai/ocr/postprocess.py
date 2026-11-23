"""Lossless structural handling of OTSL, without linguistic text correction.

OTSL token meanings are documented by Xiaomi-OCR-0 (Apache-2.0).
This implementation rejects malformed grids rather than silently padding them.
"""
from __future__ import annotations

import html
import re

_TOKEN = re.compile(r"<(fcel|ecel|lcel|ucel|xcel|nl)>")


def otsl_to_html(text: str) -> str:
    pieces = _TOKEN.split(text.strip())
    if len(pieces) == 1:
        raise ValueError("No OTSL cells")
    rows, row = [], []
    for index in range(1, len(pieces), 2):
        tag, content = pieces[index:index + 2]
        if tag == "nl":
            if row:
                rows.append(row)
                row = []
        else:
            row.append((tag, content))
    if row:
        rows.append(row)
    if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("Non-rectangular OTSL table; raw result retained")
    owners, cells = {}, {}
    for r, row in enumerate(rows):
        for c, (tag, content) in enumerate(row):
            if tag in {"fcel", "ecel"}:
                owner = (r, c)
                cells[owner] = {"text": content if tag == "fcel" else "", "rs": 1, "cs": 1}
            elif tag == "lcel":
                owner = owners.get((r, c - 1))
            elif tag == "ucel":
                owner = owners.get((r - 1, c))
            else:
                owner = owners.get((r - 1, c))
                if owner != owners.get((r, c - 1)):
                    raise ValueError("Inconsistent OTSL merged cell")
            if owner is None:
                raise ValueError("OTSL continuation without origin")
            owners[(r, c)] = owner
            cell = cells[owner]
            cell["rs"] = max(cell["rs"], r - owner[0] + 1)
            cell["cs"] = max(cell["cs"], c - owner[1] + 1)
    output = ["<table>"]
    for r, row in enumerate(rows):
        output.append("<tr>")
        for c in range(len(row)):
            if (r, c) not in cells:
                continue
            cell = cells[(r, c)]
            if any(owners.get((rr, cc)) != (r, c) for rr in range(r, r + cell["rs"])
                   for cc in range(c, c + cell["cs"])):
                raise ValueError("Non-rectangular OTSL merged cell")
            attrs = (f' rowspan="{cell["rs"]}"' if cell["rs"] > 1 else "")
            attrs += (f' colspan="{cell["cs"]}"' if cell["cs"] > 1 else "")
            output.append(f"<td{attrs}>{html.escape(cell['text'].strip())}</td>")
        output.append("</tr>")
    return "".join(output) + "</table>"


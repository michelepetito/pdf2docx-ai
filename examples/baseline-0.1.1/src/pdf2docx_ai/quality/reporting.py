from pathlib import Path
from html import escape
import base64
import json


def _img(path):
    p=Path(path)
    return "data:image/jpeg;base64,"+base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def write_report(report: dict,path: Path):
    e=lambda x:escape(str(x))
    summary=report.get("structural",{})
    visual=report.get("visual",{})
    cards="".join(f'<div class="metric"><strong>{e(v)}</strong><span>{e(k)}</span></div>' for k,v in [
        ("Pagine originali",report.get("pages",0)),("Caratteri modificabili",summary.get("editable_characters",0)),
        ("Tabelle Word",summary.get("native_word_tables",0)),("Secondi",round(report.get("performance",{}).get("total_seconds",0),2))])
    warnings="".join(f"<li>{e(w)}</li>" for w in report.get("warnings",[])) or "<li>Nessun avviso aggiuntivo.</li>"
    noneditable="".join(f'<li>Pagina {e(x.get("page"))}: {e(x.get("reason"))}</li>' for x in report.get("non_editable",[])) or "<li>Nessun elemento raster aggiuntivo segnalato.</li>"
    pages=""
    for p in visual.get("pages",[]):
        images="".join(f'<figure><img alt="{label} pagina {p["page"]}" src="{_img(p[key+"_path"])}"><figcaption>{label}</figcaption></figure>' for key,label in [("original","Originale"),("result","Risultato"),("overlay","Sovrapposizione"),("diff","Differenze")] if p.get(key+"_path"))
        pages+=f'<section><h2>Pagina {p["page"]}</h2><p>SSIM {p["ssim"]:.4f} · pixel cambiati {p["changed_pixel_fraction"]:.1%} · scostamento blocchi {e(p.get("mean_block_displacement_pt"))} pt</p><div class="comparison">{images}</div></section>'
    comparison=report.get("comparison")
    if comparison:
        pages+='<section><h2>Confronto motori</h2><p>Nessun vincitore assegnato senza ground truth. Le versioni restano separate.</p><pre>'+e(json.dumps(comparison,ensure_ascii=False,indent=2))+'</pre></section>'
    path.write_text('''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Rapporto PDF2DOCX AI Fidelity</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f1f4f6;color:#172b35;font:16px system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:40px 24px}h1{font-size:32px;margin-bottom:8px}h2{font-size:23px}p,li{line-height:1.65}section{background:white;border:1px solid #dce5e8;border-radius:12px;padding:24px;margin:22px 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.metric{padding:20px;background:#fff;border:1px solid #dce5e8;border-radius:10px}.metric strong{display:block;font-size:28px;color:#147970}.metric span{font-size:13px}.comparison{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}figure{margin:0}img{width:100%;border:1px solid #ddd}figcaption{padding:8px;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}small{color:#536670}@media(max-width:700px){.metrics,.comparison{grid-template-columns:1fr 1fr}main{padding:18px}}
    </style><main><small>ELABORAZIONE LOCALE · RAPPORTO MISURATO</small><h1>PDF2DOCX AI Fidelity</h1><p>'''+e(report.get("source",""))+" · modalità "+e(report.get("mode",""))+'''</p><div class="metrics">'''+cards+'''</div><section><h2>Avvisi e limiti</h2><ul>'''+warnings+'''</ul><p>Validazione visiva: '''+e(visual.get("status","not_requested"))+". "+e(visual.get("reason",""))+''' SSIM misura la somiglianza visiva e non la precisione OCR.</p></section><section><h2>Parti non modificabili</h2><ul>'''+noneditable+'''</ul></section>'''+pages+'''<section><h2>Metriche e provenienza</h2><pre>'''+e(json.dumps(report,ensure_ascii=False,indent=2))+'''</pre></section><small>Word ricalcola il layout. Font, renderer e motori OCR possono introdurre differenze.</small></main></html>''',encoding="utf-8")

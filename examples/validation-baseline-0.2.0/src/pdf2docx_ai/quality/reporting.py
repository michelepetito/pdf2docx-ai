from pathlib import Path
from html import escape
import base64
import json


def _img(path):
    p=Path(path)
    return "data:image/jpeg;base64,"+base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def _number(value,digits=3):
    return "non disponibile" if value is None else f"{value:.{digits}f}"


def _geometric_summary(visual):
    geometry=visual.get("geometry",{});foreground=visual.get("foreground",{});text=visual.get("textual",{})
    if not geometry: return ""
    e=lambda x:escape(str(x))
    coverage=geometry.get("match_coverage")
    return '<section><h2>Geometria e conservazione del testo</h2><p>Pagine originali / risultato: '+e(visual.get("original_pages","?"))+" / "+e(visual.get("rendered_pages","?"))+" · differenza "+e(visual.get("page_count_difference","?"))+'</p><p>Abbinamenti esatti di parole: '+e(geometry.get("matched_words",0))+" / "+e(geometry.get("source_words",0))+" · copertura "+(f"{coverage:.1%}" if coverage is not None else "non disponibile")+'''</p><div class="metric-grid">'''+"".join(
        f'<div><strong>{e(_number(value))}</strong><span>{e(label)}</span></div>' for label,value in [
        ("Errore mediano origine box pt",geometry.get("median_position_error_pt")),
        ("Errore P95 origine box pt",geometry.get("p95_position_error_pt")),
        ("Errore massimo origine box pt",geometry.get("max_position_error_pt")),
        ("Errore mediano baseline pt",geometry.get("median_baseline_error_pt")),
        ("IoU medio box",geometry.get("mean_iou")),("SSIM primo piano",foreground.get("foreground_ssim"))])+'''</div><p>Parole mancanti: '''+e(text.get("missing_words","non misurato"))+" · parole in eccesso: "+e(text.get("excess_words","non misurato"))+" · parole spostate di pagina: "+e(geometry.get("page_drift_words",0))+'''</p><p>CER '''+e(_number(text.get("cer")))+" · WER "+e(_number(text.get("wer")))+". Riferimento: "+e(text.get("reference","non disponibile"))+'''. Le metriche basate sul testo nativo non sostituiscono un ground truth OCR. Le origini dei box e le baseline sono misurate separatamente: ascendenti e font diversi modificano il box senza necessariamente spostare la linea.</p><p>Confronto senza riallineamento automatico. Gli abbinamenti di parole identiche ripetute possono essere ambigui; percentili e copertura vanno letti insieme.</p></section>'''


def _optimization(optimization,visual):
    if not optimization: return ""
    e=lambda x:escape(str(x))
    history=optimization.get("history",[])
    rows=""
    for item in history:
        rows+="<tr>"+"".join(f"<td>{e(value)}</td>" for value in [
            item.get("iteration",""),_number(item.get("objective")),item.get("accepted",False),
            _number(item.get("ssim"),5),_number(item.get("foreground_ssim"),5),
            _number(item.get("median_position_error_pt")),_number(item.get("p95_position_error_pt")),
            _number(item.get("median_baseline_error_pt")),item.get("page_count_difference",""),
            item.get("parameters_changed","")])+"</tr>"
    result='<section><h2>Ottimizzazione del layout</h2><p>Algoritmo: '+e(optimization.get("algorithm",""))+" · stato: "+e(optimization.get("status",""))+" · migliore iterazione: "+e(optimization.get("best_iteration",""))+'''</p><p>Arresto: '''+e(optimization.get("stop_reason",""))+" · renderer: "+e(optimization.get("renderer",visual.get("renderer","non registrato")))+'''</p><div class="table-scroll"><table><thead><tr><th>Iterazione</th><th>Obiettivo</th><th>Accettata</th><th>SSIM</th><th>SSIM primo piano</th><th>Mediana box pt</th><th>P95 box pt</th><th>Mediana baseline pt</th><th>Δ pagine</th><th>Parametri</th></tr></thead><tbody>'''+rows+'''</tbody></table></div><p>La soluzione migliore è conservata; il punteggio dell'obiettivo non rappresenta una percentuale di fedeltà.</p></section>'''
    before=optimization.get("before",{});after=optimization.get("after",visual)
    for initial,final in zip(before.get("pages",[]),after.get("pages",[])):
        if initial.get("result_path") and final.get("result_path"):
            result+=f'<section><h2>Prima e dopo pagina {e(initial["page"])}</h2><div class="comparison">'+"".join(
                f'<figure><img alt="{label}" src="{_img(item["result_path"])}"><figcaption>{label} · SSIM {_number(item.get("ssim"),5)}</figcaption></figure>'
                for label,item in (("Prima dell'ottimizzazione",initial),("Migliore soluzione",final)))+'</div></section>'
    return result


def _divergences(page):
    e=lambda x:escape(str(x))
    matches=sorted(page.get("line_matches",[]),key=lambda x:x.get("position_error_pt",0),reverse=True)[:25]
    if not matches: return '<p>Nessuna riga testuale abbinabile: lo scostamento geometrico non viene stimato.</p>'
    rows=""
    for match in matches:
        rows+="<tr>"+"".join(f"<td>{e(value)}</td>" for value in [
            match.get("text",""),str([round(v,2) for v in match["source_bbox"]]),
            str([round(v,2) for v in match["target_bbox"]]),_number(match.get("dx_pt")),
            _number(match.get("dy_pt")),_number(match.get("baseline_dy_pt")),_number(match.get("iou")),match.get("target_page","?")])+"</tr>"
    return '<details><summary>Coordinate delle righe più divergenti (punti PDF)</summary><div class="table-scroll"><table><thead><tr><th>Testo</th><th>Box sorgente</th><th>Box risultato</th><th>Δx</th><th>Δy box</th><th>Δ baseline</th><th>IoU</th><th>Pagina risultato</th></tr></thead><tbody>'+rows+'</tbody></table></div></details>'


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
        images="".join(f'<figure><img alt="{label} pagina {p["page"]}" src="{_img(p[key+"_path"])}"><figcaption>{label}</figcaption></figure>' for key,label in [("original","PDF originale"),("result","DOCX renderizzato in PDF"),("overlay","Sovrapposizione semitrasparente"),("heatmap","Heatmap differenze"),("diff","Differenze assolute"),("geometry","Box sorgente verde e risultato magenta")] if p.get(key+"_path"))
        warning='<p><strong>Pagina assente nel risultato.</strong></p>' if p.get("target_page_missing") else '<p><strong>Pagina aggiuntiva nel risultato.</strong></p>' if p.get("source_page_missing") else ''
        pages+=f'<section><h2>Pagina {p["page"]}</h2>'+warning+f'<p>SSIM {p["ssim"]:.4f} · pixel cambiati {p["changed_pixel_fraction"]:.1%} · mediana errore box {_number(p.get("geometry",{}).get("median_position_error_pt"))} pt · primo piano SSIM {_number(p.get("foreground",{}).get("foreground_ssim"))}</p><div class="comparison">{images}</div>'+_divergences(p)+'</section>'
    comparison=report.get("comparison")
    if comparison:
        pages+='<section><h2>Confronto motori</h2><p>Nessun vincitore assegnato senza ground truth. Le versioni restano separate.</p><pre>'+e(json.dumps(comparison,ensure_ascii=False,indent=2))+'</pre></section>'
    pages=_geometric_summary(visual)+_optimization(report.get("optimization",{}),visual)+pages
    path.write_text('''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Rapporto PDF2DOCX AI Fidelity</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f1f4f6;color:#172b35;font:16px system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:40px 24px}h1{font-size:32px;margin-bottom:8px}h2{font-size:23px}p,li{line-height:1.65}section{background:white;border:1px solid #dce5e8;border-radius:12px;padding:24px;margin:22px 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.metric{padding:20px;background:#fff;border:1px solid #dce5e8;border-radius:10px}.metric strong{display:block;font-size:28px;color:#147970}.metric span{font-size:13px}.comparison{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}figure{margin:0}img{width:100%;border:1px solid #ddd}figcaption{padding:8px;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}small{color:#536670}@media(max-width:700px){.metrics,.comparison{grid-template-columns:1fr 1fr}main{padding:18px}}
    .metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.metric-grid strong,.metric-grid span{display:block}.metric-grid span{font-size:12px;color:#536670}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:8px;border:1px solid #dce5e8;vertical-align:top}th{background:#edf4f3}details{margin-top:18px}summary{cursor:pointer;font-weight:600}
    </style><main><small>ELABORAZIONE LOCALE · RAPPORTO MISURATO</small><h1>PDF2DOCX AI Fidelity</h1><p>'''+e(report.get("source",""))+" · modalità "+e(report.get("mode",""))+'''</p><div class="metrics">'''+cards+'''</div><section><h2>Avvisi e limiti</h2><ul>'''+warnings+'''</ul><p>Validazione visiva: '''+e(visual.get("status","not_requested"))+". "+e(visual.get("reason",""))+" Renderer: "+e(visual.get("renderer","non registrato"))+''' SSIM misura la somiglianza visiva e non la precisione OCR.</p></section><section><h2>Parti non modificabili</h2><ul>'''+noneditable+'''</ul></section>'''+pages+'''<section><h2>Metriche e provenienza</h2><pre>'''+e(json.dumps(report,ensure_ascii=False,indent=2))+'''</pre></section><small>Word ricalcola il layout. Font, renderer e motori OCR possono introdurre differenze.</small></main></html>''',encoding="utf-8")

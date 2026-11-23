"""Reproducible local baseline/candidate evaluation and technical report.

No downloads or installations. Development is the default split; held-out
synthetic/public documents are evaluated only by an explicit split selection.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime,timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from pdf2docx_ai.quality.visual_diff import compare_pdfs
from pdf2docx_ai.quality.validator import find_renderer,render_docx_to_pdf

BASELINE=ROOT/"examples/baseline-0.1.1/src"
HISTORICAL=ROOT/"tmp/reconstruction-20261116"
DEFAULT_OUTPUT=ROOT/"examples/output/reconstruction-review"
REPORT_HTML=ROOT/"docs/reconstruction-final-report.html"
REPORT_MD=ROOT/"docs/reconstruction-final-report.md"


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024**2),b""): h.update(block)
    return h.hexdigest()


def code_digest(folder):
    h=hashlib.sha256()
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file() and path.suffix in (".py",".html",".css",".js",".swift") and "__pycache__" not in path.parts:
            h.update(str(path.relative_to(folder)).encode());h.update(b"\0");h.update(path.read_bytes());h.update(b"\0")
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temp,path)


def renderer_identity():
    executable=find_renderer()
    if not executable: raise RuntimeError('A real local renderer is required for this evaluation')
    version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=30)
    return {'path':str(executable),'wrapper_sha256':digest(executable),'version':(version.stdout+version.stderr).strip()}


def source_path(value,manifest):
    path=Path(value)
    if path.is_absolute() and path.is_file(): return path.resolve()
    candidate=Path(manifest).parent/(path.name if path.is_absolute() else path)
    if candidate.is_file(): return candidate.resolve()
    raise FileNotFoundError(candidate)


def documents(include_simple=False):
    docs=[]
    for manifest in (ROOT/"tests/fixtures/complex/generated/manifest.json",ROOT/"tests/fixtures/complex/public/manifest.json"):
        if not manifest.is_file(): continue
        data=read_json(manifest)
        for record in data["documents"]:
            item=dict(record)
            item["pdf"]=str(source_path(item.get("pdf",item.get("path")),manifest))
            item["group"]="holdout-public" if item.get("origin")=="real-public-publication" else item["split"]
            item["manifest"]=str(manifest)
            item["language"]="en" if item["group"]=="holdout-public" else "it"
            docs.append(item)
    if include_simple:
        for path in sorted((ROOT/"tests/fixtures/generated").glob("*.pdf")):
            docs.append(dict(id="simple_"+path.stem,pdf=str(path.resolve()),split="regression-simple",group="regression-simple",
                             language="en" if path.stem=="scan_en" else "it",features=["fixture di regressione semplice"],
                             ground_truth=str(path.with_suffix(".txt")) if path.with_suffix(".txt").is_file() else None))
    ids=[item["id"] for item in docs]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate document IDs")
    return docs


def selected(item,split,include_simple):
    if item["group"]=="regression-simple": return include_simple
    if split=="all": return True
    if split=="development": return item["group"]=="development"
    return item["group"] in ("holdout","holdout-public")


def rendered_path(report,docx):
    visual=report.get("visual",{})
    if visual.get("rendered_pdf_path") and Path(visual["rendered_pdf_path"]).is_file():
        return Path(visual["rendered_pdf_path"])
    legacy=Path(docx).with_suffix(".work")/"rendered"/(Path(docx).stem+".pdf")
    if legacy.is_file(): return legacy
    raise FileNotFoundError(f"Rendered PDF not found for {docx}")


def historical_baseline(item,source_sha):
    is_simple=item["group"]=="regression-simple"
    name=item["id"].removeprefix("simple_") if is_simple else item["id"]
    folder=HISTORICAL/("baseline-simple" if is_simple else "baseline-complex")
    quality=folder/(name+".quality.json");docx=folder/(name+".docx")
    if not quality.is_file() or not docx.is_file(): return None
    report=read_json(quality)
    if report.get("source_sha256")!=source_sha: return None
    try: pdf=rendered_path(report,docx)
    except FileNotFoundError: return None
    return dict(docx=str(docx),report=str(quality),rendered_pdf=str(pdf),
                provenance="preserved pre-revision output with matching source SHA-256",historical=True)


def convert_document(item,kind,folder,baseline_src,current_hash,args):
    folder.mkdir(parents=True,exist_ok=True)
    docx=folder/(item["id"]+".docx")
    quality=docx.with_suffix(".quality.json")
    provenance=docx.with_suffix(".evaluation.json")
    source_sha=digest(item["pdf"])
    source_code=baseline_src if kind=="before" else ROOT/"src"
    code_hash=code_digest(source_code)
    config=dict(engine="vision",mode="editable",language=item["language"],
                validate_visual=True,resume=False,max_layout_iterations=args.max_layout_iterations if kind=="after" else None,
                optimize_layout=not args.no_optimize_layout if kind=="after" else None,renderer=args.renderer_identity)
    expected=dict(source_sha256=source_sha,code_sha256=code_hash,configuration=config)
    if not args.force and quality.is_file() and provenance.is_file() and docx.is_file():
        previous=read_json(provenance)
        if all(previous.get(k)==v for k,v in expected.items()):
            report=read_json(quality)
            try:
                pdf=rendered_path(report,docx)
                return dict(docx=str(docx),report=str(quality),rendered_pdf=str(pdf),provenance="reused exact source/code/configuration",historical=False)
            except FileNotFoundError: pass
    env=dict(os.environ,PYTHONPATH=str(source_code))
    command=[sys.executable,"-m","pdf2docx_ai","convert",item["pdf"],"--output",str(docx),
             "--engine","vision","--mode","editable","--language",item["language"],
             "--validate-visual","--no-resume","--overwrite","--json"]
    truth=item.get("ground_truth")
    if truth and Path(truth).is_file(): command.extend(["--ground-truth",str(truth)])
    if kind=="after":
        command.extend(["--max-layout-iterations",str(args.max_layout_iterations)])
        if args.no_optimize_layout: command.append("--no-optimize-layout")
    start=time.perf_counter()
    completed=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=args.timeout)
    logs=folder/"logs";logs.mkdir(exist_ok=True)
    (logs/(item["id"]+".stdout.txt")).write_text(completed.stdout,encoding="utf-8")
    (logs/(item["id"]+".stderr.txt")).write_text(completed.stderr,encoding="utf-8")
    if completed.returncode: raise RuntimeError(f"{kind} {item['id']}: {completed.stderr[-1600:]} {completed.stdout[-800:]}")
    parsed=json.loads(completed.stdout)
    report=read_json(parsed["json_path"])
    if report.get("source_sha256")!=source_sha: raise RuntimeError("Conversion report refers to a different source PDF")
    if code_digest(source_code)!=code_hash: raise RuntimeError("Source code changed during conversion; rerun after freezing the revision")
    expected.update(command=command,wall_seconds=time.perf_counter()-start,completed_utc=datetime.now(timezone.utc).isoformat())
    write_json(provenance,expected)
    return dict(docx=str(docx),report=parsed["json_path"],rendered_pdf=str(rendered_path(report,docx)),provenance="executed in isolated source PYTHONPATH",historical=False)


def one_document(item,args,output,current_hash,baseline_hash):
    source_sha=digest(item["pdf"])
    old=None if args.force_baseline else historical_baseline(item,source_sha)
    if old is None: old=convert_document(item,"before",output/"before",args.baseline_source,current_hash,args)
    new=convert_document(item,"after",output/"after"/current_hash[:12],args.baseline_source,current_hash,args)
    before_report=read_json(old["report"]);after_report=read_json(new["report"])
    # Re-render both DOCX with the same CURRENT executable, even when a
    # matching-source historical DOCX is reused from the preserved baseline.
    for kind,artifact in (("before",old),("after",new)):
        rendered=render_docx_to_pdf(Path(artifact['docx']),output/'rendered-pairs'/kind/item['id'],args.renderer_identity['path'])
        if rendered['status']!='rendered': raise RuntimeError(f'{kind} renderer failed: {rendered}')
        artifact['rendered_pdf']=rendered['pdf_path'];artifact['renderer']=args.renderer_identity
    assets=output/"comparisons"/item["id"]
    before=compare_pdfs(Path(item["pdf"]),Path(old["rendered_pdf"]),assets/"before")
    after=compare_pdfs(Path(item["pdf"]),Path(new["rendered_pdf"]),assets/"after")
    old.update(measurement=before,performance=before_report.get("performance",{}),structural=before_report.get("structural",{}),
               non_editable=before_report.get("non_editable",[]),warnings=before_report.get("warnings",[]),code_sha256=baseline_hash,
               ground_truth_accuracy=before_report.get("text_accuracy"),version=before_report.get("version"))
    new.update(measurement=after,performance=after_report.get("performance",{}),structural=after_report.get("structural",{}),
               non_editable=after_report.get("non_editable",[]),warnings=after_report.get("warnings",[]),code_sha256=current_hash,
               ground_truth_accuracy=after_report.get("text_accuracy"),optimization=after_report.get("optimization",{}),version=after_report.get("version"))
    return dict(id=item["id"],group=item["group"],source=dict(item,actual_sha256=source_sha),
                status="measured",completed_utc=datetime.now(timezone.utc).isoformat(),before=old,after=new,
                delta=dict(ssim=after["mean_ssim"]-before["mean_ssim"],
                           median_position_error_pt=_delta(after["geometry"].get("median_position_error_pt"),before["geometry"].get("median_position_error_pt")),
                           p95_position_error_pt=_delta(after["geometry"].get("p95_position_error_pt"),before["geometry"].get("p95_position_error_pt"))))


def _delta(after,before):
    return None if after is None or before is None else after-before


def fmt(value,digits=3):
    return "n.d." if value is None else f"{value:.{digits}f}"


def image_uri(path):
    file=Path(path)
    return "data:image/jpeg;base64,"+base64.b64encode(file.read_bytes()).decode() if file.is_file() else ""


def href(path,parent):
    return escape(os.path.relpath(Path(path),Path(parent)),quote=True)


def metrics_row(row):
    b,a=row["before"],row["after"];bm,am=b["measurement"],a["measurement"]
    bg,ag=bm["geometry"],am["geometry"];bt,at=bm["textual"],am["textual"]
    return [row["id"],row["group"],f'{bm["original_pages"]}/{bm["rendered_pages"]} → {am["original_pages"]}/{am["rendered_pages"]}',
            fmt(bm["mean_ssim"],5)+" → "+fmt(am["mean_ssim"],5),
            fmt(bm["foreground"]["foreground_ssim"],5)+" → "+fmt(am["foreground"]["foreground_ssim"],5),
            fmt(bg.get("median_position_error_pt"))+" → "+fmt(ag.get("median_position_error_pt")),
            fmt(bg.get("p95_position_error_pt"))+" → "+fmt(ag.get("p95_position_error_pt")),
            fmt(bg.get("median_baseline_error_pt"))+" → "+fmt(ag.get("median_baseline_error_pt")),
            fmt(bt.get("cer"),5)+" → "+fmt(at.get("cer"),5),fmt(bt.get("wer"),5)+" → "+fmt(at.get("wer"),5),
            f'{at.get("missing_characters",0)}/{at.get("excess_characters",0)}',
            f'{ag["matched_words"]}/{ag["source_words"]}',
            f'{b["structural"].get("native_word_tables","?")} → {a["structural"].get("native_word_tables","?")}',
            f'{b["structural"].get("picture_count","?")} → {a["structural"].get("picture_count","?")}',
            f'{a["structural"].get("text_box_count","?")}/{a["structural"].get("additional_word_tables","?")}',
            fmt(b["performance"].get("total_seconds"))+" → "+fmt(a["performance"].get("total_seconds"))]


HEADERS=["Documento","Gruppo","Pagine sorgente/risultato","SSIM prima → dopo","SSIM primo piano","Mediana box pt","P95 box pt","Mediana baseline pt","CER","WER","Caratteri mancanti/eccesso dopo","Parole associate","Tabelle Word","Immagini Word","Textbox/tabelle aggiuntive dopo","Secondi prima → dopo"]


def table_html(rows,headers=HEADERS):
    return '<div class="table-scroll"><table><thead><tr>'+"".join('<th>'+escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+"".join(
        '<tr>'+"".join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def figures(row,all_pages=True):
    before=row["before"]["measurement"]["pages"];after=row["after"]["measurement"]["pages"]
    result=""
    for index in range(max(len(before),len(after)) if all_pages else min(1,max(len(before),len(after)))):
        b=before[index] if index<len(before) else {};a=after[index] if index<len(after) else {}
        result+=f'<h3>Pagina {index+1}</h3><div class="figures">'
        for label,item,key in (("PDF originale",b,"original_path"),("Prima della revisione",b,"result_path"),("Dopo la revisione",a,"result_path")):
            if item.get(key): result+=f'<figure><img alt="{escape(label)} pagina {index+1}" src="{image_uri(item[key])}"><figcaption>{escape(label)}</figcaption></figure>'
            else: result+=f'<figure><p>Pagina non disponibile</p><figcaption>{escape(label)}</figcaption></figure>'
        result+='</div>'
        if all_pages:
            result+='<details><summary>Overlay e heatmap dopo la revisione</summary><div class="figures">'
            for key,label in (("overlay_path","Overlay originale/risultato"),("heatmap_path","Heatmap"),("geometry_path","Box sorgente e risultato")):
                if a.get(key): result+=f'<figure><img alt="{label}" src="{image_uri(a[key])}"><figcaption>{label}</figcaption></figure>'
            result+='</div></details>'
    return result


CSS='''*{box-sizing:border-box}body{font:15px/1.6 system-ui,sans-serif;background:#f2f5f6;color:#19323a;margin:0}main{max-width:1480px;margin:auto;padding:36px 24px}h1{font-size:34px;line-height:1.15}h2{font-size:25px;margin-top:0}h3{font-size:19px}section{padding:24px;background:white;border:1px solid #d8e2e5;border-radius:10px;margin:22px 0}a{color:#126d67}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:8px;border:1px solid #d8e2e5;text-align:left;vertical-align:top}th{background:#eaf1f1}td{font-variant-numeric:tabular-nums}.figures{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}figure{margin:0}figure img{width:100%;border:1px solid #d8e2e5}figcaption{font-size:12px;font-weight:600;padding:7px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}code{overflow-wrap:anywhere}details{margin:16px 0}summary{cursor:pointer;font-weight:600}.notice{background:#fff5df;padding:14px;border-left:4px solid #bf8824}.small{font-size:12px;color:#526970}@media(max-width:800px){.figures{grid-template-columns:1fr}main{padding:18px}section{padding:18px}}'''


def page(title,body):
    return '<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+escape(title)+'</title><style>'+CSS+'</style><main><h1>'+escape(title)+'</h1>'+body+'</main></html>'


def document_report(row,output):
    destination=output/"documents"/(row["id"]+".comparison.html");destination.parent.mkdir(parents=True,exist_ok=True)
    body='<p>Confronto locale con lo stesso PDF sorgente e le stesse metriche, senza riallineamento.</p><section>'+table_html([metrics_row(row)])+'</section>'
    body+='<section><h2>Anteprime prima e dopo</h2>'+figures(row)+'</section>'
    optimization=row["after"].get("optimization",{})
    if optimization:
        body+='<section><h2>Evoluzione della soluzione corrente</h2><p>Stato '+escape(str(optimization.get("status")))+' · migliore iterazione '+escape(str(optimization.get("best_iteration")))+' · arresto '+escape(str(optimization.get("stop_reason")))+'</p>'
        history=optimization.get("history",[])
        body+=table_html([[h.get('iteration'),'iniziale' if h.get('iteration')==0 else h.get('kind','geometry'),fmt(h.get('objective')),h.get('accepted'),fmt(h.get('ssim'),5),fmt(h.get('foreground_ssim'),5),fmt(h.get('median_position_error_pt')),fmt(h.get('p95_position_error_pt')),h.get('parameters_changed')] for h in history],
                         ['Iterazione','Tipo','Obiettivo','Accettata','SSIM','SSIM primo piano','Mediana box pt','P95 box pt','Parametri cambiati'])+'<p>Politica font finale: '+escape(optimization.get('font_policy','non registrata'))+'</p></section>'
    body+='<section><h2>Modificabilità e parti non editabili</h2><pre>'+escape(json.dumps({'prima':row['before']['structural'],'dopo':row['after']['structural'],'non_editable':row['after']['non_editable']},ensure_ascii=False,indent=2))+'</pre></section>'
    body+='<section><h2>Provenienza</h2><pre>'+escape(json.dumps({k:row[k] for k in ('source','completed_utc')},ensure_ascii=False,indent=2))+'</pre><p>Codice precedente '+escape(row['before']['code_sha256'])+'<br>Codice corrente '+escape(row['after']['code_sha256'])+'</p></section>'
    destination.write_text(page('Confronto '+row['id'],body),encoding='utf-8')
    return destination


def validation_notes(measured,output):
    """Report first independent observations as well as later bug fixes."""
    parts=[]
    archive=output/'first-heldout-attempt'
    first=[read_json(p) for p in sorted(archive.glob('*.json'))] if archive.is_dir() else []
    if first:
        rows=[]
        for r in first:
            if r.get('status')=='measured':
                m=r['after']['measurement']
                rows.append([r['id'],f"{m['original_pages']}/{m['rendered_pages']}",fmt(m['mean_ssim'],5),fmt(m['geometry'].get('median_position_error_pt')),'misurato'])
            else:rows.append([r['id'],'n.d.','n.d.','n.d.',r.get('error','errore')])
        parts.append('<section><h2>Prima validazione indipendente e correzioni successive</h2><p>I cinque documenti indipendenti non hanno guidato la taratura iniziale. La prima prova ha rilevato pagine aggiuntive nella newsletter, un JPEG Adobe non riconosciuto e un costo quadratico nella generazione di migliaia di forme. Gli esiti originali sono conservati separatamente. Sono seguite correzioni generali di raggruppamento header/footer, compatibilità immagine e allocazione degli identificatori. Le misure correnti su questi casi sono quindi una rivalidazione dopo diagnosi, non una nuova prova cieca. Non sono stati scelti coefficienti specifici per documento.</p>'+table_html(rows,['Documento','Pagine sorgente/risultato iniziale','SSIM iniziale','Mediana box iniziale pt','Esito iniziale'])+'<p>Archivio numerico e visivo: <code>'+escape(str(archive.relative_to(ROOT)))+'</code>.</p></section>')
    regressions=[]
    for r in measured:
        b,a=r['before']['measurement'],r['after']['measurement']
        if a['mean_ssim']<.98 or a['page_count_difference'] or (a['geometry'].get('median_position_error_pt') or 0)>2:
            regressions.append([r['id'],fmt(a['mean_ssim'],5),f"{a['original_pages']}/{a['rendered_pages']}",fmt(a['geometry'].get('median_position_error_pt')),fmt(a['geometry'].get('p95_position_error_pt'))])
    if regressions:
        parts.append('<section><h2>Obiettivi non raggiunti</h2><p>Questi casi non soddisfano almeno una soglia progettuale: SSIM≥0,98, mediana dei box≤2pt, parità di pagine. La differenza di ascendente dei font può influire sui box anche con baseline corrette; per questo sono disponibili entrambe le misure. I casi elencati richiedono ulteriore lavoro. Bordi delle tabelle sono ancora uniformati e possono ridurre SSIM anche quando le parole coincidono.</p>'+table_html(regressions,['Documento','SSIM corrente','Pagine sorgente/risultato','Mediana box pt','P95 box pt'])+'</section>')
    parts.append('<section><h2>Interpretazione del testo e collaudo applicativo</h2><p>Nella fixture a colonne l’ordine interno di scrittura PDF alterna sinistra/destra; entrambi i DOCX seguono le colonne e conservano i conteggi, pur avendo CER/WER di sequenza non nulli. La formula con apice può essere estratta dal renderer come due token pur conservando i caratteri. Il testo OCR aggiunto nelle immagini miste non è testo in eccesso rispetto a un ground truth OCR: l’estrazione nativa del PDF non lo contiene. Le scansioni sono valutate anche con i riferimenti testuali separati.</p><p>La suite completa comprende OCR Vision e MiniCPM reali e i test complessi. Il file JUnit <code>docs/reconstruction-test-results.xml</code> riporta l’esito esatto dell’ultima esecuzione. Una conversione MiniCPM è stata inviata anche all’API della GUI locale, verificando completamento, DOCX e download dei rapporti, con CER/WER zero sulla breve scansione italiana. L’upload tramite controllo grafico del browser non è stato completato: collegamento debugger e finestra nativa non disponibili. Microsoft Word non è stato verificato come renderer; queste misure usano LibreOffice incluso.</p></section>')
    font_rows=[]
    for row in measured:
        if row['group']!='holdout-public':continue
        detail=read_json(row['after']['report'])
        for font in detail.get('font_matching',[]):
            if not font.get('available'):
                font_rows.append([row['id'],font['source'],font['word_family'],font.get('selection_method'),fmt(font.get('aggregate_width_error')),font.get('selection_samples')])
    if font_rows:
        parts.append('<section><h2>Font assenti nelle pubblicazioni reali</h2><p>La diagnosi ha rilevato un fallback di fontconfig misurato senza imporre la stessa famiglia in Word. Ora le alternative metriche emettono proprio il font misurato, ma la larghezza da sola non decide: il renderer deve confermare il miglioramento. La prova dei font viene respinta se peggiora SSIM globale o primo piano. Nei due documenti pubblici la scelta finale resta requested: il nome sorgente è conservato e non si applica tracking basato su una famiglia diversa. La sostituzione non viene dichiarata riuscita. Anche questa correzione segue la diagnosi sul corpus e non costituisce una nuova prova cieca.</p>'+table_html(font_rows,['Documento','Font PDF non disponibile','Famiglia Word corrente','Metodo corrente','Errore aggregato disponibile','Campioni'])+'</section>')
    junit=ROOT/'docs/reconstruction-test-results.xml'
    if junit.is_file():
        suites=list(ET.parse(junit).getroot().iter('testsuite'))
        totals={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
        parts.append('<section><h2>Esito della suite completa</h2>'+table_html([[totals[k] for k in ('tests','failures','errors','skipped')]],['Test','Fallimenti','Errori','Saltati'])+'<p>Comprende corpus complesso, Vision e MiniCPM reali; provenienza esatta nel JUnit. Le misure di layout su un documento non sono sostituite dal solo passaggio dei test.</p></section>')
    parts.append('<section><h2>Divergenze residue osservate</h2><p>Le due pubblicazioni reali restano sotto la baseline SSIM e generano pagine aggiuntive: non sono casi superati. I font proprietari mancanti, il wrapping e la distribuzione dei blocchi compromettono il flusso; gli header/footer ripetuti sulle pagine aggiunte producono testo in eccesso nel PDF renderizzato. Le primitive curve/oblique omesse e i limiti di tempo restano segnalati nei rapporti. L’esito favorevole dei documenti sintetici non dimostra generalizzazione a questi impaginati.</p><p>La fattura conserva testo e geometria, ma i bordi uniformati delle celle riducono SSIM. Il testo ruotato viene ricostruito a flusso orizzontale: il contenuto è leggibile, mentre la posizione rispetto alla sorgente resta divergente. Nel rendiconto tabulato e nelle colonne l’ordine interno di serializzazione PDF può differire dal flusso Word, con CER/WER non nulli pur conservando caratteri e valori.</p><p>Per i testi lunghi delle pubblicazioni, CER/WER esatti risultano non disponibili per il limite computazionale dichiarato della distanza; i conteggi di caratteri, parole, numeri e associazioni restano riportati. Non sono zeri presunti. Tutte le misure usano LibreOffice; Microsoft Word non è stato verificato.</p></section>')
    return ''.join(parts)


def render_final_report(all_docs,results,output,run_metadata):
    measured=[r for r in results if r.get('status')=='measured'];failures=[r for r in results if r.get('status')!='measured']
    hashes=sorted({r['after']['code_sha256'] for r in measured})
    pending=[d for d in all_docs if d['id'] not in {r['id'] for r in results}]
    groups=Counter(r['group'] for r in measured)
    rows=[metrics_row(r) for r in measured]
    body='<p>Collaudo locale della revisione del motore geometrico. Nessuna fedeltà del100% viene dichiarata. Documento generato dalle misure effettivamente registrate.</p>'
    if len(hashes)>1: body+='<p class="notice">I risultati contengono più versioni del codice corrente. Non costituiscono un unico benchmark congelato; rigenerare i casi con la stessa revisione prima di aggregare.</p>'
    body+='<section><h2>A Problemi individuati</h2><p>La versione iniziale perdeva baseline e metriche di riga, sommava spaziature usando box tipografici come altezze di flusso, imponeva margini e gap di colonna semplificati e trattava immagini indipendenti come elementi inline. I blocchi con tabulazioni, le righe con font diversi e le tabelle multipagina amplificavano gli scostamenti. Il precedente matching dei soli blocchi e SSIM dominato dal bianco non descrivevano questi errori adeguatamente.</p></section>'
    body+='<section><h2>B Soluzioni implementate</h2><p>Il motore corrente usa geometria di righe e baseline, margini e sezioni, rientri e tabulazioni native, interlinea derivata dalle metriche del font, colonne native e immagini ancorate autonome. Le tabelle Word rappresentano le vere tabelle individuate. Una ricerca locale vincolata genera DOCX, li rende con LibreOffice e conserva soltanto miglioramenti ammissibili, verificando invarianti di contenuto e pagine. I parametri e le decisioni effettivamente usati per ogni file sono nelle rispettive storie di ottimizzazione.</p><p>La validazione usa parole uno-a-uno e distingue posizione dei box, baseline, dimensioni, IoU, copertura, testo e immagini. Nessun allineamento raster nasconde gli scostamenti. CER/WER del testo nativo sono separati dal riferimento ground truth OCR.</p></section>'
    body+='<section><h2>C Risultati comparativi</h2><p>Documenti misurati: '+str(len(measured))+' · falliti: '+str(len(failures))+' · non ancora eseguiti: '+str(len(pending))+'. Development e holdout restano distinti.</p>'
    body+=table_html([[g,groups[g]] for g in ('development','holdout','holdout-public','regression-simple')],['Gruppo','Documenti effettivamente misurati'])+table_html(rows)
    body+='<p>Mediana e P95 sono sulle parole esattamente associate della medesima pagina; leggere insieme la copertura. CER/WER confrontano estrazioni native dei PDF e non rappresentano accuratezza OCR senza un riferimento testuale separato. I tempi comprendono rendering/validazione, ma le condizioni di cache del sistema e warm-up non sono controllate come in uno studio prestazionale.</p></section>'
    if pending: body+='<section><h2>Documenti non ancora valutati</h2>'+table_html([[d['id'],d['group']] for d in pending],['Documento','Gruppo'])+'<p>Questi casi non sono presentati come superati.</p></section>'
    if failures: body+='<section><h2>Errori effettivi del collaudo</h2><pre>'+escape(json.dumps(failures,ensure_ascii=False,indent=2))+'</pre></section>'
    cv=next((r for r in measured if r['id']=='europass_fictitious'),None)
    body+='<section><h2>D Curriculum europeo complesso</h2>'
    if cv:
        body+='<p>CV realistico interamente fittizio di due pagine, con ritratto sintetico, sezioni, date allineate, rientri, elenchi, intestazioni e una tabella linguistica autentica. Il DOCX di riferimento è distinto dall’output del convertitore. Il riferimento non usa tabelle invisibili né caselle di testo per il layout.</p>'+table_html([metrics_row(cv)])+figures(cv)
        body+='<p>La misura geometrica separa il miglioramento delle posizioni dal semplice mantenimento del testo; la struttura OOXML resta verificabile nel rapporto dettagliato.</p>'
    else: body+='<p>CV non ancora misurato in questa esecuzione: nessun risultato viene presunto.</p>'
    body+='</section><section><h2>E Limiti residui</h2><p><strong>Software correggibile:</strong> inferenza di paragrafi e ordine di lettura rimane euristica; tabelle senza bordi e geometrie editoriali molto intrecciate possono essere interpretate male. Le divergenze effettive di ogni documento restano visibili nei report, compresi percentili estremi e parole mancanti.</p><p><strong>Font:</strong> nome, metriche e sostituzioni dipendono dai font disponibili; box tipografici diversi non implicano sempre una baseline diversa. Non si redistribuiscono font incorporati senza verificarne i diritti.</p><p><strong>Word:</strong> la ricostruzione usa un flusso ricalcolabile. Float, tabelle spezzate, campi e sezioni continue possono variare dopo modifiche nel Word destinatario.</p><p><strong>Renderer:</strong> queste misure usano LibreOffice locale, non Microsoft Word. Differenze di font, antialiasing e motore di impaginazione non sono attribuite automaticamente all’algoritmo. Le soglie SSIM≥0,98 e mediana≤2pt sono obiettivi e non garanzie. Per documenti scannerizzati senza testo nativo CER/WER dal PDF sono indisponibili: si usa l’eventuale ground truth separato.</p></section>'
    body+='<section><h2>F Prossimi miglioramenti non implementati</h2><p>Priorità: validazione incrociata con Microsoft Word reale; espansione del gruppo indipendente con nuove licenze verificate; risoluzione dei casi ancora divergenti di lettura e tabelle; calibrazione dei font non presenti sul destinatario. Nessuno di questi interventi viene presentato come completato dal benchmark.</p></section>'
    body+=validation_notes(measured,output)
    links=[]
    for r in measured:
        report=document_report(r,output);links.append((r['id'],report))
    body+='<section><h2>Rapporti completi e provenienza</h2><ul>'+''.join(f'<li><a href="{href(path,REPORT_HTML.parent)}">{escape(name)}</a></li>' for name,path in links)+'</ul><pre>'+escape(json.dumps(run_metadata,ensure_ascii=False,indent=2))+'</pre><p>Hash del codice corrente nei risultati: '+escape(', '.join(hashes))+'</p></section>'
    public=[d for d in all_docs if d['group']=='holdout-public']
    if public: body+='<section><h2>Fonti pubbliche e attribuzioni</h2>'+''.join('<p>'+escape(d.get('attribution',d['id']))+' — riferimenti e licenza nel manifest pubblico.</p>' for d in public)+'</section>'
    REPORT_HTML.write_text(page('Revisione del motore di ricostruzione PDF2DOCX',body),encoding='utf-8')
    md=['# Revisione del motore di ricostruzione PDF2DOCX','',f'Documenti misurati: {len(measured)}. Errori: {len(failures)}. Non eseguiti: {len(pending)}.','',
        'La versione HTML autonoma contiene le immagini comparative del curriculum europeo e i collegamenti ai report completi. Nessuna fedeltà del100% viene dichiarata.','',
        '## A Problemi individuati','', 'Perdita di baseline e metriche; spaziature ricavate da box tipografici; gap/margini semplificati; immagini inline; metriche dominate dal bianco e pochi blocchi associati.','',
        '## B Soluzioni implementate','', 'Geometria di righe e baseline, struttura Word nativa, tabulazioni/rientri/colonne, immagini ancorate, tabelle autentiche, ottimizzazione vincolata con renderer e invarianti. Le storie registrate documentano i parametri realmente corretti.','',
        '## C Risultati comparativi','', '| '+' | '.join(HEADERS)+' |','| '+' | '.join(['---']*len(HEADERS))+' |']
    md.extend('| '+' | '.join(str(v).replace('|','\\|') for v in row)+' |' for row in rows)
    md.extend(['','CER/WER sono misure sul testo nativo renderizzato, non ground truth OCR. Le geometrie considerano associazioni esatte e copertura. I gruppi sono distinti: '+str(dict(groups))+'.','',
               '## D Curriculum europeo','', 'Il CV contiene dati interamente fittizi, un ritratto sintetico e almeno due pagine. Vedere le immagini prima/dopo e il rapporto dedicato nella versione HTML.' if cv else 'CV non ancora misurato.','',
               '## E Limiti residui','', 'Software: inferenze euristiche e casi editoriali complessi. Font: sostituzioni e metriche. Word: flusso ricalcolabile. Renderer: verificato LibreOffice, non Microsoft Word. Soglie desiderate non garantite.','',
               '## F Prossimi miglioramenti non implementati','', 'Validazione Microsoft Word; più campioni indipendenti; risoluzione delle divergenze residue di lettura/tabelle; calibrazione di font assenti.','',
               '## Provenienza','', '```json',json.dumps(run_metadata,ensure_ascii=False,indent=2),'```',''])
    if pending: md.extend(['Documenti non ancora eseguiti: '+', '.join(d['id'] for d in pending)+'.',''])
    if len(hashes)>1: md.extend(['ATTENZIONE: più hash del codice corrente. Non aggregare come unico benchmark congelato.',''])
    if (output/'first-heldout-attempt').is_dir():md.extend(['La prima validazione indipendente è conservata in `examples/output/reconstruction-review/first-heldout-attempt`. Dopo quella prova sono stati corretti bug generali di raggruppamento header/footer, compatibilità JPEG Adobe e costo quadratico delle forme. I risultati correnti su questi documenti sono una rivalidazione, non un nuovo holdout cieco.',''])
    md.extend(['Il file JUnit `docs/reconstruction-test-results.xml` registra i test completi. GUI: API locale con conversione MiniCPM reale e download verificati; controllo grafico dell’upload non completato per indisponibilità del collegamento browser. Microsoft Word non verificato come renderer.',''])
    REPORT_MD.write_text('\n'.join(md),encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=['development','holdout','all'],default='development')
    parser.add_argument('--simple',action='store_true',help='Include the fourteen existing simple regression fixtures')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--baseline-source',type=Path,default=BASELINE)
    parser.add_argument('--max-layout-iterations',type=int,default=3)
    parser.add_argument('--no-optimize-layout',action='store_true')
    parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--force',action='store_true',help='Rerun candidate and locally generated baseline artifacts')
    parser.add_argument('--force-baseline',action='store_true',help='Do not reuse preserved matching-source baseline outputs')
    parser.add_argument('--list',action='store_true',help='Print the fixed selection without converting any document')
    parser.add_argument('--report-only',action='store_true',help='Regenerate reports from recorded results only')
    args=parser.parse_args(argv)
    if not 0<=args.max_layout_iterations<=12: parser.error('iterations must be between0 and12')
    args.baseline_source=args.baseline_source.resolve();args.output=args.output.resolve()
    all_docs=documents(args.simple);chosen=[d for d in all_docs if selected(d,args.split,args.simple)]
    if args.list:
        print(json.dumps([{'id':d['id'],'group':d['group'],'pdf':d['pdf']} for d in chosen],ensure_ascii=False,indent=2));return 0
    if not args.baseline_source.is_dir(): raise FileNotFoundError('Baseline source snapshot is required: '+str(args.baseline_source))
    current_hash=code_digest(ROOT/'src');baseline_hash=code_digest(args.baseline_source)
    args.renderer_identity=renderer_identity()
    metadata=dict(completed_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,platform=platform.platform(),
                  command=sys.argv,split=args.split,include_simple=args.simple,configuration={'max_layout_iterations':args.max_layout_iterations,'optimize_layout':not args.no_optimize_layout},
                  baseline_source=str(args.baseline_source),baseline_code_sha256=baseline_hash,current_code_sha256=current_hash,
                  harness_sha256=digest(__file__),metrics='same current compare_pdfs for both rendered PDFs;100dpi;no registration')
    metadata['renderer']=args.renderer_identity
    result_dir=args.output/'results';result_dir.mkdir(parents=True,exist_ok=True)
    errors=0
    if not args.report_only:
        for index,item in enumerate(chosen,1):
            print(f'[{index}/{len(chosen)}] {item["group"]}: {item["id"]}',flush=True)
            try:
                row=one_document(item,args,args.output,current_hash,baseline_hash)
                print(f'  SSIM {row["before"]["measurement"]["mean_ssim"]:.5f} -> {row["after"]["measurement"]["mean_ssim"]:.5f}; median pt {row["before"]["measurement"]["geometry"]["median_position_error_pt"]} -> {row["after"]["measurement"]["geometry"]["median_position_error_pt"]}',flush=True)
            except Exception as exc:
                row=dict(id=item['id'],group=item['group'],status='failed',error=str(exc),source=item,completed_utc=datetime.now(timezone.utc).isoformat());errors+=1
                print('  FAILED '+str(exc),flush=True)
            write_json(result_dir/(item['id']+'.json'),row)
    results=[read_json(p) for p in sorted(result_dir.glob('*.json'))]
    write_json(args.output/'evaluation.json',{'run':metadata,'results':results})
    render_final_report(all_docs,results,args.output,metadata)
    print('Report:',REPORT_HTML,flush=True)
    return 1 if errors else 0


if __name__=='__main__':
    sys.exit(main())

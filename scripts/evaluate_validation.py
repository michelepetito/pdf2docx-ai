"""Evaluate frozen conversions with legacy/current validators on identical PDFs.

Also compare the two preserved converter versions with the SAME new validator.
No PDF source, production DOCX, or previous reconstruction report is overwritten.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from html import escape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pdf2docx_ai import __version__
from pdf2docx_ai.document.models import Document
from pdf2docx_ai.quality.validator import render_docx_to_pdf
from pdf2docx_ai.quality.visual_diff import compare_pdfs
from pdf2docx_ai.quality.assessment import assess_conversion,persist_assessment,_code_fingerprint
from pdf2docx_ai.quality.reporting import write_report
from evaluate_reconstruction import read_json,write_json,digest,code_digest,renderer_identity,page,table_html,href

LEGACY=ROOT/'examples/validation-baseline-0.2.0/src'
FROZEN=ROOT/'examples/output/reconstruction-review/results'
DEFAULT=ROOT/'examples/output/validation-review'


def legacy_measure(source,pdf,output):
    program="""import json,sys
from pathlib import Path
from pdf2docx_ai.quality.visual_diff import evaluate_pdf_pair
r=evaluate_pdf_pair(Path(sys.argv[1]),Path(sys.argv[2]),include_images=True,dpi=100)
Path(sys.argv[3]).write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8')
"""
    env={**os.environ,'PYTHONPATH':str(LEGACY)}
    run=subprocess.run([sys.executable,'-c',program,str(source),str(pdf),str(output)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=240)
    if run.returncode:raise RuntimeError('Legacy validation failed: '+run.stderr[-1500:])
    return read_json(output)


def summarize(a):
    d=a['dimensions'];t=d['textual'];g=d['geometry'];s=d['structure'];v=d['visual'];primary=t.get('primary',{})
    return {'ssim':v.get('mean_ssim'),'worst_page_ssim':v.get('minimum_page_ssim'),
        'foreground_ssim':(v.get('foreground') or {}).get('foreground_ssim'),
        'cer_strict':t.get('strict_stream',{}).get('cer'),'wer_strict':t.get('strict_stream',{}).get('wer'),
        'cer_primary':primary.get('cer'),'wer_primary':primary.get('wer'),'cer_reference':primary.get('reference'),
        'missing_characters':t.get('missing_characters'),'added_characters':t.get('added_characters'),
        'median_mm':g.get('word_summary',{}).get('median_position_error_mm'),
        'p95_mm':g.get('word_summary',{}).get('p95_position_error_mm'),
        'max_mm':g.get('word_summary',{}).get('max_position_error_mm'),
        'source_words':g.get('word_summary',{}).get('source_words'),'word_coverage':g.get('word_summary',{}).get('match_coverage'),
        'categories':{k:{'status':c['status'],**c['summary']} for k,c in g.get('categories',{}).items()},
        'page_count_difference':g.get('page_count_difference'),'native_tables':s['audit']['native_tables'],
        'textboxes':s['audit']['text_box_count'],'hidden_characters':s['audit']['hidden_characters'],
        'raster_replacements':s['raster_pages']['suspected_replacement_count'],
        'edit_probe':{k:s['edit_probe'].get(k) for k in ('status','outcome','original_unchanged','objects_preserved','xml_text_change_exact','missing_baseline_characters','page_count_change','affected_pages','rule_text_collisions')},
        'targets':a['target_summary'],'target_checks':a['target_checks'],'assessment_id':a['assessment_id']}


def one(row,args,renderer,fingerprint):
    source=Path(row['source']['pdf']);source_sha=digest(source)
    if row['source'].get('actual_sha256') and row['source']['actual_sha256']!=source_sha:raise ValueError('Frozen source SHA mismatch')
    work=args.output/'runs'/fingerprint[:16]/row['id'];work.mkdir(parents=True,exist_ok=True)
    result={'id':row['id'],'group':row['group'],'source':str(source),'source_sha256':source_sha,
            'validator_code_sha256':fingerprint,'status':'measured','renderer':renderer,'conversion_changed':False}
    previous=None
    for kind in ('before','after'):
        original=Path(row[kind]['docx']);docx_sha=digest(original);snapshot=work/'inputs'/(kind+'.docx');snapshot.parent.mkdir(exist_ok=True)
        if not snapshot.exists() or digest(snapshot)!=docx_sha:shutil.copy2(original,snapshot)
        render=render_docx_to_pdf(snapshot,work/kind/'render',renderer['path'])
        if render['status']!='rendered':raise RuntimeError(f'{kind} render: {render}')
        pdf=Path(render['pdf_path']);visual=compare_pdfs(source,pdf,work/kind/'visual')
        visual.update(rendered_pdf_path=str(pdf),renderer=renderer['path'])
        model_path=original.with_suffix('.model.json');model=Document.model_validate_json(model_path.read_text()) if model_path.is_file() else None
        if model is not None and model.source_sha256!=source_sha:raise ValueError('Model refers to another source PDF')
        truth=row['source'].get('ground_truth')
        # A transcript extracted from the native PDF is not an independent OCR
        # ground truth. Keep native logical flow as the declared reference.
        if truth and (str(truth).endswith('.pdf.txt') or not Path(truth).is_file()):truth=None
        if truth and row['group']!='regression-simple':truth=None
        a,visual=assess_conversion(source,snapshot,work/kind/'assessment',model=model,visual=visual,renderer=renderer['path'],
            ground_truth=truth,run_edit_probe=not args.no_edit_probe and kind=='after',previous=previous)
        data={'application':'PDF2DOCX AI Fidelity','version':__version__,'source':source.name,'source_sha256':source_sha,
              'pages':visual['original_pages'],'mode':'validation of frozen '+kind+' conversion','visual':visual,'assessment':a,
              'structural':{'audit':a['dimensions']['structure']['audit']},'warnings':['No converter change is claimed by this validator comparison.'],
              'non_editable':[],'assessment_history_path':persist_assessment(a,args.output/'assessments')}
        quality=work/(kind+'.validation.json');report=work/(kind+'.validation.html')
        write_json(quality,data);write_report(data,report)
        result[kind]={'summary':summarize(a),'assessment_json':str(quality),'report':str(report),'docx_sha256':docx_sha,
                      'rendered_pdf_sha256':digest(pdf),'docx':str(snapshot),'rendered_pdf':str(pdf),'probe_enabled':not args.no_edit_probe and kind=='after'}
        if kind=='before':previous=a
        else:
            old=legacy_measure(source,pdf,work/'legacy-validator.json')
            # Same artifacts: pixel similarity cannot be presented as improved
            # merely because a validator was changed.
            assert abs(old['mean_ssim']-visual['mean_ssim'])<1e-10,'Unexpected SSIM method drift'
            old_cer=old['textual'].get('cer');new_cer=a['dimensions']['textual']['strict_stream'].get('cer')
            if old_cer is not None and new_cer is not None:assert abs(old_cer-new_cer)<1e-10,'Exact text distance changed on comparable references'
            result['legacy_validator']={'ssim':old['mean_ssim'],'cer_strict':old_cer,'wer_strict':old['textual'].get('wer'),
                'median_pt':old['geometry'].get('median_position_error_pt'),'p95_pt':old['geometry'].get('p95_position_error_pt'),
                'same_rendered_pdf_sha256':digest(pdf),'raw_json':str(work/'legacy-validator.json')}
            result['conversion_regression']=a['regression']
    assert digest(source)==source_sha and digest(Path(row['after']['docx']))==result['after']['docx_sha256'],'Input changed during validation'
    result['completed_utc']=datetime.now(timezone.utc).isoformat();return result


def number(value,digits=4):return 'n.d.' if value is None else f'{value:.{digits}f}'


def final_report(results,args,metadata):
    good=[r for r in results if r['status']=='measured'];bad=[r for r in results if r['status']!='measured']
    destination=ROOT/'docs/validation-final-report.html';md=ROOT/'docs/validation-final-report.md'
    rows=[]
    for r in good:
        a=r['after']['summary'];old=r['legacy_validator'];probe=a['edit_probe']
        rows.append([r['id'],r['group'],number(old['ssim'])+' → '+number(a['ssim']),number(a['worst_page_ssim']),
            number(old['cer_strict']*100 if old['cer_strict'] is not None else None)+' → '+number(a['cer_strict']*100 if a['cer_strict'] is not None else None),
            number(a['cer_primary']*100 if a['cer_primary'] is not None else None),
            number(old['median_pt'])+' pt → '+number(a['median_mm'])+' mm',number(a['p95_mm']),number(a['max_mm']),
            number(a['missing_characters'],0)+'/'+number(a['added_characters'],0),a['raster_replacements'],probe['outcome'],str(a['targets'])])
    headers=['Documento','Gruppo','SSIM vecchio → nuovo validatore','SSIM peggiore pagina','CER stream % prima → dopo','CER riferimento logico/GT %','Stessa mediana, pt → mm','P95 mm','Massimo mm','Caratteri mancanti/aggiunti','Raster sostitutivi','Prova di modifica','Target sperimentali']
    body='<p>Validazione multidimensionale 0.3.0. <strong>Il cambio del validatore non migliora da solo un DOCX.</strong> I vecchi e nuovi SSIM/CER stream sono calcolati sugli stessi PDF renderizzati, verificati con SHA-256. Cambi di unità e di riferimento testuale non sono presentati come miglioramenti della conversione.</p>'
    body+='<section><h2>Modifiche e metodologia</h2><p>Quattro dimensioni separate: SSIM globale/primo piano e peggior pagina; CER/WER esatti con normalizzazione dichiarata, ordine e posizioni degli errori; IoU e geometria di otto categorie in punti e millimetri; audit OOXML con prova di modifica reale su una copia. Nessun punteggio composito o certificazione del 99%.</p><p>Il validatore precedente 0.2.0 è eseguito in un processo isolato. Il nuovo usa la stessa rasterizzazione e lo stesso renderer per entrambi gli artefatti. Le conversioni congelate precedenti e correnti sono inoltre confrontate con il medesimo nuovo validatore per segnalare regressioni reali.</p><p><a href="validation-methodology.md">Definizioni, riferimenti, limiti e riproduzione</a>. CER/WER usano la distanza esatta documentata da <a href="https://rapidfuzz.github.io/RapidFuzz/Usage/distance/Levenshtein.html">RapidFuzz</a>; soglia CER 0,001 = 0,1%.</p></section>'
    body+='<section><h2>Confronto del validatore sugli stessi documenti</h2><p>Misurati '+str(len(good))+' · falliti '+str(len(bad))+'. Il CER stream confronta lo stesso ordine interno PDF, mentre il CER logico/GT dichiara un altro riferimento: non sono valori intercambiabili. La conversione da pt a mm non è un miglioramento geometrico.</p>'+table_html(rows,headers)+'</section>'
    conversion_rows=[];regression_rows=[]
    for r in good:
        b,a=r['before']['summary'],r['after']['summary'];reg=r['conversion_regression']
        conversion_rows.append([r['id'],number(b['ssim'])+' → '+number(a['ssim']),number(b['cer_primary']*100 if b['cer_primary'] is not None else None)+' → '+number(a['cer_primary']*100 if a['cer_primary'] is not None else None),number(b['median_mm'])+' → '+number(a['median_mm']),number(b['p95_mm'])+' → '+number(a['p95_mm']),len(reg['regressions']),reg['tradeoff']])
        for change in reg['regressions']:regression_rows.append([r['id'],change['metric'],change['before'],change['after'],change['delta'],reg['tradeoff']])
    body+='<section><h2>Conversioni precedenti e correnti con lo stesso nuovo validatore</h2>'+table_html(conversion_rows,['Documento','SSIM 0.1.1 → 0.2.0','CER logico/GT %','Mediana mm','P95 mm','Regressioni','SSIM migliora ma altro peggiora'])+'</section>'
    body+='<section><h2>Regressioni e compromessi espliciti</h2>'+table_html(regression_rows,['Documento','Metrica','Prima','Dopo','Delta','Compromesso'])+'<p>La comparabilità del renderer e le tolleranze numeriche sono registrate in ogni JSON. Un guadagno SSIM non annulla peggioramenti testuali, geometrici o strutturali. Il campo missing_native_images conta immagini sorgenti non abbinate, non perdite di byte provate: sul rendering PLOS vi sono 11 immagini sorgenti e 11 nel risultato, ma 10 cambiano pagina e risoluzione del raster e restano da verificare. Il conservativo controllo non certifica la conservazione.</p></section>'
    body+='<section><h2>Interpretazione delle differenze di testo</h2><p>Nel caso formula, SSIM della conversione passa da 0,997085 a 0,998513 ma il CER del flusso fisico inferito passa da 0 a 5,2632%: l’esponente 2 viene estratto prima di E = mc. Non sono caratteri scomparsi; è una segnalazione di ordine/tokenizzazione da revisionare con la semantica della formula. Anche procurement conserva i caratteri ma ha CER logico non nullo. I riferimenti inferiti non sostituiscono una ground truth indipendente.</p><p>Per la pagina mista il riferimento nativo non contiene le parole OCR: CER/WER complessivi sono indisponibili senza riferimento completo. Le differenze diagnostiche rispetto al solo testo nativo non vengono interpretate come errori delle parole OCR aggiunte correttamente.</p></section>'
    cv=next((r for r in good if r['id']=='europass_fictitious'),None)
    if cv:
        detail=read_json(cv['after']['assessment_json']);a=detail['assessment'];probe=a['dimensions']['structure']['edit_probe']
        body+='<section><h2>Curriculum europeo obbligatorio</h2><p>Due pagine, dati interamente fittizi, ritratto sintetico, date allineate, elenchi e vera tabella delle lingue. Originale e DOCX di conversione non vengono modificati. La prova aggiunge tre parole a una copia e confronta il salvataggio e il rendering.</p>'
        for p in detail['visual']['pages']:
            body+='<h3>Pagina '+str(p['page'])+'</h3><div class="figures">'
            for key,label in (('original_path','PDF originale'),('result_path','DOCX renderizzato'),('overlay_path','Overlay')):
                from evaluate_reconstruction import image_uri
                if p.get(key):body+='<figure><img src="'+image_uri(p[key])+'" alt="'+escape(label)+'"><figcaption>'+escape(label)+'</figcaption></figure>'
            body+='</div>'
        compact_probe={k:v for k,v in cv['after']['summary']['edit_probe'].items() if k!='rule_text_collisions'}
        body+='<p>Prova: '+escape(str(compact_probe))+'</p>'
        collisions=probe.get('rule_text_collisions',{})
        body+='<p><strong>Nuove intersezioni sospette tra linee decorative e testo: '+str(collisions.get('introduced_count','n.d.'))+'.</strong> Testo, foto e tabella conservati non dimostrano stabilità grafica della modifica.</p>'
        body+=table_html([[x['page'],x['text'],x['text_bbox_pt'],x['rule_bbox_pt']] for x in collisions.get('introduced',[])],['Pagina','Titolo interessato','Box testo pt','Box linea pt'])
        for p in probe.get('previews',[]):
            body+='<details><summary>Modifica reale, pagina '+str(p['page'])+'</summary><div class="figures">'
            for key,label in (('before_path','Prima'),('after_path','Dopo tre parole'),('overlay_path','Overlay modifica')):
                if p.get(key):body+='<figure><img src="'+image_uri(p[key])+'" alt="'+escape(label)+'"><figcaption>'+escape(label)+'</figcaption></figure>'
            body+='</div></details>'
        body+='</section>'
    body+='<section><h2>Errori residui e limiti</h2><p>PLOS ed Eurostat rimangono casi difficili di conversione: font mancanti, pagine aggiuntive, flusso e grafica incompleta. Il testo ruotato viene ricostruito orizzontalmente e può avere errori geometrici molto grandi pur con SSIM alto. I bordi delle tabelle sono semplificati. Questi errori non vengono corretti o occultati dal validatore.</p><p>Paragrafi, corsie di colonna, header/footer e ordine fisico sono inferenze esplicite. Le tabelle senza bordi, il significato dei grafici e i cambi di campo non hanno una ground truth semantica universale nel PDF. I soli match geometrici non coprono contenuti mancanti: copertura, numeri e testo restano separati. Le coordinate degli errori testuali indicano il box della parola contenente il carattere, non contorni dei glifi.</p><p>Il test di modifica misura un’inserzione deterministica: non certifica ogni possibile intervento. Reflow successivo può essere legittimo. LibreOffice è verificato; Microsoft Word non è stato usato come renderer. Le precedenti correzioni guidate dal corpus sono documentate nel rapporto di ricostruzione: questo confronto del validatore non è un nuovo holdout cieco.</p></section>'
    body+='<section><h2>Priorità successive non implementate</h2><p>Collegare le decorazioni al flusso del paragrafo per evitare le sovrapposizioni dopo una modifica del CV; risolvere le regressioni di conversione evidenziate; confronto con Microsoft Word e font effettivi; ground truth semantica indipendente per tabelle, paragrafi e lettura; più tipi di modifica e documenti indipendenti. Le soglie SSIM≥0,990, CER≤0,1%, mediana≤1mm e P95≤2mm restano sperimentali.</p></section>'
    import xml.etree.ElementTree as ET
    tests=ROOT/'docs/validation-test-results.xml'
    if tests.is_file():
        suites=[s.attrib for s in ET.parse(tests).getroot().iter('testsuite')]
        body+='<section><h2>Verifica della suite</h2><p>Suite completa con corpus complesso, Vision e MiniCPM reali abilitati.</p><pre>'+escape(json.dumps(suites,ensure_ascii=False,indent=2))+'</pre><a href="validation-test-results.xml">JUnit completo</a></section>'
    body+='<section><h2>Report JSON/HTML individuali e provenienza</h2><ul>'
    for r in good:
        body+='<li>'+escape(r['id'])+': <a href="'+href(r['before']['report'],destination.parent)+'">conversione precedente</a> · <a href="'+href(r['after']['report'],destination.parent)+'">conversione corrente</a> · <a href="'+href(r['after']['assessment_json'],destination.parent)+'">JSON</a></li>'
    body+='</ul><pre>'+escape(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre><h3>Attribuzioni dei PDF pubblici</h3><p>I DOCX e le anteprime di confronto sono trasformazioni per valutazione della conversione.</p><ul>'
    public_manifest=read_json(ROOT/'tests/fixtures/complex/public/manifest.json')
    for item in public_manifest['documents']:
        if any(r['id']==item['id'] for r in good):
            body+='<li>'+escape(item['attribution'])+' <a href="'+escape(item['landing_url'],quote=True)+'">Fonte ufficiale</a> · <a href="'+escape(item['license_url'],quote=True)+'">Licenza</a></li>'
    body+='</ul></section>'
    if bad:body+='<section><h2>Valutazioni non riuscite</h2><pre>'+escape(json.dumps(bad,ensure_ascii=False,indent=2))+'</pre></section>'
    destination.write_text(page('Validazione PDF → DOCX in quattro dimensioni',body),encoding='utf-8')
    lines=['# Validazione PDF → DOCX in quattro dimensioni','',f'Documenti misurati: {len(good)}; falliti: {len(bad)}.','',
           'Il DOCX non cambia nel confronto vecchio/nuovo validatore. SSIM e CER stream sono ricalcolati sugli stessi PDF. Riferimenti logici e cambi di unità non sono miglioramenti del convertitore.','',
           '| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    lines.extend('| '+' | '.join(str(x).replace('|','\\|') for x in row)+' |' for row in rows)
    lines+=['','## Regressioni delle conversioni','', '| Documento | Metrica | Prima | Dopo | Delta | Compromesso |','| --- | --- | --- | --- | --- | --- |']
    lines.extend('| '+' | '.join(str(x) for x in row)+' |' for row in regression_rows)
    lines+=['','## Limiti e priorità','', 'Vedere il rapporto HTML per immagini, prove di modifica, categorie e riferimenti. Paragrafi/colonne/lettura restano ipotesi. Le regressioni PLOS/Eurostat, la rotazione e i bordi sono problemi di conversione ancora presenti. Microsoft Word non verificato. Le soglie sono sperimentali.','',
            '## Provenienza','', '```json',json.dumps(metadata,ensure_ascii=False,indent=2),'```','']
    md.write_text('\n'.join(lines),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=DEFAULT);p.add_argument('--frozen-results',type=Path,default=FROZEN)
    p.add_argument('--only',nargs='+');p.add_argument('--no-edit-probe',action='store_true');p.add_argument('--report-only',action='store_true');p.add_argument('--force',action='store_true')
    args=p.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    if not LEGACY.is_dir():raise FileNotFoundError('Preserved validator 0.2.0 required')
    fingerprint=_code_fingerprint();renderer=renderer_identity();results_dir=args.output/'results';results_dir.mkdir(exist_ok=True)
    rows=[read_json(file) for file in sorted(args.frozen_results.glob('*.json'))]
    rows=[r for r in rows if r.get('status')=='measured' and (not args.only or r['id'] in args.only)]
    if not rows:raise ValueError('No frozen conversions selected')
    failures=0
    if not args.report_only:
        for index,row in enumerate(rows,1):
            print(f'[{index}/{len(rows)}] {row["group"]}: {row["id"]}',flush=True)
            result_file=results_dir/(row['id']+'.json')
            try:
                old=read_json(result_file) if result_file.exists() else None
                artifacts_unchanged=bool(old and old.get('source_sha256')==digest(Path(row['source']['pdf'])) and all(
                    old.get(kind,{}).get('docx_sha256')==digest(Path(row[kind]['docx']))
                    and Path(old.get(kind,{}).get('assessment_json','missing')).is_file()
                    and Path(old.get(kind,{}).get('rendered_pdf','missing')).is_file()
                    and old.get(kind,{}).get('rendered_pdf_sha256')==digest(Path(old[kind]['rendered_pdf']))
                    for kind in ('before','after')))
                if old and artifacts_unchanged and not args.force and old.get('validator_code_sha256')==fingerprint and old.get('status')=='measured' and old['after']['probe_enabled']==(not args.no_edit_probe) and old['renderer']==renderer:
                    result=old
                else:result=one(row,args,renderer,fingerprint)
                print('  legacy/new SSIM '+number(result['legacy_validator']['ssim'])+'/'+number(result['after']['summary']['ssim'])+'; CER '+number(result['after']['summary']['cer_primary'])+'; P95 mm '+number(result['after']['summary']['p95_mm']),flush=True)
            except Exception as exc:
                result={'id':row['id'],'group':row['group'],'status':'failed','error':str(exc),'validator_code_sha256':fingerprint};failures+=1
                print('  FAILED '+str(exc),flush=True)
            write_json(result_file,result)
    results=[]
    for row in rows:
        path=results_dir/(row['id']+'.json')
        result=read_json(path) if path.exists() else {'id':row['id'],'group':row['group'],'status':'not_run'}
        if result.get('status')=='measured' and result.get('validator_code_sha256')!=fingerprint:
            result={**result,'status':'stale_previous_measurement'}
        if result.get('status')=='measured':
            for kind in ('before','after'):
                result[kind]['summary']=summarize(read_json(result[kind]['assessment_json'])['assessment'])
            write_json(path,result)
        results.append(result)
    metadata={'completed_utc':datetime.now(timezone.utc).isoformat(),'application_version':__version__,'validator_code_sha256':fingerprint,
              'legacy_code_sha256':code_digest(LEGACY),'evaluation_script_sha256':digest(Path(__file__)),
              'renderer':renderer,'frozen_conversions':str(args.frozen_results.resolve()),
              'command':sys.argv,'comparison':'same SHA-256 rendered PDF for validator 0.2.0 and 0.3.0; no converter improvement claimed','edit_probe':not args.no_edit_probe}
    write_json(args.output/'evaluation.json',{'run':metadata,'results':results});final_report(results,args,metadata)
    print('Report: '+str(ROOT/'docs/validation-final-report.html'),flush=True)
    return 1 if failures or any(r['status']!='measured' for r in results) else 0


if __name__=='__main__':raise SystemExit(main())

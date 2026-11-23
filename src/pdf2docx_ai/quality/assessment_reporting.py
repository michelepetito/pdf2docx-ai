"""HTML presentation of the four dimensions; no composite fidelity percent."""
from html import escape
from pathlib import Path
import base64


def _v(value,digits=4):
    return 'non disponibile' if value is None else f'{value:.{digits}f}' if isinstance(value,float) else str(value)


def _table(headers,rows):
    return '<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join('<td>'+escape(_v(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def _picture(path,label):
    file=Path(path)
    if not file.is_file():return ''
    return '<figure><img alt="'+escape(label)+'" src="data:image/jpeg;base64,'+base64.b64encode(file.read_bytes()).decode()+'"><figcaption>'+escape(label)+'</figcaption></figure>'


def assessment_html(a):
    if not a:return ''
    d=a['dimensions'];v=d['visual'];t=d['textual'];g=d['geometry'];s=d['structure'];audit=s['audit'];p=t.get('primary',{})
    content='<section><h2>Validazione in quattro dimensioni</h2><p><strong>SSIM non è una percentuale certificata di fedeltà.</strong> Testo, geometria e modificabilità non vengono compensati da una buona immagine. Non viene calcolato un punteggio composito.</p>'
    content+=_table(['Dimensione','Misura','Riferimento'],[
        ['Visiva','SSIM '+_v(v.get('mean_ssim'))+' · peggiore pagina '+_v(v.get('minimum_page_ssim')),'stesso DPI/canvas; nessun riallineamento'],
        ['Testuale','CER '+(_v(100*p['cer'])+'%' if p.get('cer') is not None else 'non disponibile')+' · WER '+(_v(100*p['wer'])+'%' if p.get('wer') is not None else 'non disponibile'),p.get('reference','nessun riferimento')],
        ['Geometrica','mediana '+_v(g.get('word_summary',{}).get('median_position_error_mm'))+' mm · P95 '+_v(g.get('word_summary',{}).get('p95_position_error_mm'))+' mm','origini dei box delle parole associate; copertura e baseline separate'],
        ['Strutturale',str(audit['visible_nonwhitespace_characters'])+' caratteri visibili · '+str(audit['native_tables'])+' tabelle · '+str(audit['picture_count'])+' immagini','audit OOXML e prova di modifica separati']])
    content+='<p>Target sperimentali, non garanzie. Una misura non disponibile non equivale a zero errori.</p>'+_table(
        ['Verifica','Esito','Valore','Relazione','Target','Base'],[[k,c['status'],c['value'],c['operator'],c['threshold'],c['basis']] for k,c in a['target_checks'].items()])+'</section>'
    content+='<section><h2>A — Resa visiva per pagina</h2>'+_table(['Pagina','SSIM','SSIM primo piano','Pixel differenti','Pagina mancante','Pagina aggiunta'],
        [[p['page'],p.get('ssim'),(p.get('foreground') or {}).get('foreground_ssim'),p.get('changed_pixel_fraction'),p.get('target_page_missing'),p.get('source_page_missing')] for p in v.get('pages',[])])
    content+='<p>Pagine sotto target: '+escape(str(v.get('pages_below_target',[])))+'. Le anteprime, l’overlay e le differenze assolute seguono nel rapporto.</p></section>'
    rows=[]
    for label,key in [('Stream PDF, solo spazi bianchi','strict_stream'),('Stream normalizzato','normalized_stream'),('Flusso fisico inferito','logical_pdf_flow'),('Ordine XML del corpo Word','docx_body_order'),('Ground truth esterno','ground_truth')]:
        m=t.get(key,{})
        if m:rows.append([label,m.get('cer')*100 if m.get('cer') is not None else None,m.get('wer')*100 if m.get('wer') is not None else None,m.get('reference',m.get('normalization',''))])
    content+='<section><h2>B — Testo, valori e ordine di lettura</h2>'+_table(['Riferimento','CER %','WER %','Metodo'],rows)
    if t.get('native_only_reference_incomplete_for_ocr'):
        content+='<p><strong>Riferimento nativo incompleto: esclude le regioni OCR.</strong> I confronti dello stream nativo sopra sono diagnostici parziali; aggiunte e differenze non dimostrano errori OCR. CER/WER complessivi e conteggi di contenuto richiedono un riferimento esterno completo.</p>'
    content+='<p>Normalizzazione: '+escape(a['methodology']['normalization'])+'. I segni numerici, gli accenti, la punteggiatura e le maiuscole restano significativi.</p>'
    content+=_table(['Caratteri mancanti','Caratteri aggiunti','Token non associati sorgente','Token non associati risultato','Possibili duplicati','Interpretazione'],[[t.get('missing_characters'),t.get('added_characters'),t.get('missing_token_count'),t.get('added_token_count'),t.get('potential_duplicate_token_count'),t.get('sequence_error_interpretation')]])
    numeric=t.get('reference_numbers_dates',{});order=t.get('stream_order',{})
    content+='<p><strong>Numeri/date mancanti o aggiunti: '+escape(str(numeric.get('missing_count','n.d.')))+' / '+escape(str(numeric.get('added_count','n.d.')))+'.</strong> Sono verificati anche quando CER globale è piccolo. Inversioni delle ancore nello stream: '+escape(str(order.get('inversions','n.d.')))+'.</p>'
    locations=[]
    for role,key in [('mancante','missing_token_locations'),('aggiunto','added_token_locations'),('possibile duplicato','potential_duplicate_locations')]:
        for item in t.get(key,[])[:35]:locations.append([role,item['text'],item['page'],item['bbox_pt'],item['bbox_mm']])
    content+='<details><summary>Posizioni dei token difformi</summary>'+_table(['Tipo','Testo','Pagina','Box pt','Box mm'],locations)+'</details>'
    ops=[]
    for item in t.get('sequence_edit_locations',[])[:60]:
        src=item.get('source') or {};dst=item.get('target') or {}
        ops.append([item['operation'],item['source_character'],item['target_character'],src.get('page'),src.get('bbox_mm'),dst.get('page'),dst.get('bbox_mm')])
    content+='<details><summary>Operazioni testuali localizzate</summary><p>Gli edit descrivono la sequenza dichiarata; non vengono confusi con una prova di cancellazione semantica. Limite campioni: '+escape(str(t.get('location_limit','n.d.')))+'.</p>'+_table(['Operazione','Prima','Dopo','Pagina sorgente','Box sorgente mm','Pagina risultato','Box risultato mm'],ops)+'</details></section>'
    categories=g.get('categories',{});rows=[]
    for name,cat in categories.items():
        z=cat['summary'];rows.append([name,cat['status'],str(z['matched_elements'])+'/'+str(z['source_elements']),z['target_coverage'],z['mean_iou'],z.get('mean_position_error_mm'),z.get('median_position_error_mm'),z.get('p95_position_error_mm'),z.get('max_position_error_mm'),z.get('mean_x_error_mm'),z.get('mean_y_error_mm'),z.get('mean_width_error_mm'),z.get('mean_height_error_mm')])
    content+='<section><h2>C — Geometria e impaginazione</h2><p>1 pt = 25,4/72 mm. Statistiche sui soli elementi associati nella stessa pagina, insieme a copertura e mancanti. Paragrafi, colonne e ruoli ai bordi sono inferenze dichiarate.</p>'
    content+=_table(['Categoria','Stato','Associati/sorgente','Copertura risultato','IoU medio','Media mm','Mediana mm','P95 mm','Massimo mm','Errore X medio mm','Errore Y medio mm','Errore larghezza mm','Errore altezza mm'],rows)
    for name,cat in categories.items():
        content+='<details><summary>'+escape(name)+' — elementi più difformi</summary><p>'+escape(cat['basis'])+'</p>'+_table(
            ['Testo','Pagina sorgente/risultato','Box sorgente pt','Box risultato pt','Errore mm','IoU','Frammenti'],
            [[m['text'][:160],str(m['source_page'])+'/'+str(m['target_page']),m['source_bbox'],m['target_bbox'],m.get('position_error_mm',m['position_error_pt']*25.4/72),m['iou'],m.get('fragments',1)] for m in cat.get('matches',[])[:20]])+'</details>'
    margins=g.get('margins',{});layout=g.get('layout',{})
    content+='<p>Margini: '+escape(margins.get('basis','non disponibili'))+'. Parole su altra pagina: '+escape(str(layout.get('page_drift_words','n.d.')))+'; su altra corsia: '+escape(str(layout.get('column_lane_drift_words','n.d.')))+'.</p>'
    content+=_table(['Pagina','Margini sorgente pt','Margini risultato pt','Errori assoluti mm'],[[m['page'],m['source_pt'],m['target_pt'],m['absolute_error_mm']] for m in margins.get('pages',[])])
    content+='<details><summary>Differenze di impaginazione</summary>'+_table(['Tipo','Dati'],[[x.get('kind'),x] for x in layout.get('differences',[])])+'</details></section>'
    probe=s['edit_probe'];content+='<section><h2>D — Modificabilità e prova di modifica</h2>'+_table(['Controllo','Valore'],
        [[k,audit.get(k)] for k in ('hidden_characters','text_box_count','textbox_text_fraction','native_tables','expected_source_tables','unverified_additional_tables','explicitly_invisible_tables','anchored_pictures','inline_pictures','sections','native_column_counts','tab_stops','indented_paragraphs','document_protection_enforced','locked_content_controls')])
    content+='<p>Possibili pagine raster sostitutive: '+escape(str(s['raster_pages']['suspected_replacement_count']))+'. La presenza di testo invisibile o di una grande immagine non dimostra modificabilità.</p>'
    content+=_table(['Prova su copia','Esito'],[[k,probe.get(k)] for k in ('status','operation','original_unchanged','objects_preserved','missing_baseline_characters','page_count_change','affected_pages','outcome')])
    collisions=probe.get('rule_text_collisions',{})
    if collisions:
        content+='<p>Nuove intersezioni sospette fra righe decorative e testo: '+escape(str(collisions.get('introduced_count')))+'. '+escape(collisions.get('basis',''))+'</p>'
        content+=_table(['Pagina','Testo','Box testo pt','Box linea pt'],[[r['page'],r['text'],r['text_bbox_pt'],r['rule_bbox_pt']] for r in collisions.get('introduced',[])])
    content+='<p>Un’aggiunta può causare reflow legittimo: numero di pagine, spostamenti e testo conservato restano separati. La prova non certifica ogni possibile modifica in Word.</p>'
    for page in probe.get('previews',[]):
        content+='<details><summary>Prova di modifica, pagina '+str(page['page'])+'</summary><div class="comparison">'+''.join(_picture(page[key+'_path'],label) for key,label in (('before','Prima della modifica'),('after','Dopo tre parole aggiunte'),('overlay','Overlay della prova')) if page.get(key+'_path'))+'</div></details>'
    content+='</section>'
    regression=a.get('regression',{})
    if regression.get('status')=='compared':
        content+='<section><h2>Regressioni rispetto alla misura precedente</h2>'
        if regression.get('tradeoff'):content+='<p><strong>Migliora SSIM ma peggiora almeno un’altra dimensione: compromesso esplicitamente segnalato.</strong></p>'
        content+=_table(['Metrica','Prima','Dopo','Delta','Regressione'],[[r['metric'],r['before'],r['after'],r['delta'],r['regressed']] for r in regression['changes']])
        content+='<p>'+escape(regression['interpretation'])+'</p></section>'
    return content

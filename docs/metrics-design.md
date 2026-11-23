# Misure della ricostruzione geometrica

Per la revisione **0.3.0** vedere [validazione multidimensionale](validation-methodology.md).
Il limite Levenshtein descritto sotto è storico: ora RapidFuzz calcola la distanza
esatta senza il precedente limite di celle. Sono aggiunti riferimenti testuali
distinti, geometria in mm per otto categorie, storia e prova di modifica reale.

La revisione del 17 novembre 2026 distingue aspetto, coordinate, contenuto ed
editabilità. Nessun singolo numero rappresenta una percentuale di fedeltà.
I risultati di una versione precedente vanno ricalcolati sul suo PDF renderizzato
con le stesse metriche della nuova versione, non confrontati con il vecchio
SSIM riallineato o con il vecchio matching dei soli blocchi.

## Contratto per validazione e ottimizzazione

```python
evaluate_pdf_pair(original, rendered, assets=None, include_images=False, dpi=100)
```

Restituisce `status`, numero di pagine, `page_count_difference`, `geometry`,
`textual`, `foreground`, `mean_ssim`, `images` e `pages`. Le pagine mancanti o
aggiunte non vengono ignorate: il raster assente è un canvas bianco e rimane
marcato con `target_page_missing` o `source_page_missing`. Il confronto usa il
massimo dei due numeri di pagine, anziché limitarsi alle pagine comuni.

`compare_pdfs(original, rendered, assets)` mantiene il vecchio contratto pubblico
e attiva anche abbinamento immagini e produzione di asset. Sono mantenuti i
campi pagina storici `ssim`, `mean_absolute_pixel_error`,
`changed_pixel_fraction`, `mean_block_displacement_pt` e `matched_text_blocks`.
Gli ultimi due ora derivano dalle righe abbinate e non dai vecchi blocchi: sono
alias per retrocompatibilità, non misure confrontabili con i vecchi report.

L'ottimizzatore può usare la variante senza asset: salta JPEG, heatmap e detector
tabelle, conservando le misure effettive. Il raster è limitato a 2,5 milioni di
pixel per pagina; se necessario entrambi i documenti sono renderizzati allo
stesso DPI ridotto. Non si applicano stretch o traslazioni per alzare il punteggio.

## Coordinate e baseline

Tutti i box sono in punti PDF visualizzati, relativi al crop e con origine in
alto a sinistra. PyMuPDF fornisce testo e origini nel riferimento non ruotato;
si applica `page.rotation_matrix` sia al box sia al punto della baseline. Il
caso con MediaBox 640×900, crop(40,50,600,850), rotazione 90 e origine nativa
(90,140) è verificato esplicitamente: baseline visualizzata (710,50).

Il confronto delle coordinate non usa il raster registrato. `dx_pt` e `dy_pt`
sono risultato meno sorgente. Si misurano distanza dell'origine del box,
errore medio dei due angoli, differenze di larghezza/altezza e Intersection over
Union. Per ciascuna misura sono riportati media, mediana, P90, P95 e massimo.

La baseline è separata dal bordo superiore del box. Un font sostitutivo può
avere ascendenti diversi pur mantenendo la posizione delle lettere. Nella
baseline semplice già prodotta, Helvetica→Liberation Sans presenta mediana
box 2,3414 pt ma baseline 0,3008 pt; il P95 rispettivamente 3,9009 pt e 0,6008 pt. È un
esempio del campione, non un dato garantito. Spostare la linea di 2 pt solo per
compensare il box tipografico peggiorerebbe la geometria effettiva.

`pages[n].line_matches` comprende testo, box e baseline sorgente/risultato,
font e dimensione, errori, copertura dei token e `target_wrap_lines`. Una riga
originaria può essere associata a più righe nel risultato: i token abbinati
mantengono visibile il wrapping introdotto. I match vengono esposti soltanto
quando è associato almeno l'80% delle parole della riga sorgente.

## Abbinamento senza riuso dei duplicati

Le parole sono associate per identità testuale esatta dopo normalizzazione
Unicode NFC e degli spazi. Non si ignorano maiuscole, accenti, numeri o simboli.
Il vincolo è uno-a-uno: una parola del risultato non può soddisfare più parole
del sorgente. Per testi ripetuti, la distanza geometrica e la pagina risolvono
i casi ambigui in modo euristico. Per gruppi piccoli si ordinano le coppie per
costo; per parole molto frequenti si limita l'allocazione di candidati e si
preferiscono quelli sulla medesima pagina.

Questo non è un algoritmo di associazione semantica perfetto né una prova che
una delle ripetizioni fosse quella corretta. La copertura deve accompagnare
ogni percentile; un errore basso con pochi match non descrive tutto il documento.
Il testo trovato su un'altra pagina è contato in `page_drift_words` e non riceve
un errore geometrico nullo soltanto perché ha la stessa coordinata locale.

## Contenuto e ordine

CER/WER confrontano il testo estratto dai due PDF con sola normalizzazione
degli spazi; questa misura non è un ground truth OCR. Se il sorgente non ha
testo nativo, CER/WER sono `null` e lo stato dichiara che il riferimento manca.
L'accuratezza OCR deve usare il ground truth testuale separato della pipeline.

Il report include conteggi di parole mancanti, in eccesso, potenzialmente
duplicate, numeri/date e simboli alterati. L'uguaglianza dei conteggi è distinta
dall'uguaglianza della sequenza: una permutazione può conservare tutti i token
pur avere un ordine diverso. Sono disponibili anche confronti dei caratteri
non bianchi, per distinguere tokenizzazione/spazi da perdita effettiva di testo.

Levenshtein usa righe di memoria e elimina prefisso/suffisso identici senza
approssimare la distanza. Per grandi coppie profondamente differenti, oltre
25 milioni di celle residue, CER/WER risultano indisponibili con motivazione;
restano disponibili i conteggi esatti di contenuto. Non viene sostituita una
stima euristica presentandola come distanza esatta.

## Aspetto e primo piano

SSIM usa luminanza Pillow, finestra uniforme 7×7, covarianza campionaria e
costanti C1=(0,01×255)² e C2=(0,03×255)². Il canvas comune è bianco, alla stessa
scala fisica e senza riallineamento. Vengono mantenuti MAE RGB e frazione di
pixel con differenza massima per canale superiore a 25/255.

Per evitare che il bianco nasconda errori nel testo sono riportati separatamente:

- IoU e F1 delle maschere d'inchiostro, soglia minima dei canali RGB inferiore a 225.
- MAE soltanto sull'unione delle maschere d'inchiostro.
- SSIM sulla regione d'inchiostro estesa di 3 pixel, per includere il contesto
  locale della finestra senza pesare tutta la pagina bianca.

Queste misure sono sensibili a antialiasing, rasterizzazione e metriche dei font;
non sono misure OCR. Nella baseline semplice citata, SSIM globale 0,99187 convive
con SSIM di primo piano 0,70842: è proprio la distinzione che il vecchio report
non rendeva visibile. La media del documento è una media delle pagine, non una
percentuale di caratteri corretti e non un punteggio percettivo addestrato.

## Immagini ed editabilità

Con `include_images=True` si cercano prima digest dei pixel decodificati.
Se l'export ha cambiato il raster, l'abbinamento usa rapporto d'aspetto e
posizione sulla stessa pagina, dichiarandolo euristico. Il report distingue
`verified_identity_matches` da `heuristic_matches`: il secondo non dimostra
che sia stata conservata la stessa immagine. Le trasparenze o la compressione
originale non si certificano soltanto dal digest del pixmap.

La verifica OOXML riapre il DOCX, conta testo/celle native, immagini, caselle di
testo, tabelle aggiuntive rispetto al modello e documenti editable composti
soltanto da raster. Verifica inoltre che i byte degli asset immagine del modello
siano presenti invariati nelle parti immagine del DOCX. Questo certifica l'asset
intermedio; la conservazione dei byte originali PDF dipende dall'estrattore.
I confini dei run di stile non inseriscono spazi artificiali nel conteggio.
Formule raster e numeri dinamici PAGE non vengono falsamente contati come testo
perso nella verifica strutturale; il rendering misura comunque il risultato.

## Rendering e report

`render_docx_to_pdf` usa un profilo LibreOffice isolato e un timeout. Rimuove il
solo PDF di rendering precedente prima del comando, evitando di promuovere un
file vecchio quando il renderer fallisce. Se manca il renderer o il comando
fallisce lo stato è esplicito, senza metriche inventate.

L'HTML autonomo include originale, DOCX renderizzato, overlay, differenze,
heatmap, box verdi/magenta e coordinate delle 25 righe più divergenti. Le
immagini sono incorporate e il testo è escaped. `optimization.history` mostra
obiettivo, accettazione, SSIM globale/primo piano, errori box/baseline e pagine.
Le immagini prima/dopo vengono mostrate se `optimization.before` e `after`
contengono i rispettivi asset. L'ottimizzatore deve conservare la migliore
soluzione; il reporter non decide quale iterazione accettare.

## Regressioni automatiche

`tests/unit/test_geometry_metrics.py` verifica PDF identico, traslazione non
occultata, ascendente diverso con baseline uguale, parole ripetute, numeri/date
alterati, pagina mancante, testo spostato di pagina, wrapping, crop/rotazione,
immagine autonoma, HTML con storia/heatmap e escaping, PDF di rendering obsoleto,
testo lungo uguale, confini dei run e conservazione degli asset immagine.

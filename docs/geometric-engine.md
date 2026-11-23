# Geometric Layout Reconstruction Engine — 0.2.0

La revisione conserva la pipeline e i backend esistenti. Il modello intermedio aggiunge righe fisiche con baseline, direzione, ascendente/discendente e avanzamento tipografico. Le coordinate restano punti PDF nel crop visualizzato; conversioni Word: 20 twip/punto e 12.700 EMU/punto. CropBox e rotazione non vengono modificati durante l'estrazione.

## Regole di flusso

L'estrazione nativa prevale sull'OCR. Il motore deduce margini dai contenuti, interlinea dalle baseline e rientri dalle righe successive. Frammenti della stessa riga usano tabulazioni native; righe originali di un paragrafo usano interruzioni morbide. I gutter persistenti individuano fino a tre colonne, anche diseguali, con bande a larghezza piena e sezioni continue. Brevi date e etichette non bastano a creare una colonna. Il bordo dell'inchiostro è un limite inferiore della larghezza del paragrafo: un margine di tolleranza di due punti evita ritorni aggiuntivi dovuti all'arrotondamento delle metriche Word.

Le vere tabelle hanno griglia, larghezze, celle unite, sfondi e padding misurati. Le tabelle che proseguono su pagine diverse possono diventare più tabelle Word: non sono introdotte griglie per il layout. Le altezze sono esatte soltanto quando il testo misurato entra nella riga; altrimenti si consente l'espansione. Immagini native compatibili sono estratte senza ricompressione e ancorate alla pagina. Rettangoli e segmenti decorativi reali diventano forme DrawingML editabili senza contenitori di testo. Curve e grafica obliqua restano una limitazione segnalata.

Il matching dei font valuta famiglia e avanzamento delle stringhe sui font disponibili. Le sostituzioni metriche sono registrate; correzioni di tracking sono piccole e limitate. Nessun font incorporato viene redistribuito automaticamente. Le informazioni OS/2 su embedding descrivono permessi tecnici e non sostituiscono una licenza.

Un risultato di `fc-match` non dimostra che la famiglia richiesta esista: può essere un fallback. Per famiglie mancanti il DOCX iniziale conserva il nome richiesto, senza applicare tracking misurato su un font diverso. Il ciclo con renderer può provare una sostituzione scelta confrontando fino a100 campioni univoci con sei famiglie locali (Arial, Times New Roman, Calibri, Courier New, Georgia e Palatino, quando disponibili). Il candidato usa anche nelle celle esattamente il font misurato. Viene adottato solo se migliora l'obiettivo, rispetta gli invarianti e non peggiora SSIM globale o sul primo piano oltre0,001. La prova conta nel massimo di iterazioni. Se viene respinta, resta il font richiesto e la sua risoluzione nel renderer è dichiarata non verificata. Il report distingue famiglia disponibile, font risolto, campioni e scelta finale (`requested` oppure `metric`). Non vengono scaricati o incorporati font. La migliore larghezza non garantisce identità dei glifi, delle legature o della metrica verticale.

## Ciclo con renderer

1. Generare un DOCX iniziale a flusso naturale.
2. Renderizzare con LibreOffice usando un profilo isolato.
3. Associare parole e righe, misurare baseline, posizione, pagine e testo.
4. Provare, se necessario, il candidato tipografico; proporre correzioni limitate di Y e rientro sinistro per regione.
5. Rigenerare, verificare gli invarianti e accettare soltanto un miglioramento ammissibile.
6. Conservare sempre il miglior DOCX e il relativo PDF renderizzato.

È una ricerca locale deterministica per coordinate, non un renderer differenziabile. L'obiettivo penalizza soprattutto pagine divergenti e caratteri persi/aggiunti, poi baseline mediana e P95, X e somiglianza sul primo piano. Il P95 delle baseline non può peggiorare di oltre 0,5 punti rispetto alla prima versione. L'hash degli invarianti comprende testo di tutte le parti Word, dimensioni dei font, conteggi di tabelle/caselle di testo e byte delle immagini. I candidati che li cambiano vengono respinti. Non si alterano dimensioni dei caratteri per far entrare il testo.

Le proposte correggono Y e X; margini verticali e spaziature seguono questi obiettivi attraverso il flusso. Non sono implementate una ricerca globale su tutte le proprietà Word, l'ottimizzazione delle dimensioni delle immagini o una modifica automatica della struttura delle tabelle. Scansioni prive di testo nativo non forniscono corrispondenze geometriche dirette: la geometria iniziale usa box OCR o segmentazione raster dichiarata come stima.

Impostazioni Python `Settings`: `optimize_layout=True`, `max_layout_iterations=3` (0–12), `layout_max_adjustment_pt=24`, `layout_tolerance_pt=0.15`, `layout_min_improvement=0.001`, `layout_optimization_timeout=60` secondi. Arresti possibili: tolleranza raggiunta, limite di iterazioni/tempo, assenza di proposte, miglioramenti insufficienti, candidato respinto o renderer indisponibile. Storia, parametri e motivo compaiono nei report JSON/HTML. CLI e GUI attivano lo stesso percorso.

## Valutazione riproducibile

`scripts/evaluate_reconstruction.py` confronta lo snapshot precedente con il codice corrente in processi Python separati. Riutilizza un vecchio DOCX solo se l'hash del PDF coincide. Entrambi i DOCX vengono nuovamente renderizzati con il medesimo eseguibile attuale, identificato nel report, per evitare confronti fra versioni differenti del renderer. Hash del codice e configurazione controllano il riuso dei risultati.

Il rapporto A–F e i confronti individuali registrano pagine, SSIM globale/primo piano, mediana/P95 geometrica, baseline, CER/WER, parole mancanti/aggiunte, vere tabelle, immagini, parti non modificabili e tempi. Il PDF nativo non è ground truth per il testo interno delle immagini; quelle parole sono valutabili soltanto con un riferimento separato. I casi di sviluppo e quelli indipendenti sono distinti e non si presumono superati.

La suite verifica coordinate/crop/rotazione, testo Unicode e numeri, tabulazioni, conservazione JPEG, decorazioni effettive, vere tabelle, ancoraggi, baseline header/footer e rifiuto di candidati che alterano gli invarianti. I test complessi e OCR reali sono attivati esplicitamente. Risultati e limiti misurati: [rapporto finale](reconstruction-final-report.html).

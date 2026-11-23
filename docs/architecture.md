# Architettura

La pipeline separa estrazione, riconoscimento, ricostruzione e misurazione. Il modello intermedio Pydantic è indipendente dagli OCR e serializzabile JSON. La GUI dipende dall'API Python e non contiene logica di ricostruzione.

```text
CLI / FastAPI
    -> validazione PDF e limiti
    -> rendering pagina limitato in pixel + estrazione nativa PyMuPDF
    -> selezione regioni senza testo recuperabile
    -> detector opzionale / geometria -> OCR locale lazy
    -> Page / Region / TextLine / TextSpan / TableCell in punti PDF
    -> ordine lettura + review flags + eventuale secondo OCR
    -> GeometricLayoutReconstructionEngine -> python-docx / OOXML
    -> DOCX -> LibreOffice -> confronto -> correzioni vincolate -> miglior DOCX
    -> assessment: aspetto / testo / geometria / struttura
    -> prova opzionale di modifica su copia + cronologia immutabile + regressioni
    -> DOCX + JSON + HTML + PDF ricercabile opzionale
```

## Contratti

`OCREngine` restituisce testo, eventuali parole/righe con box in pixel del crop, formato e confidenza opzionale. La confidenza non viene inventata per i VLM. `LayoutDetector` restituisce regioni in pixel. Il fallback a proiezioni rileva inchiostro e spazi bianchi: non riconosce semanticamente titoli, formule o tabelle come un modello AI.

`PageTransform` applica scale indipendenti ricavate dalle dimensioni effettive del raster. I box delle estrazioni PyMuPDF passano per `rotation_matrix`: il riferimento canonico è il crop visualizzato, origine in alto a sinistra e unità punti (72 punti/pollice). Word usa 20 twip/punto e 12.700 EMU/punto. Il PDF ricercabile usa la trasformazione inversa `derotation_matrix`. Il cropbox originale e la rotazione restano nel modello.

Un bug verificato di PyMuPDF 1.26.7 può alterare la cropbox durante `find_tables` con rotazione. Il detector viene evitato su pagine ruotate/ritagliate e si conserva testo e avviso. Una futura implementazione dovrà usare una copia normalizzata verificando le coordinate di ritorno.

## Ricostruzione

Ogni pagina PDF diventa una sezione Word con dimensioni/orientamento e margini geometrici stimati. Paragrafi e run preservano testo, line break, font o sostituzione esplicita, size, grassetto, corsivo e colore. Le intestazioni ripetute vicino al bordo superiore diventano parti header; il bordo inferiore usa footer. Il riconoscimento è euristico, non semantico, e confronta il testo ai bordi anche quando il PDF lo raggruppa diversamente tra pagine. I footer conservano testo e numeri estratti; frammenti sulla stessa baseline usano tabulazioni.

Fino a tre colonne geometricamente separabili usano `w:cols`, larghezze/gutter misurati, sezioni continue per bande estese e interruzioni di colonna. Date e brevi etichette affiancate restano in tabulazioni. Note laterali e grafica sovrapposta richiedono ulteriori strategie. Tabelle native a griglia usano vere celle Word, larghezze fisse, merge, sfondi, padding, bordi e font estratti. Le tabelle HTML/OTSL dei backend OCR possono essere convertite in celle Word; senza un detector semantico non si richiede automaticamente il prompt tabella.

Le immagini sono elementi indipendenti ancorati alla pagina; l'estrazione conserva i byte originali quando possibile. Segmenti e rettangoli decorativi effettivi usano forme DrawingML prive di contenitori di testo. In modalità visual le pagine sono immagini esplicitamente classificate come raster non modificabile. Il percorso Office Math esiste solo come helper di testo Unicode; non è una conversione verificata di LaTeX complesso. Per i risultati OCR LaTeX si mantiene il ritaglio originale con avviso. Le formule native rimangono testo Unicode editabile.

Il [motore geometrico](geometric-engine.md) documenta il ciclo di coordinate descent, i limiti di tempo/iterazioni, gli invarianti e la conservazione della migliore soluzione. L'alias Python `DocumentReconstructionEngine` rimane compatibile con le integrazioni precedenti.

## Stato, memoria e concorrenza

La revisione 0.3.0 riusa il rendering e il matching finali, aggiungendo CER/WER
esatti, categorie geometriche, audit OOXML e prova di modifica. Le verifiche
dettagliate non sono ripetute a ogni tentativo dell'ottimizzatore.
`validate` può valutare anche un DOCX esistente senza riconvertire il PDF;
`--validate-editability` abilita la prova nella conversione. Configurazione
del solo validatore esclusa dal fingerprint della cache OCR. Definizioni,
stati, hash e limiti in [metodologia](validation-methodology.md).

Elaborazione e rilascio dei raster pagina per pagina, OCR inizializzato solo se necessario, crop e raw persistiti in `.work`. Il checkpoint è scritto con rename atomico dopo ciascuna pagina; l'hash include PDF, versione e configurazione. Un cambio fingerprint invalida i checkpoint precedenti prima di pubblicare il nuovo manifest. La ripresa è a livello di pagina, non durante una singola chiamata OCR.

Un lock esclusivo impedisce due scrittori sullo stesso output. I file finali vengono preparati nella directory di lavoro e poi rinominati: ogni rename è atomico, ma l'insieme di più artefatti non è una transazione di filesystem. Un'interruzione durante l'ultima pubblicazione può lasciare parte dei file; consultare troubleshooting.

MuPDF è protetto da un lock di processo condiviso anche con upload/anteprime. La GUI tiene la coda reattiva, ma serializza le conversioni; il benchmark parallelizza documenti in processi separati. I confronti fra modelli sono sequenziali. Ollama viene scaricato dalla memoria con `keep_alive=0` quando effettivamente usato; per server OpenAI compatibili il client chiude la connessione, senza assumere di controllare la memoria del server.

## Privacy

Non esiste codice di telemetria né invio documenti a Internet. Il frontend non carica risorse esterne. Il server serve su loopback, valida Host e Origin, limita upload e pagine e usa nomi interni casuali, allowlist di download e directory private. Il trasporto OCR accetta solo IP loopback e ignora proxy/redirect. Eventuali server OCR installati separatamente restano sotto il controllo dell'utente. I limiti non sostituiscono un sandbox di sistema per PDF ostili; non è stato svolto un audit di sicurezza indipendente.

# Limiti effettivi

La versione **0.3.0** amplia la misurazione e lascia invariato il convertitore.
Il [rapporto di validazione](validation-final-report.html) separa quattro
dimensioni, registra riferimenti e copertura e conserva i risultati precedenti.
La prova di modifica del CV rileva nuove intersezioni fra decorazioni ferme e
titoli spostati: contenuto integro e pagine invariate non garantiscono stabilità
del layout. Il controllo delle intersezioni è euristico e richiede revisione.
CER/WER esatti sono ora calcolabili anche sui documenti lunghi; paragrafi,
colonne, ruoli e lettura fisica restano inferenze. Vedere
[metodologia e limitazioni della misura](validation-methodology.md).

La versione 0.2.0 introduce la ricostruzione geometrica con ciclo di rendering e misure separate. La fedeltà dei casi editoriali complessi rimane variabile: risultati per documento, campioni indipendenti e regressioni sono nel [rapporto comparativo](reconstruction-final-report.html). Le misure storiche dell'MVP non sono confrontabili direttamente con quelle nuove.

| Area | Stato e limiti |
| --- | --- |
| PDF nativo | Testo Unicode, stile, geometria, immagini, tabelle semplici, pagine/sezioni verificati. Le interruzioni di riga originali restano esplicite. |
| OCR reale | Vision e MiniCPM verificati su due scansioni pulite e una pagina mista. Non verificati manoscritti, foto degradate, corpus amministrativi o documenti reali. |
| Xiaomi | Adapter verificato con mock HTTP; inferenza reale, prestazioni e qualità italiana **non verificate**. Pesi non installati. |
| MiniCPM | Pesi installati con consenso, hash verificati e inferenza reale Ollama/Metal M5 eseguita. CER/WER0 sulle due semplici scansioni, senza validazione generale. I prompt testuali non forniscono box affidabili: eventuali righe sono allineate alla segmentazione raster soltanto se il conteggio coincide, con provenienza esplicita. |
| Layout AI | Adapter PP-DocLayoutV3 locale; pesi e inferenza **non verificati**. ONNX valutato dalla documentazione, non integrato. |
| Fallback layout | Proiezioni geometriche, senza equivalenza semantica al modello. Il default OCR riconosce l'intera pagina per conservare il contesto; Vision fornisce box di riga. |
| Colonne | Inferenza di una–tre colonne native anche diseguali, bande estese e date in tabulazioni. Gutter irregolari, note laterali e oggetti intrecciati restano euristici. |
| Tabelle | Griglie native, merge, sfondi e padding misurati; bordi uniformati. Una tabella multipagina può diventare più tabelle Word. Tabelle senza bordi o scannerizzate richiedono detector/struttura OCR; non si promettono celle dal solo Vision. |
| Rotazione/crop | Formato pagina e coordinate del testo verificati. `find_tables` evitato su pagine ruotate/ritagliate a causa di un effetto collaterale verificato. Testo ruotato ricostruito a flusso, non nello stesso angolo. |
| Font | Famiglie e sostituzioni valutate anche sulle larghezze di fino a100 campioni; per font mancanti la scelta fra sei famiglie locali è esplicita e coerente con il font misurato. Non garantisce identità dei glifi. Quantizzazione Word e font mancanti possono modificare wrapping e box. Disponibilità sul PC destinatario non certificata; font incorporati non ridistribuiti. |
| Header/footer | Euristiche di bordo e ripetizione, parti Word editabili e distanze derivate dalle baseline. Numerazione e altri contenuti estratti restano letterali salvo campi esplicitamente ricostruiti. |
| Elenchi | Stile Word e marcatori originali editabili; rinumerazione automatica e gerarchie multilivello non ricostruite. |
| Immagini/grafica | Byte nativi conservati quando formato, maschere, clipping e rotazione lo consentono; altrimenti crop con motivo esplicito. Immagini ancorate autonome. Rettangoli e regole reali diventano DrawingML; curve, linee oblique e trasparenze complesse non sono riprodotte integralmente. I grafici con etichette non diventano semplice testo OCR. L'omissione del fondo di scansioni con testo già recuperabile può perdere grafica di sfondo; viene segnalata. |
| Formule | Native come testo Unicode; risultati OCR LaTeX con ritaglio originale e raw. Conversione semantica LaTeX→Office Math **non completata**. |
| Note/riferimenti | Contenuto testuale, senza veri footnote, endnote, link bibliografici o campi incrociati. |
| Qualità AI | Flag conservativi, secondo OCR opzionale con entrambe le versioni. MiniCPM-OCR Jev **non integrato**. Nessuna correzione semantica automatica. |
| Validazione | Struttura OOXML e rendering LibreOffice realmente eseguiti. Il benchmark usa lo stesso renderer per prima/dopo. Microsoft Word non è il renderer di queste misure; applicazioni compatibili possono reimpaginare. SSIM globale è accompagnato da primo piano, geometria e testo. |
| Geometria metrica | Matching uno-a-uno di parole esatte, con posizione per disambiguare ripetizioni. Si riportano copertura, baseline e percentili; parole mancanti non sono nascoste nei soli errori dei match. Scansioni senza testo nativo richiedono riferimenti separati. |
| Ottimizzazione | Ricerca locale limitata di Y e rientro X, senza cambiare dimensioni dei caratteri o contenuti. Miglior candidato conservato; può arrestarsi lontano dall'obiettivo. Non corregge ogni proprietà Word e non crea un ground truth geometrico per le scansioni. |
| Memoria | Picco RSS campionato ogni50ms, può perdere spike brevi; memoria processi figli solo quando accessibile. Server modelli esterni e memoria unificata GPU esclusi. Non è una misura dell'intera RAM del sistema. |
| Ripresa | Checkpoint per pagina; modello/configurazione identificati da nomi/versione, senza fingerprint dei pesi del server esterno. Usare `--no-resume` se si cambiano pesi dietro lo stesso alias. |
| Concorrenza | GUI serializzata per sicurezza MuPDF; benchmark multiprocesso. Nessuna promessa di speedup. |
| Privacy/sicurezza | Codice locale senza telemetria; Host/Origin, upload e percorsi protetti. Server OCR scelti dall'utente sono componenti separati. Nessun audit indipendente su PDF ostili. |
| Distribuzione | Installazione pulita verificata su Python3.12 macOS ARM64; MiniCPM/Metal Apple M5 effettivamente eseguito. Non testati Ubuntu, installer firmato/notarizzato o pacchetto `.app`. |

La modalità **visual** conserva pagine raster e le dichiara non modificabili. Non è un'alternativa presentata come DOCX editabile. Il PDF ricercabile è un formato supplementare: mantiene l'aspetto originale con testo invisibile approssimato, non una struttura Word.

# Verifica tecnica delle dipendenze

La verifica seguente documenta la prima versione e il setup OCR. Per le modifiche 0.2.0, la suite completa di 148 test e le misure geometriche aggiornate usare il [rapporto di ricostruzione](reconstruction-final-report.html) e la [descrizione del motore](geometric-engine.md). I vecchi SSIM con riallineamento e matching dei blocchi non sono la metrica della revisione corrente.

Verifica del 14 novembre 2026. Questo documento distingue disponibilità dichiarata
dai manutentori, import locale e inferenza realmente eseguita. La disponibilità di
una wheel non dimostra da sola che una pipeline con un determinato modello funzioni.

## Ambiente osservato

L'ambiente di sviluppo osservato è macOS 26.7.1 `arm64`, Python 3.12.14. Non è stato
identificato inizialmente il modello commerciale del chip. Il successivo
collaudo MiniCPM ha identificato Apple M5 e confermato inferenza Metal reale
dai log Ollama (vedere l'aggiornamento seguente).
Il repository usa un proprio ambiente `.venv`; non modifica gli altri progetti.

Versioni importate nell'ambiente di sviluppo:

| Pacchetto | Versione |
| --- | --- |
| PyMuPDF | 1.26.7 |
| python-docx | 1.2.0 |
| lxml | 6.1.1 |
| Pillow | 13.0.0 |
| NumPy | 2.3.5 |
| Pydantic | 2.14.3 |
| Typer | 0.29.1 |
| FastAPI | 0.163.0 |
| Uvicorn | 0.54.0 |
| pytest | 9.2.0 |
| httpx | 0.28.1 |
| python-multipart | 0.0.33 |
| psutil | 7.2.2 |

La documentazione `latest` può descrivere versioni successive a quelle bloccate
nel progetto. Le API usate devono essere verificate anche con la versione locale;
gli esiti della suite e delle conversioni sono registrati negli altri report.

Nella versione 1.26.7 è stato riprodotto un effetto collaterale di `find_tables()`
su una pagina con cropbox non banale e rotazione90: la chiamata modifica la
cropbox della pagina in memoria. La fixture `rotated_crop.pdf` e il test delle
coordinate del testo rilevano questa regressione. Il codice di estrazione deve
preservare il riferimento della pagina anche quando il detector di tabelle
modifica lo stato; un controllo del solo formato DOCX non sarebbe sufficiente.

## PDF e DOCX

PyMuPDF espone estrazione di testo e span, immagini, grafica vettoriale, rendering
e ricerca delle tabelle. Le coordinate restituite da estrazione testo e immagini
sono nel riferimento non ruotato; `rotation_matrix` e `derotation_matrix` servono
per trasformarle nel riferimento visualizzato. Il mantenimento di un unico
riferimento geometrico è quindi una scelta esplicita del modello intermedio.
Fonti: [API Page](https://pymupdf.readthedocs.io/en/latest/page.html),
[installazione ufficiale](https://pymupdf.readthedocs.io/en/latest/installation.html).

PyMuPDF e MuPDF sono distribuiti con una scelta tra AGPL e licenza commerciale.
Questo progetto open source adotta AGPL-3.0-or-later e non include il prodotto
commerciale PyMuPDF Office. La disponibilità del sorgente e i testi di licenza
devono essere mantenuti nella distribuzione.
Fonte: [licenze del manutentore](https://pymupdf.io/licensing).

python-docx 1.2.0 crea e modifica paragrafi, run, tabelle, sezioni, intestazioni,
piè di pagina e immagini. Non costituisce un motore di impaginazione di Word;
aprire il pacchetto DOCX con python-docx è una verifica strutturale, distinta dal
rendering in un'applicazione compatibile. La sua licenza è MIT.
Fonti: [documentazione](https://python-docx.readthedocs.io/en/latest/),
[licenza](https://github.com/python-openxml/python-docx/blob/master/LICENSE).

## PaddlePaddle e PP-DocLayoutV3

Le guide generali di PaddlePaddle consultate contengono indicazioni contrastanti
su ARM64. L'elenco dei file ufficiale di PaddlePaddle **3.3.1** su PyPI pubblica
wheel `macosx_11_0_arm64` per CPython 3.11 e 3.12, circa 104.5 MB ciascuna. È
quindi scorretto affermare che nessuna build macOS ARM64 esista. Ciò non verifica
PaddleX, gli operatori di PP-DocLayoutV3, l'inferenza completa o l'accelerazione
Metal. Fonti: [file ufficiali PyPI](https://pypi.org/project/paddlepaddle/3.3.1/),
[guida PaddleX](https://paddlepaddle.github.io/PaddleX/latest/en/installation/paddlepaddle_install.html).

La documentazione PaddleX 3.5 colloca PP-DocLayoutV3 nel modulo **Layout Analysis**.
L'API documentata è `create_model(model_name="PP-DocLayoutV3", model_dir=..., device="cpu")`,
seguita da `predict`. L'output comprende bounding box, classe, score e indice
`order`. Specificare solo il nome del modello può causare un download automatico:
il progetto richiede una directory modello locale esplicita. Il fallback
geometrico non ha le stesse capacità semantiche del detector AI.
Fonte: [Layout Analysis](https://paddlepaddle.github.io/PaddleX/3.5/en/module_usage/tutorials/ocr_modules/layout_analysis.html).

PaddleX è Apache-2.0; licenze e provenienza dei pesi restano da verificare per
ciascun artefatto effettivamente selezionato. Non si applica automaticamente la
licenza del codice a qualsiasi conversione di pesi trovata online.
Fonte: [licenza PaddleX](https://raw.githubusercontent.com/PaddlePaddle/PaddleX/develop/LICENSE).

Esiste un repository ONNX nell'organizzazione ufficiale PaddlePaddle. La guida
PaddleX descrive inoltre l'esportazione ONNX per modelli supportati. Questo
progetto non ha scaricato quei pesi e non dichiara verificati licenza del singolo
checkpoint, firme I/O, postprocessing, operatori o esecuzione ARM64. ONNX resta
un percorso di integrazione da collaudare, non una sostituzione presentata come
completata. Fonti: [repository ONNX](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/tree/main),
[esportazione PaddleX](https://paddlepaddle.github.io/PaddleX/latest/en/pipeline_deploy/paddle2onnx.html).

## Interfaccia locale e manutenzione

FastAPI documenta l'esecuzione attraverso un server ASGI come Uvicorn. Il
progetto restringe il listener a loopback; l'esempio pubblico `0.0.0.0` delle
guide generiche non è il valore predefinito del progetto. FastAPI è MIT.
Fonti: [esecuzione del server](https://fastapi.tiangolo.com/deployment/manually/),
[licenza](https://raw.githubusercontent.com/fastapi/fastapi/master/LICENSE).

Le versioni di questo documento sono una fotografia dell'ambiente osservato.
Gli aggiornamenti devono passare per un ambiente separato e la suite di
regressione; non sono attivati aggiornamenti automatici o telemetria. Le
prestazioni pubblicate da altri progetti, su GPU diverse o checkpoint diversi,
non sono misure di questa applicazione.

Gli adapter Xiaomi e MiniCPM, i prompt e lo stato dell'inferenza sono descritti
separatamente in `ocr-backends.md`. Il collaudo OCR italiano deve essere distinto
dal supporto linguistico dichiarato nei model card e dall'OCR inglese.

## Collaudo sintetico della ricostruzione

Sono state generate 14 fixture PDF originali, con tre file di ground truth. La
suite di integrazione contiene 26 casi: ispezione, OCR simulato, testo Unicode,
stili, ordine colonne, tabelle native e merge, immagini, intestazioni/piè di
pagina, elenchi, formati, cropbox/rotazione, formule conservate, modalità visual,
PDF ricercabile e rifiuto di input/limiti/collisioni. I primi controlli hanno
individuato e fatto correggere sia il raggruppamento di righe di colonne diverse
da parte di MuPDF sia il cambio di cropbox provocato dal detector di tabelle.

Sono state convertite e renderizzate con il LibreOffice locale quattro fixture:
`native`, `columns`, `table` e `headers`. È stato eseguito anche `render_docx.py`
del runtime di authoring, e sono state aperte e controllate tutte le sei PNG
prodotte: testo leggibile, nessun clipping, tabella con celle editabili e
intestazioni/piè di pagina su tre pagine. Il numero di pagine è rimasto uguale.

Misure registrate dal confronto a 100 DPI, stesso canvas bianco e traslazione
limitata, senza stretching:

| Fixture | Pagine PDF / DOCX renderizzato | SSIM | Scostamento medio blocchi abbinati |
| --- | --- | --- | --- |
| native | 1 / 1 | 0.99187 | 2.61 pt, 5 blocchi |
| columns | 1 / 1 | 0.96524 | 3.52 pt, **solo 1 blocco** |
| table | 1 / 1 | 0.95570 | 7.73 pt, 4 blocchi |
| headers | 3 / 3 | 0.99156 circa su ciascuna pagina | 6.82 pt, 4 blocchi per pagina |

Il confronto geometrico abbina testo in modo euristico: nel caso multicolonna
la suddivisione diversa dei blocchi ha consentito un solo abbinamento, quindi
quel valore non descrive l'intero layout. I PDF sintetici contengono molto
spazio bianco: SSIM alto non dimostra accuratezza OCR né qualità su documenti
densi. Questi risultati costituiscono misure del campione, non soglie garantite.

Questa tabella fotografa la prima verifica. La revisione finale conserva font
e stile dei run nelle celle e stima anche l'allineamento verticale; il caso
`table` passa a SSIM0.95807. Intestazioni/piè di pagina usano ancora distanze
semplificate. I dati finali sono in `benchmarks.md` e `benchmark-results.json`.
Il risultato è editabile e leggibile, ma non una replica identica della pagina.
Word su Microsoft Office non è stato avviato: la prova del renderer è con
LibreOffice.

## Installazione pulita e verifiche finali

Il 15 novembre 2026 è stato creato `.venv-verify` con Python3.12.14 **senza**
`--system-site-packages` ed eseguito `pip install -c constraints-macos-arm64.txt
-e '.[test]'`. Tutte le dipendenze sono state risolte e installate; `pip check`
risponde `No broken requirements found`. La fotografia completa, comprese le
dipendenze transitive, è `requirements-lock-macos-arm64.txt`.

La CLI è stata eseguita realmente con `doctor`, `convert --json`, `inspect` e
`benchmark`; JSON viene verificato come oggetto parsabile. Il flusso web è
provato sia con job simulati sia con una conversione nativa reale tramite
TestClient; il frontend è stato aperto e ispezionato in Chrome. I test delle
due API VLM restano simulati e non dimostrano inferenza dei checkpoint.

Il benchmark finale passa 14/14 documenti sintetici. I test opt-in Vision sono
stati eseguiti fuori dal sandbox dell'agente con 3/3 passati; la suite completa
ha prodotto inizialmente 69 passati (66 passati e 3 saltati senza opt-in).
In questa prima fase non è stata richiesta alcuna installazione di sistema o
download di pesi. Un wheel Python è stato
costruito e verificato: include sorgenti, helper Swift, frontend e licenza.

## Aggiornamento MiniCPM dopo autorizzazione

Il 15 novembre 2026 l'utente ha autorizzato il download e la configurazione dei
pesi. I tre GGUF ufficiali, revisioni e hash in `scripts/minicpm-models.json`,
sono stati scaricati e verificati; Ollama0.40.16 già presente è usato su una
seconda istanza loopback18499 con store nel repository. L'istanza11434 è rimasta
attiva. Nessun nuovo componente o servizio di sistema installato.

Inferenza MiniCPM riuscita su scansioni it/en e pagina mista, oltre a un job
attraverso la GUI preesistente sulla8765. Sono stati riaperti e renderizzati i
DOCX risultanti. I log confermano Metal/Apple M5, target25/25 layer su GPU,
draft6/6 e statistiche DSpark. CER/WER0 sui due minuscoli ground truth, senza
generalizzazione a documenti reali. Il layout è semplificato per l'assenza di
box di parola/riga nel risultato MiniCPM.

La suite completa aggiornata, con `PDF2DOCX_REAL_OCR=1` e
`PDF2DOCX_REAL_MINICPM=1`, ha prodotto **77 passati in13.07s**. Dati portabili
in `minicpm-verification.json`; setup e gestione server in `setup-minicpm.md`.

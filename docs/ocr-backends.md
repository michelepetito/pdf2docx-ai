# Backend OCR locali e layout

Prima verifica tecnica il14novembre2026, aggiornamento MiniCPM il15novembre.
MiniCPM è ora installato e verificato con inferenza reale dopo autorizzazione;
Xiaomi resta verificato soltanto con risposte HTTP simulate. Nessun demone di
sistema installato: il server MiniCPM è un processo locale separato.

## Contratto e selezione

`OCREngine` espone `initialize()`, `recognize(PIL.Image, region_type, language)`,
`health_check()` e `shutdown()`. I bounding box di `OCRResult.words` sono pixel
relativi al crop ricevuto. Il convertitore deve applicare l'offset del crop e
la trasformazione pixel/punti PDF. La confidenza resta `null` se il runtime non
la fornisce; la confidenza dichiarata dal modello non equivale a precisione
misurata su un corpus.

`auto` sceglie il primo backend disponibile nel seguente ordine fisso:
Xiaomi, MiniCPM, Apple Vision, Tesseract. Un modello deve risultare effettivamente
presente nell'elenco del server. La scelta esplicita di un motore non cambia
motore silenziosamente in caso di errore. Il convertitore nativo non ha bisogno
di inizializzare alcun OCR. `compare` richiede due esecuzioni separate, con
artefatti distinti: la lunghezza dell'output non è un criterio di selezione.

Le connessioni OCR accettano esclusivamente HTTP verso IP numerici loopback
(`127.0.0.1`, altri indirizzi loopback IPv4, `::1`). Proxy di ambiente e redirect
sono disabilitati. Gli adapter non invocano API di download. I server sono
gestiti dall'utente e devono essere configurati in modalità locale: questo
client non può certificare il comportamento interno di un servizio esterno al
proprio processo.

## Apple Vision

Il backend aggiuntivo `vision` usa `VNRecognizeTextRequest` con livello
`accurate`, lingue `it-IT` e/o `en-US`, correzione linguistica disabilitata.
Una piccola interfaccia Swift inclusa nel pacchetto viene compilata lazy nella
cartella locale `.pdf2docx-cache/vision/`; richiede macOS e Xcode Command Line
Tools già installati. Non installa strumenti né modifica impostazioni di
sistema. Vision decide le risorse hardware: non attribuiamo al backend uso
verificato di GPU Metal o Neural Engine.

I box sono di **righe intere**, esposti nel campo comune `words` con ID `line`.
Questo backend non rileva struttura semantica, griglie di tabelle o formule.
L'OCR è reale; font e struttura richiedono ricostruzione geometrica separata.

Prova reale su macOS ARM64, Python 3.12.14, rendering PyMuPDF a 180 dpi:

| Fixture sintetica | Lingua | Secondi OCR | CER | WER |
| --- | --- | ---: | ---: | ---: |
| `tests/fixtures/generated/scan_it.pdf` | italiano | 0.277628 | 0.0 | 0.0 |
| `tests/fixtures/generated/scan_en.pdf` | inglese | 0.231971 | 0.0 | 0.0 |

CER/WER calcolati con distanza di Levenshtein dopo normalizzazione degli spazi;
le stringhe di riferimento `.txt` accompagnano le fixture. Sono due pagine
pulite di tre righe ciascuna, non un benchmark generale. La compilazione Swift
era già completata e non è inclusa nei tempi. I test hanno richiesto esecuzione
fuori dal sandbox dell'agente: al suo interno Vision restituiva
`Foundation._GenericObjCError error 0`. Un normale terminale macOS non usa quel
sandbox. Un errore analogo viene propagato esplicitamente.

Documentazione Apple:
[VNRecognizeTextRequest](https://developer.apple.com/documentation/vision/vnrecognizetextrequest).
Vision è un framework proprietario di sistema opzionale, non viene redistribuito:
l'applicazione e gli altri backend rimangono sorgenti aperti; su Linux usare un
runtime locale dei modelli o Tesseract.

## Xiaomi-OCR-0

Il repository richiesto `xiaomi-research/Xiaomi-OCR-0` rimanda attualmente al
repository [SeerRay-Lab/Xiaomi-OCR-0](https://github.com/SeerRay-Lab/Xiaomi-OCR-0).
Codice upstream: Apache-2.0, copyright Xiaomi Corporation 2026. La configurazione
di default usa `longwayxu/xiaomi-ocr-0:bf16` su `http://127.0.0.1:11434/v1`.
È un pacchetto GGUF comunitario che upstream classifica sperimentale; nessuna
equivalenza con i punteggi del checkpoint originale è stata verificata qui.

L'adapter riproduce la ricetta documentata nel
[trasporto Ollama ufficiale](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/main/pipeline/ollama_backend.py)
e nel [preprocessing](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/main/evaluation_pipeline/cropping.py):
RGB, orientamento EXIF, limite iniziale lato lungo 2048 pixel, griglia 32 pixel,
limiti dinamici di area, template raw single-image senza thinking e decoding
deterministico. Il percorso Ollama usa `/api/generate` con `raw=true`;
il percorso OpenAI compatibile usa `/v1/chat/completions` con thinking
disabilitato. Non trattiamo questi due percorsi come numericamente identici.

Usiamo prompt distinti verificati nel
[server ufficiale](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/main/skills/xiaomi-ocr/mcp_ocr_server.py)
per testo, tabelle OTSL e formule LaTeX. Il convertitore OTSL locale segue i
significati di cella e continuazione descritti nel
[postprocessor ufficiale](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/main/postprocess/otsl.py):
preserva celle unite, rifiuta griglie incoerenti e conserva sempre l'output raw.
È una implementazione indipendente; non elimina ripetizioni né riscrive parole.
Lo shutdown invia `keep_alive=0` solo se l'adapter ha effettuato inferenza Ollama.

Per installare il modello, prima autorizzare il download e consultare la
[guida Ollama upstream](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/main/OLLAMA.md).
La guida riporta verifiche con Ollama 0.35.0; qui né Ollama né questi pesi sono
presenti. Non abbiamo eseguito inferenza Xiaomi, misurato qualità italiana o
prestazioni del GGUF.

## MiniCPM-OCR 1.0

[Repository ufficiale](https://github.com/OpenBMB/MiniCPM-OCR), codice Apache-2.0,
copyright OpenBMB. L'SDK `minicpm-ocr` risulta alla versione 1.0.5 nelle release
upstream lette. L'adapter è a livello di crop: riusa le
[ricette prompt dell'SDK](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/sdk/minicpmvocr/prompts.py)
e i [dialetti di trasporto](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/sdk/minicpmvocr/backends/dialects.py),
senza richiamare la pipeline SDK completa e duplicarne il rilevamento layout.
Le immagini viaggiano come PNG lossless; slicing e proiettore sono del runtime.

L'endpoint predefinito è `http://127.0.0.1:18499/v1`, alias `minicpm-ocr`.
Il controllo locale identifica Ollama tramite `/api/tags` oppure un server
OpenAI compatibile tramite `/v1/models`, richiedendo l'alias configurato.
Riconoscimento distinto di testo, tabelle HTML e formule LaTeX; output troncato
o vuoto causa errore, non una conversione presentata come completa.

Upstream fornisce istruzioni per
[llama.cpp b11901 e Metal su Apple Silicon](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/llamacpp_deploy.md)
e [Ollama 0.40.12+](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy.md).
La configurazione documentata richiede modello principale, proiettore visivo e
draft DSpark abbinati. Il15novembre, dopo consenso, sono stati scaricati i tre
pesi ufficiali con SHA-256 verificati e registrati nell'Ollama0.40.16 già
installato, con store nel repository e porta18499. Inferenza reale su Metal/M5
eseguita: scansioni it/en e pagina mista producono Word editabile. CER/WER0 sui
due piccoli ground truth; l'italiano non fa parte del supporto cinese/inglese
dichiarato e richiede comunque validazione su un corpus rappresentativo.
Dettagli e limiti geometrici in [setup MiniCPM](setup-minicpm.md).

## Tesseract

Fallback CLI opzionale con TSV contenente parole, righe, box e confidenza.
Richiede eseguibile e language data già presenti (`ita`, `eng`).
Nessuna installazione automatica. In questo ambiente l'eseguibile non è
disponibile e l'inferenza Tesseract non è stata eseguita.

## Layout

`LayoutDetector.detect(image, page_number=1)` restituisce regioni con box pixel.
`GeometricLayoutDetector` usa proiezioni raster e spazi vuoti per trovare bande
e, quando evidente, una separazione in colonne. Non è equivalente al modello
AI, non classifica semanticamente titoli, tabelle o formule e non deve essere
presentato come tale. È disponibile senza OpenCV o modelli.

`PPDocLayoutDetector` implementa l'API PaddleX `create_model` e `predict`,
classi/box/confidenza e ordine originale. Accetta solo una directory locale
contenente `inference.yml` e `inference.pdiparams`; non scarica modelli.
L'adapter limita esplicitamente il device a CPU. Non abbiamo installato Paddle
né eseguito PP-DocLayoutV3. La presenza di wheel macOS ARM64 PaddlePaddle
3.3.1 su [PyPI](https://pypi.org/project/paddlepaddle/3.3.1/) non prova che l'intera
pipeline PaddleX/V3 funzioni sul target; alcune guide ufficiali generali
riportano indicazioni ARM discordanti. Non viene perciò etichettato come
incompatibile in assoluto o come funzionante senza prova.

All'inizializzazione l'adapter imposta solo nel processo corrente
`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` e `HF_HUB_OFFLINE=1`, prima di
importare PaddleX, per evitare controlli di raggiungibilità degli host dei
modelli. Non scrive configurazioni esterne al repository.

L'API è verificata contro
[l'adapter PaddleX upstream MiniCPM](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/sdk/minicpmvocr/layouts/ppdoclayout3_paddlex.py).
Input BGR, regione in pixel, etichette e punteggi vengono conservati; il
poligono è conservato nei metadati, ma il ritaglio poligonale non è implementato.
L'eventuale percorso ONNX resta da validare: non viene costruito un adapter da
nomi o forma dei tensori ipotizzati.

MiniCPM-OCR Jev non è integrato. Non vengono inventati score di affidabilità.

## Test eseguiti

`PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_ocr_backends.py -q`:
19 test passati. Coprono selezione deterministica/lazy, rifiuto URL esterni,
redirect, presenza effettiva del modello, prompt delle tabelle, preprocessing
Xiaomi, output troncato, OTSL e assenza di pesi layout. Le prove Apple Vision
reali sono riportate separatamente sopra; i test HTTP non fingono inferenza.


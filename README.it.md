# PDF2DOCX AI Fidelity

[English](README.md) · **Italiano**

Convertitore locale PDF → Word modificabile con interfaccia web, riga di comando, OCR opzionale e misure di qualità. **Versione 0.3.1.** Per PDF nativi o OCR Tesseract non servono account cloud né GPU. L'interfaccia web attuale è in italiano.

Il Word usa paragrafi, sezioni, colonne, tabulazioni, vere tabelle e immagini indipendenti. Aspetto, precisione testuale, geometria e modificabilità restano separati: SSIM 0,99 non certifica il 99% di fedeltà.

## Requisiti

| Componente | Utilizzo |
| --- | --- |
| Git + Python **3.12** a 64 bit | Obbligatori; sono accettati Python 3.11–3.13 |
| LibreOffice | Consigliato: ottimizzazione del layout, rendering DOCX e verifica visiva/delle modifiche |
| Tesseract + dati `ita`/`eng` | OCR delle scansioni sui tre sistemi; non necessario per PDF nativi |
| Apple Vision / Ollama + MiniCPM | Motori OCR alternativi opzionali |

Usare Python per l'architettura della macchina. Destinazioni native comuni: **macOS Intel/Apple Silicon, Linux x86_64/ARM64, Windows x64**. Su Windows ARM64 si può usare Python/runtime x64 in emulazione oppure Linux ARM64 in WSL2, secondo la disponibilità delle dipendenze. Sistemi arbitrari a 32 bit e qualsiasi GPU non sono garantiti; consultare il [supporto wheel di PyMuPDF](https://pymupdf.readthedocs.io/en/latest/installation.html).

## 1. Installare i prerequisiti una volta

### macOS

Con [Homebrew](https://brew.sh/) già disponibile:

```bash
brew install git python@3.12 tesseract tesseract-lang
brew install --cask libreoffice
```

Senza Homebrew, installare separatamente [Python](https://www.python.org/downloads/), [Git](https://git-scm.com/downloads), [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) e [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html). Scegliere le versioni Intel o Apple Silicon appropriate. Non sono necessari Codex o il suo runtime.

### Linux — Ubuntu 24.04 / famiglia Debian

```bash
sudo apt update
sudo apt install -y git python3 python3-venv libreoffice-writer tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng fontconfig fonts-liberation
python3 --version
```

Ubuntu 24.04 fornisce Python 3.12. Su altre distribuzioni installare pacchetti equivalenti e verificare che Python sia 3.11–3.13. Installare i font del documento originale quando la licenza lo consente.

### Windows — PowerShell

Installare [Git](https://git-scm.com/download/win), [Python 3.12](https://www.python.org/downloads/windows/), [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) e un [installer Tesseract indicato dal progetto ufficiale](https://tesseract-ocr.github.io/tessdoc/Installation.html#windows). Includere i dati OCR italiani e inglesi, poi riaprire PowerShell.

Le installazioni standard in `Program Files` di LibreOffice e Tesseract vengono rilevate automaticamente. Per percorsi personalizzati aggiungere le cartelle degli eseguibili al `PATH` utente. `doctor --json` controlla gli eseguibili rilevati e le lingue OCR.

## 2. Clonare e installare

**macOS / Linux:**

```bash
git clone https://github.com/michelepetito/pdf2docx-ai.git
cd pdf2docx-ai
python3.12 scripts/bootstrap.py
source .venv/bin/activate
```

Su Ubuntu 24.04 va bene anche `python3 scripts/bootstrap.py`. Se necessario, Python Homebrew si trova in `"$(brew --prefix python@3.12)/bin/python3.12"`.

**Windows:**

```powershell
git clone https://github.com/michelepetito/pdf2docx-ai.git
cd pdf2docx-ai
py -3.12 scripts/bootstrap.py
.\.venv\Scripts\Activate.ps1
```

Se l'attivazione è bloccata, usare `.\.venv\Scripts\python.exe -m pdf2docx_ai ...` al posto di `pdf2docx-ai ...`: non serve modificare la execution policy. Su macOS/Linux l'equivalente è `.venv/bin/python -m pdf2docx_ai ...`.

Il bootstrap crea soltanto `.venv`, installa il progetto con le [versioni applicative condivise](constraints.txt) ed esegue `pip check`. Non installa programmi di sistema, scarica pesi OCR o avvia servizi. Aggiungere `--dev` per i test o `--venv .venv-other` per un ambiente separato.

Installazione manuale in un ambiente Python attivato:

```bash
python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[test]"
python -m pip check
```

Le wheel native vengono scelte per la piattaforma in uso. [requirements-lock-macos-arm64.txt](requirements-lock-macos-arm64.txt) conserva il freeze completo del Mac originario e non è un lock universale. Salvare l'ambiente risolto completo con `python -m pip freeze > requirements-local.txt`.

## 3. Usare l'interfaccia web

```bash
pdf2docx-ai doctor --json
pdf2docx-ai serve
```

Aprire **[http://127.0.0.1:8765](http://127.0.0.1:8765)**. Caricare un PDF, scegliere lingua/motore, mantenere la modalità **editable**, convertire e scaricare Word e rapporto. Nelle opzioni avanzate, **«Verifica una modifica al Word»** prova una modifica ordinaria su una copia.

Per le scansioni, Tesseract è il percorso comune più semplice. `auto` verifica Xiaomi → MiniCPM → Vision → Tesseract. L'assenza di motori opzionali non impedisce di convertire PDF nativi; un motore scelto esplicitamente e non disponibile produce un errore diagnostico.

Arrestare con **Ctrl+C**; **scaricare prima i risultati**, perché i file della sessione web vengono eliminati alla chiusura. Per un'altra porta: `pdf2docx-ai serve --port 8766`. Il server ascolta soltanto su loopback e usa risorse frontend locali.

## 4. Esempi — Bash e PowerShell

```bash
# PDF nativo: nessun modello OCR necessario
pdf2docx-ai convert input.pdf --output output.docx
# Scansione italiana: OCR CPU, PDF ricercabile e verifica visiva
pdf2docx-ai convert scan.pdf --engine tesseract --language it --output scan.docx --searchable-pdf --validate-visual
# Entrambe le lingue
pdf2docx-ai convert bilingual.pdf --engine tesseract --language it+en --output bilingual.docx
# Prova reale di modifica, sempre su una COPIA
pdf2docx-ai convert input.pdf --output checked.docx --validate-editability
# Verifica di un Word esistente
pdf2docx-ai validate input.pdf output.docx --output validation.html --edit-probe
# Accuratezza OCR rispetto a un riferimento indipendente completo
pdf2docx-ai validate scan.pdf scan.docx --ground-truth reference.txt --output ocr-validation.html
# Confronto con una valutazione precedente dello STESSO PDF
pdf2docx-ai validate input.pdf output.docx --previous validation.json --output comparison.html
# Conversione più rapida
pdf2docx-ai convert input.pdf --output quick.docx --no-optimize-layout
```

Per nomi di output esistenti serve `--overwrite`, che archivia il precedente rapporto di qualità. `--renderer "percorso/soffice"` sceglie il renderer per `convert`/`validate`; l'app web usa il rilevamento automatico. Altre opzioni: `pdf2docx-ai --help` e `pdf2docx-ai convert --help`.

**Esempi subito disponibili:**

```bash
python tests/fixtures/generate.py tests/fixtures/generated
pdf2docx-ai convert tests/fixtures/generated/native.pdf --output examples/output/demo-native.docx
pdf2docx-ai convert tests/fixtures/generated/scan_it.pdf --engine tesseract --language it --output examples/output/demo-scan.docx --ground-truth tests/fixtures/generated/scan_it.txt --validate-visual
```

## 5. Output e qualità

| File | Contenuto |
| --- | --- |
| `output.docx` | Documento Word modificabile |
| `output.quality.html` / `.json` | Misure, avvisi, confronti, overlay e differenze quando il rendering è disponibile |
| `output.model.json` | Layout, coordinate e provenienza OCR |
| `output.searchable.pdf` | Solo con `--searchable-pdf`: aspetto originale più livello testuale OCR |
| `output.work/` | Cache per ripresa/anteprime; può contenere copie dei documenti |

Quattro dimensioni separate: **SSIM per pagina/globale/primo piano**, **CER/WER esatti, valori e ordine di lettura**, **IoU/geometria in pt/mm per otto categorie** e **struttura Word/prova di modifica**. I target iniziali—SSIM≥0,990, CER≤0,1%, mediana geometrica≤1 mm, P95≤2 mm—sono sperimentali. Riferimenti o renderer assenti producono misure esplicitamente indisponibili. La modalità `visual` crea intenzionalmente pagine immagine non modificabili in `.visual.docx`.

## 6. MiniCPM-OCR 1.0 opzionale — macOS, Linux, Windows

Installare [Ollama](https://ollama.com/download) e rendere `ollama` disponibile nel `PATH`. Il setup con modello principale/proiettore/DSpark richiede **Ollama≥0.40.12**, secondo la [guida ufficiale OpenBMB](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy.md). Download: **circa 2,04 GB**; prevedere almeno **6 GB liberi su disco** per pesi/import, oltre alle esigenze del runtime. L'accelerazione GPU dipende da runtime e driver; l'inferenza CPU può essere lenta.

Dalla radice del repository, nell'ambiente attivato:

```bash
python scripts/setup_minicpm.py
# Download esplicito: revisioni fissate e verifica SHA-256
python scripts/setup_minicpm.py --download-models
# Terminale A: lasciare aperto
python scripts/serve_minicpm.py
```

Nel **terminale B**, attivare lo stesso ambiente:

```bash
python scripts/setup_minicpm.py --register
pdf2docx-ai doctor --json
pdf2docx-ai convert tests/fixtures/generated/scan_it.pdf --engine minicpm --language it --output examples/output/demo-minicpm.docx --ground-truth tests/fixtures/generated/scan_it.txt --validate-visual
pdf2docx-ai serve
```

Generare prima le fixture della sezione 4. Endpoint: `http://127.0.0.1:18499`, alias `minicpm-ocr`, pesi/store nella cartella `models/` esclusa da Git. Ctrl+C nel terminale A arresta soltanto il suo server. Una porta occupata viene rifiutata; altre istanze restano intatte. I precedenti launcher `.command` sono specifici di macOS.

Per un'istanza locale già configurata: `pdf2docx-ai serve --minicpm-url http://127.0.0.1:11434/v1 --minicpm-model minicpm-ocr`. Cambiare URL non installa il modello. Sono ammessi solo indirizzi loopback numerici. [Evidenze del setup originario](docs/setup-minicpm.md).

Apple Vision: macOS + Xcode Command Line Tools, quindi `--engine vision`. Xiaomi e PP-DocLayoutV3 sono adapter opzionali; l'inferenza reale non era stata verificata nel rilascio originario. [Dettagli dei backend](docs/ocr-backends.md).

## 7. Test e riproducibilità

```bash
python -m pip install -c constraints.txt -e ".[test]"
python -m pytest -m "not real_ocr and not complex and not renderer" -q
# Con LibreOffice installato:
python -m pytest -m "not real_ocr and not complex" -q
```

La verifica locale attuale della 0.3.1 ha superato **179 test**: [verifica](docs/portability-local-verification.json), [JUnit completo](docs/portability-full-tests.xml), [evidenze CI multipiattaforma](docs/portability-ci-verification.json).

La [CI](https://github.com/michelepetito/pdf2docx-ai/actions) copre Linux x64/ARM64, macOS Intel/ARM64 e Windows x64, con una prova Linux di rendering/OCR. Consultare gli esiti effettivi per le combinazioni verificate; non scarica pesi VLM. Il collaudo macOS storico della 0.3.0 ha superato **174 test** con Vision/MiniCPM reali e documenti complessi: [JUnit](docs/validation-test-results.xml), [verifica](docs/validation-verification.json).

Per generare e verificare un CV europeo complesso sulla propria macchina:

```bash
python scripts/generate_complex_corpus.py
pdf2docx-ai convert tests/fixtures/complex/generated/europass_fictitious.reference.pdf --output examples/output/europass-geometric.docx --validate-editability
```

Font e renderer possono cambiare l'impaginazione. Gli script storici `evaluate_reconstruction.py` e `evaluate_validation.py` richiedono conversioni congelate in `examples/output/`, esclusa da Git: l'archivio di output di diversi GB non è nel repository. Generare nuove conversioni come sopra. I riepiloghi HTML storici incorporano anteprime; alcuni link a report individuali e percorsi assoluti appartengono alla macchina originaria e non sono prerequisiti d'installazione.

## Risoluzione problemi

| Sintomo | Intervento |
| --- | --- |
| Python assente / 3.14+ | Installare/selezionare Python 3.12 e riaprire il terminale |
| Nessuna wheel compatibile | Verificare Python a 64 bit, architettura e disponibilità upstream; su Windows ARM provare emulazione x64/WSL2 |
| Comando non trovato | Attivare `.venv` o usare il suo Python con `-m pdf2docx_ai` |
| LibreOffice indisponibile | Installarlo; usare percorso standard, `PATH` o `--renderer` nella CLI |
| Lingua OCR assente | Installare `ita`/`eng`; controllare `doctor --json` e `tesseract --list-langs` |
| Connessione MiniCPM rifiutata | Avviare il server, registrare i pesi e ricontrollare i motori |
| Layout diverso su un altro PC | Allineare font/renderer e consultare tutte e quattro le dimensioni |

## Limiti e licenza

Pubblicazioni complesse, testo ruotato, font mancanti e decorazioni ancorate alla pagina hanno ancora limiti di fedeltà/modifica. La prova sul CV rileva due intersezioni linea/titolo nonostante testo e oggetti integri. Microsoft Word non era il renderer del collaudo storico. Vedere [limiti](docs/limitations.md), [metodologia](docs/validation-methodology.md), [rapporto comparativo](docs/validation-final-report.md) e [architettura](docs/architecture.md).

Sorgente: [src/](src/), [tests/](tests/), [scripts/](scripts/); snapshot storici in `examples/`. Git esclude ambienti, pesi binari, cache, output generati e distribuzioni. Gli script di setup e il manifest dei modelli sono inclusi. L'installazione scarica pacchetti/modelli richiesti esplicitamente; la conversione dei documenti è locale.

**AGPL-3.0-or-later**: [LICENSE](LICENSE), [attribuzioni](THIRD_PARTY_NOTICES.md). Le fixture pubbliche PLOS/Eurostat hanno [attribuzione](tests/fixtures/complex/public/manifest.json) CC BY 4.0 separata; dati/ritratto del CV sono sintetici. Le licenze dei modelli restano separate.

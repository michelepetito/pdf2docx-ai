# Installazione su macOS

Ambiente verificato: macOS 26.7.1, ARM64, Python 3.12.14. Il successivo collaudo MiniCPM ha identificato Apple M5 e confermato inferenza Metal nei log Ollama; non è stata misurata la RAM totale del sistema. Il Python `/usr/bin/python3` osservato era 3.9.6 e non è adatto a questo progetto. Usare un Python 3.12 ARM64 già installato, senza modificare altri ambienti.

```bash
cd /Users/jacklondon/Documents/ChatGPT/Codex/pdf2docx-ai
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-lock-macos-arm64.txt -e '.[test]'
python -m pip check
pdf2docx-ai doctor --json
python -m pytest -q
pdf2docx-ai serve
```

In questa workspace il runtime 3.12 era disponibile nel bundle Codex ed è stato usato per creare `.venv` e l'ambiente pulito `.venv-verify`. Sono entrambi pronti; preferire quest'ultimo per riprodurre il collaudo:

```bash
source .venv-verify/bin/activate
pdf2docx-ai serve --port 8765
```

Il file `scripts/start.command` avvia `.venv/bin/pdf2docx-ai serve` con doppio clic o da terminale. Non apre porte sulla LAN. Alla chiusura il servizio elimina la directory temporanea della sessione web, compresi i risultati non scaricati.

## OCR senza download di modelli

`--engine vision` richiede macOS e Xcode Command Line Tools già presenti (`xcrun --find swiftc`). Il primo avvio compila il bridge incluso nel pacchetto. Non viene avviato `xcode-select --install` automaticamente. Lingue sperimentate: italiano e inglese su fixture sintetiche. Correzione linguistica disattivata.

```bash
pdf2docx-ai convert scansione.pdf --engine vision --language it --output scansione.docx
```

## Renderer opzionale

L'ottimizzazione geometrica della versione 0.2.0 è attiva per impostazione predefinita e usa LibreOffice headless con un profilo temporaneo isolato. La ricerca privilegia il runtime incluso in Codex quando disponibile. In questa workspace viene usato `/Users/jacklondon/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice`. È possibile indicare un eseguibile con `--renderer /percorso/soffice`; non viene installato LibreOffice automaticamente. Senza renderer si conserva il DOCX iniziale e si registra l'indisponibilità. `--no-optimize-layout` disattiva il ciclo; `--validate-visual` richiede il confronto anche senza ottimizzazione.

## Modelli AI opzionali

Non sono necessari per convertire PDF nativi o usare Vision. Per Xiaomi/MiniCPM seguire le fonti ufficiali in `ocr-backends.md`, dopo aver autorizzato personalmente runtime e download dei pesi. I modelli GGUF richiedono il proiettore visivo abbinato e versioni runtime compatibili: il semplice nome di un modello non garantisce inferenza funzionante.

Nella workspace MiniCPM è ora installato con consenso e collaudato su Ollama
0.40.16, porta 18499. Avvio/arresto e verifica sono in [setup MiniCPM](setup-minicpm.md).
Non è necessario riscaricare i pesi per riavviare il server.

Per PP-DocLayoutV3 usare un **ambiente separato** per verificare prima PaddlePaddle/PaddleX e i pesi locali. Esistono wheel Paddle macOS ARM64, ma l'intera inferenza V3 non è stata eseguita qui. Non si dichiara accelerazione Metal per Paddle. Il client richiede `--layout ppdoclayout --layout-model-dir /directory/locale` e non deve ricevere solo un identificativo remoto.

## Linux

Il core è Python e le dipendenze dispongono anche di distribuzioni Linux, ma Ubuntu non è stato collaudato in questa consegna. Vision è escluso; usare Tesseract già installato con dati `ita`/`eng`, oppure server locali Xiaomi/MiniCPM verificati sulla propria macchina. Rigenerare il lock per piattaforma prima di dichiarare una nuova installazione supportata.

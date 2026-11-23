# MiniCPM OCR locale: diagnosi e installazione esplicita

Il messaggio `Connection refused` su `127.0.0.1:18499` significa che a
quell'indirizzo non risponde il server richiesto dal client. La voce MiniCPM
nella GUI seleziona l'adapter e non installa modello o runtime.

Controllo reale del 15 novembre 2026: Ollama **0.40.16** risponde sulla porta
**11434**, con elenco modelli vuoto. Sulla **18499** la connessione viene
rifiutata. Cambiare solamente porta non basta: manca anche il modello.
Questa è una fotografia della macchina al momento della diagnosi.

La GUI corretta interroga `/api/engines`, mostra “non disponibile” per i
backend assenti e consente di ricontrollare dopo aver avviato il runtime.
I messaggi distinguono server assente e modello non installato. Il client
non sostituisce un motore scelto esplicitamente. I PDF nativi restano
convertibili senza inizializzare alcun OCR.

Per usare subito l'OCR già collaudato su questo Mac scegliere **Apple Vision**
oppure **Automatico**. Per vedere le modifiche nella sessione già avviata,
scaricare prima gli eventuali risultati, arrestare il server web con Ctrl-C
e avviarlo nuovamente; poi ricaricare la pagina. Non è stata arrestata
automaticamente la sessione utente, perché la chiusura elimina i suoi job
temporanei.

## Piano predisposto, senza download automatico

Il piano è leggibile senza rete e senza creare alcun modello:

```bash
.venv-verify/bin/python scripts/setup_minicpm.py
```

`scripts/minicpm-models.json` fissa tre file ufficiali OpenBMB della stessa
release, revisioni immutabili, dimensioni e SHA-256 LFS. Metadati e licenza
Apache-2.0 verificati sui repository ufficiali, senza scaricare i binari.

| File | Byte |
| --- | ---: |
| MiniCPM-OCR-1_0-Q8_0.gguf | 811598432 |
| mmproj-model-f16-4x.gguf | 901017536 |
| dspark-MiniCPM-OCR-1_0-Q8_0.gguf | 327293024 |
| Totale | **2039908992** |

Circa **2.04 GB decimali**, oltre allo spazio per l'import nello store Ollama;
lo script richiede almeno6GB liberi. I pesi e lo store sono sotto `models/`
nel repository, esclusi da Git. Viene riusato l'eseguibile Ollama già presente;
non vengono installati componenti di sistema né eseguiti script remoti.

**Eseguire i passaggi seguenti soltanto dopo autorizzazione al download.**

1. Scaricare i file e verificarli:

   ```bash
   .venv-verify/bin/python scripts/setup_minicpm.py --download-models
   ```

2. In un terminale separato avviare il server isolato e lasciarlo aperto:

   ```bash
   scripts/start-minicpm.command
   ```

3. Registrare i pesi verificati su quella istanza:

   ```bash
   .venv-verify/bin/python scripts/setup_minicpm.py --register
   .venv-verify/bin/pdf2docx-ai doctor --json
   ```

4. Verificare inferenza su fixture sintetica prima di dichiarare il backend
   collaudato o usarlo su documenti reali:

   ```bash
   .venv-verify/bin/pdf2docx-ai convert tests/fixtures/generated/scan_en.pdf \
     --engine minicpm --language en --output examples/output/minicpm-check.docx \
     --ground-truth tests/fixtures/generated/scan_en.txt --validate-visual
   ```

Lo script di avvio non modifica il server esistente su11434; rifiuta una
18499 già occupata, imposta modello/store e limiti di concorrenza solo
nell'ambiente del processo figlio. Ctrl-C nel suo terminale arresta il server.
Nessun servizio persistente o avvio automatico di sistema viene installato.
Il download supporta file `.part`, controlla dimensione/hash e non sostituisce
file esistenti non conformi. La registrazione richiede il PID del launcher
del repository per evitare lo store Ollama predefinito.

## Server già configurato su un'altra porta

La GUI può essere avviata con endpoint e alias espliciti, sempre loopback:

```bash
pdf2docx-ai serve --minicpm-url http://127.0.0.1:11434/v1 \
  --minicpm-model minicpm-ocr
```

Questo non installa il modello: `/api/tags` deve già contenerlo. Il setup
predisposto segue invece la18499 della guida ufficiale e lascia separata
l'istanza11434.

Fonti: [guida Ollama OpenBMB](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy.md),
[pesi e proiettore](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-gguf),
[draft DSpark](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-DSpark-gguf),
[porta predefinita Ollama](https://docs.ollama.com/api/introduction).

## Installazione e inferenza completate

Dopo autorizzazione esplicita sono stati scaricati tutti i file della tabella,
verificati i tre SHA-256 e registrato `minicpm-ocr:latest` nel solo store del
repository. Il server **Ollama0.40.16 è attivo su127.0.0.1:18499** e l'istanza
preesistente su11434 resta attiva. Non sono stati installati servizi di sistema.

Il server18499 è stato lasciato in background per consentire l'uso dalla GUI.
Per arrestarlo, da terminale nel repository:

```bash
scripts/stop-minicpm.command
```

Per riavviarlo successivamente usare `scripts/start-minicpm.command`, che resta
in primo piano e si arresta con Ctrl-C. I pesi restano salvati nel repository.

Prove reali: scansioni sintetiche inglese e italiana e pagina mista convertite
in DOCX con testo editabile e PDF ricercabile. CER/WER **0** sulle due scansioni
con ground truth (57/64 caratteri); nessuna generalizzazione a un corpus reale.
È riuscito anche un job MiniCPM attraverso la GUI utente sulla8765, con testo
italiano esatto e senza interrompere gli altri job. L'istanza web preesistente
non espone ancora `/api/engines` (404): ciò non impedisce la conversione;
riavviarla dopo aver scaricato i risultati per ottenere il nuovo indicatore.

I log confermano **Metal su Apple M5**,25/25 layer target e6/6 draft su GPU,
attivazione `draft-dspark` e statistiche di accettazione dei token draft.
La suite completa con i due OCR reali ha prodotto **77 passati in13.07s**.
Evidenza compatta in `minicpm-verification.json`, report completi in
`examples/output/minicpm-live/` e verifica web in
`examples/output/minicpm-web-check/` nella workspace.

Limite osservato: MiniCPM restituisce testo e coordinate della regione, senza
box per singola riga/parola. Nel default a pagina intera il DOCX mantiene testo
editabile ma usa un layout molto semplificato; la precisione testuale non
dimostra fedeltà geometrica. I report riportano queste capacità separatamente.

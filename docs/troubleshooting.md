# Risoluzione problemi

## Python non supportato

Controllare `python --version` dopo l'attivazione dell'ambiente. Il Python3.9 di sistema non è supportato. Il collaudo usa3.12.14 ARM64; `.venv-verify` è l'ambiente pulito già preparato nella workspace.

## Nessun OCR disponibile

Eseguire `pdf2docx-ai doctor --json`. Un PDF nativo non richiede OCR. Per scansioni scegliere un backend installato: Vision richiede macOS/strumenti Swift, Tesseract eseguibile/dati lingua, i VLM server/modelli locali. Il programma non scarica modelli. Un errore sul motore esplicito viene propagato; `auto` seleziona per health check in ordine documentato.

La GUI ora visualizza lo stato dei backend. Se MiniCPM restituisce
`Connection refused`, consultare [setup MiniCPM](setup-minicpm.md): la porta18499
non è quella predefinita di Ollama e occorrono anche i pesi registrati.

## Vision restituisce Foundation error 0

Il problema è stato riprodotto nel sandbox dell'agente e non nell'esecuzione locale autorizzata. Riprovare da un normale terminale macOS. Non viene disattivata la sicurezza di sistema. Se persiste, controllare la compatibilità Vision/macOS e usare un altro backend locale già disponibile.

## Report senza SSIM

Richiedere `--validate-visual` e controllare la voce `renderer` di doctor. Se LibreOffice manca, il report è `unavailable`; se restituisce errore, stderr/stdout rilevanti sono in `visual.reason`. Indicare `--renderer` per un eseguibile già installato. Il renderer usa un profilo temporaneo e timeout120s. SSIM non è disponibile senza rendering, e non misura comunque OCR.

## File già esistente o conversione interrotta

Il programma non sovrascrive senza `--overwrite`. La cache `.work` permette la ripresa delle pagine completate; `--no-resume` forza rielaborazione. Un lock contiene il PID; un lock di un processo terminato può essere recuperato automaticamente. Un lock malformato richiede ispezione/rimozione manuale. Non rimuovere lock di conversioni attive.

I file finali sono pubblicati con rename individuali: un arresto durante l'ultima pubblicazione può lasciare parte degli artefatti. Conservare gli output necessari e ripetere con `--overwrite --resume`. Non viene offerta una transazione atomica su tutto il gruppo di file.

## Word cambia pagina o font

Consultare sostituzioni, parti non editabili e confronto. Word usa un layout a flusso e metriche font del sistema destinatario. Tabelle, header/footer e colonne possono spostarsi; non esiste garanzia pixel-perfect. La modalità visual è esplicitamente raster e conserva un nome distinto.

## GUI chiusa e file non disponibili

I file web sono temporanei e cancellati allo shutdown; scaricarli durante la sessione. Per artefatti persistenti usare la CLI. Il limite della sessione è32 job; riavviare il server per una nuova sessione o attendere la scadenza24h dei job completati, applicata al nuovo upload.

## Limiti e grandi documenti

Usare `--max-pages`, `--max-file-mb`, `--dpi` e `--timeout`. Il raster è limitato anche da `Settings.max_pixels`. Il report HTML incorpora immagini di confronto solo per le prime50 pagine, mantenendo le metriche sulle altre. La cache può occupare molto disco. Usare `--workers 1` per evitare modelli concorrenti; parallelismo multiprocesso disponibile solo nel benchmark.

## Avvisi delle dipendenze

La suite verificata emette deprecation warning di PyMuPDF SWIG e del TestClient Starlette/httpx. Non sono fallimenti di conversione; le versioni sono bloccate nel lock. Nessun aggiornamento automatico viene eseguito. Gli aggiornamenti vanno verificati in un ambiente separato.

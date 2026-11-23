# Prestazioni misurate

Collaudo finale del 15 novembre 2026 su macOS26.7.1 ARM64, Python3.12.14,
ambiente pulito `.venv-verify`, lock incluso nel repository. Nel primo benchmark
il chip non era stato identificato. Il successivo collaudo MiniCPM ha confermato
Metal su Apple M5; la RAM totale e Neural Engine non sono stati misurati.

## Corpus e metodo

14 PDF sintetici originali,18 pagine complessive, generati da
`tests/fixtures/generate.py`. Coprono testo italiano/inglese, accenti, scan,
pagina mista, due colonne, immagini, tabelle/merge, elenchi, header/footer,
formule native, orientamento, formati diversi e rotazione/crop.
Nessun documento reale di terzi è stato utilizzato. Campioni molto piccoli e
puliti: non rappresentano documenti amministrativi densi o foto degradate.

```bash
pdf2docx-ai benchmark tests/fixtures/generated --engine vision --validate-visual \
  --output examples/output/benchmark-final --workers 1 --json
```

Un processo, una conversione alla volta; prime esecuzioni degli output, cache
pagine non riutilizzata, helper Swift già compilato. Rendering OCR180dpi,
confronto100dpi con LibreOffice locale. Risultato: **14 documenti riusciti,
0 errori**. I risultati compatti portabili sono in `benchmark-results.json`;
i report completi sono in `examples/output/benchmark-final` nella workspace.

| Fixture | Pagine | Tempo riportato s | OCR s | Picco RSS campionato MB | SSIM |
| --- | ---: | ---: | ---: | ---: | --- |
| columns | 1 | 1.005 | 0.000 | 291.2 | 0.96524 |
| formula | 1 | 0.655 | 0.000 | 388.6 | 0.99709 |
| headers | 3 | 0.834 | 0.000 | 300.7 | 0.99156–0.99157 |
| image | 1 | 0.851 | 0.139 | 405.4 | 0.97049 |
| landscape | 1 | 0.668 | 0.000 | 398.7 | 0.99438 |
| lists | 1 | 0.652 | 0.000 | 403.4 | 0.98240 |
| merged_table | 1 | 0.661 | 0.000 | 408.5 | 0.96177 |
| mixed | 1 | 0.872 | 0.190 | 418.0 | 0.98837 |
| native | 1 | 0.650 | 0.000 | 430.8 | 0.99187 |
| page_sizes | 3 | 0.777 | 0.000 | 430.8 | 0.99635–0.99824 |
| rotated_crop | 1 | 0.666 | 0.000 | 457.8 | 0.98928 |
| scan_en | 1 | 0.911 | 0.200 | 470.3 | 0.97970 |
| scan_it | 1 | 0.915 | 0.214 | 470.5 | 0.97849 |
| table | 1 | 0.668 | 0.000 | 355.5 | 0.95807 |

Il tempo interno include estrazione, OCR e validazione/rendering fino alla
preparazione del report; esclude avvio dell'interprete e l'ultima scrittura dei
report. La CLI espone anche secondi/pagina e tempo di ricostruzione. I valori
sono una singola esecuzione, non medie o percentile e non una promessa di
velocità su altri input. L'OCR dell'immagine decorativa non ha sostituito il
raster quando non ha prodotto testo.

La memoria è il massimo RSS campionato ogni50ms del processo e dei figli
accessibili, non memoria GPU/unificata totale né allocazioni dei server
esterni. Lo stesso processo attraversa il corpus: allocatori e cache mantengono
memoria fra i casi, quindi i valori in tabella non sono consumi isolati per
documento. Nel sandbox, l'accesso ai figli può essere negato: il report dichiara
allora esplicitamente il solo RSS del processo. Spike inferiori a50ms possono
non essere osservati.

## Accuratezza OCR separata

Una prova precedente realmente eseguita con Vision, senza mock e con PDF
ricercabile/validazione visiva, ha confrontato le due scansioni con ground
truth. Dati in `ocr-benchmark-results.json`.

| Campione | Caratteri / parole riferimento | CER | WER | OCR s | Tempo interno s |
| --- | --- | ---: | ---: | ---: | ---: |
| scan_it | 64 /10 | 0 | 0 | 0.233 | 0.995 |
| scan_en | 57 /9 | 0 | 0 | 0.216 | 0.909 |

Normalizzazione esclusivamente dello spazio bianco; accenti e maiuscole sono
confrontati. I tre test opt-in reali sono stati eseguiti anche nell'ambiente
pulito e sono passati, compreso il caso misto senza duplicazione. Questi
risultati non dimostrano accuratezza generale italiana/inglese. Per Xiaomi e
MiniCPM inizialmente non esistevano misure locali. Dopo l'autorizzazione ai
pesi, il collaudo descritto sotto ha eseguito inferenza reale; i benchmark
upstream non vengono trasferiti ai GGUF o al presente convertitore.

## Fedeltà e verifiche

Il numero di pagine è conservato nel corpus finale. Le14 conversioni sono
state riaperte come DOCX e renderizzate anche con `render_docx.py` per controllo
visivo. Il confronto misura separatamente tabelle Word native, immagini
presenti e variazioni del detector tabelle. Le tabelle ricevono font sorgente
e allineamento verticale stimato, con bordi semplificati.

**SSIM non misura OCR**. Il bianco dominante nelle fixture alza la somiglianza.
Lo scostamento geometrico dipende dal matching testuale: `columns` ha soltanto
un blocco abbinato e le scansioni nessuno, perché il sorgente non contiene
testo nativo. Non si interpreta un campione insufficiente come fedeltà
completa. Word non è stato avviato: renderer effettivamente collaudato è
LibreOffice locale.

La suite di base ha prodotto **66 passati, 3 saltati** con `python -m pytest -q`.
La suite completa `PDF2DOCX_REAL_OCR=1 python -m pytest -q` ha prodotto
**69 passati in 4.85s** nella prima verifica. Il report JUnit `test-results.xml`
ora fotografa il collaudo aggiornato77/77 descritto sotto. Sei warning di
deprecazione provengono da SWIG e TestClient delle dipendenze. Nessun errore.
Il benchmark multiprocesso è stato inoltre provato con due worker su due PDF
nativi:2/2 riusciti. Non è una misura di accelerazione.

Il controllo visivo ha individuato righe spezzate artificialmente quando il
paragrafo era ristretto al box esatto dei glifi. La versione0.1.1 mantiene le
interruzioni sorgente e lascia disponibile la larghezza di flusso: i casi
orizzontale, elenchi e dimensioni miste sono stati corretti e renderizzati di
nuovo. Il testo su pagina ruotata è ora leggibile orizzontalmente, con avviso
esplicito sul cambio di geometria rispetto all'originale.

## MiniCPM reale dopo installazione autorizzata

Ollama0.40.16, GGUF principale Q8_0, proiettore F16 e draft DSpark abbinato,
endpoint127.0.0.1:18499. SHA-256 dei tre file verificati. Cache pagine disattivata.
Rendering180dpi e validazione LibreOffice100dpi, con PDF ricercabile.

| Fixture | Tempo interno s | OCR s | CER | WER | SSIM |
| --- | ---: | ---: | ---: | ---: | ---: |
| scan_en | 6.768 | 5.749 | 0 | 0 | 0.97476 |
| scan_it | 4.580 | 3.835 | 0 | 0 | 0.97255 |
| mixed | 4.648 | 3.921 | non misurato | non misurato | 0.98590 |

Singole esecuzioni, la prima include il caricamento iniziale. Nessun modello
caricato dal secondo backend in parallelo. La memoria campionata del processo
Python **esclude il server Ollama esterno**, quindi non rappresenta la memoria
totale di inferenza. Log runtime: Metal Apple M5, target25/25 e draft6/6 layer
su GPU, DSpark attivo con statistiche di accettazione. I tempi non dimostrano
la qualità o la velocità su documenti più complessi.

Word contiene testo editabile, ma il risultato MiniCPM a pagina intera fornisce
solo box della regione: posizione, font e margini sono molto semplificati.
SSIM alto, dominato dal bianco, non dimostra fedeltà geometrica. Le due stringhe
ground truth contengono soltanto57 e64 caratteri: CER/WER0 non è una stima
generale italiana/inglese. Una conversione italiana è riuscita anche tramite
l'API della GUI utente8765, con testo esatto e nessuna immagine di pagina nel Word.

Suite completa con Vision e MiniCPM reali: **77 passati in13.07s**, senza test
saltati. Snapshot misurato: `minicpm-verification.json`.

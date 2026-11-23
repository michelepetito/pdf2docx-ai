# Validazione multidimensionale 0.3.0

Revisione del 22 novembre 2026. Il validatore misura quattro dimensioni separate,
senza punteggio composito. Le soglie sono target sperimentali, non garanzie o
percentuali certificate di fedeltà. Un target non misurabile è `unavailable`.

## Architettura e riuso

La pipeline esistente estrae il PDF, costruisce il modello, genera il DOCX,
ottimizza il layout e produce il rendering. Sono riusati `visual_diff`, SSIM,
matching uno-a-uno delle parole, renderer isolato, modello documentale e report.
L'ottimizzatore mantiene le misure leggere; l'assessment dettagliato viene eseguito
sul risultato finale. Non sono cambiati gli algoritmi di conversione.

`quality/assessment.py` coordina `textual.py`, `geometry_metrics.py`,
`structure.py` e `history.py`. `assessment_reporting.py` integra quattro sezioni
nel report HTML già esistente. Restano disponibili i campi storici del JSON;
il nuovo oggetto `assessment` dichiara `schema_version: "2.0"`.

## A. Aspetto

PDF sorgente e DOCX renderizzato sono rasterizzati con PyMuPDF a 100 DPI,
ridotti insieme se necessario per il limite di pixel. Stessa scala fisica,
canvas bianco comune, nessuna traslazione o deformazione per aumentare SSIM.
Le pagine in più o in meno restano nel confronto. SSIM è una media di pagine;
sono esposti anche ogni pagina, minimo, P10 e pagine sotto soglia.

La definizione SSIM preesistente resta invariata: luminanza, finestra uniforme
7×7, covarianza campionaria, C1=(0,01×255)² e C2=(0,03×255)². MAE, frazione
pixel cambiati, SSIM di primo piano e IoU/F1 dell'inchiostro accompagnano la
media. Originale, risultato, differenza, heatmap e overlay semitrasparente sono
incorporati nell'HTML. I dettagli sono in [metrics-design](metrics-design.md).

SSIM≥0,990 è controllato sia globalmente sia per la peggiore pagina. Anche un
risultato visivo alto può fallire testo, geometria o struttura.

## B. Testo

CER = distanza di Levenshtein dei caratteri / numero di caratteri del riferimento;
WER applica la stessa definizione alla sequenza di parole. Si usano costi unitari
per inserzioni, cancellazioni e sostituzioni, senza cutoff, confronto fuzzy o
riordinamento dei token. Il denominatore è il riferimento, non la lunghezza
massima delle due stringhe: il risultato può superare 1. A livello della funzione
di base il denominatore vuoto è limitato a 1; l'assenza di riferimento nativo
nell'assessment è invece indisponibilità, mai errore zero.

È usato **RapidFuzz 3.14.6, MIT**, con `Levenshtein.distance` ed `editops`.
La [documentazione ufficiale](https://rapidfuzz.github.io/RapidFuzz/Usage/distance/Levenshtein.html)
descrive costi, sequenze ed operazioni esatte; il
[pacchetto fissato](https://pypi.org/project/RapidFuzz/3.14.6/) dispone di wheel
macOS ARM64. Sostituisce il precedente DP Python che rinunciava oltre 25 milioni
di celle residue. PyMuPDF e python-docx già presenti restano gli estrattori.

I riferimenti restano distinti:

| Misura | Riferimento e interpretazione |
| --- | --- |
| `strict_stream` | Ordine interno dei due PDF, soli spazi normalizzati; confrontabile con il validatore 0.2.0 |
| `normalized_stream` | Stesso ordine, normalizzazione tipografica esplicita |
| `primary` | Flusso fisico inferito oppure ground truth esterno dichiarato; base del target CER |
| `docx_body_order` | Flusso del corpo OOXML, intestazioni e footer separati; diagnostico |
| Ground truth OCR | Testo indipendente esplicito, con SHA-256; una trascrizione estratta dal PDF non è ground truth indipendente |

Il profilo canonico applica NFC, spazi uniformi, legature tipografiche ff/fi/fl/
ffi/ffl/st e rimuove soft hyphen, BOM e zero-width space. Mantiene maiuscole,
accenti, punteggiatura, trattini effettivi, segni numerici e apici come ².
Il report distingue normalizzazione, tokenizzazione/ordine e contenuto.

Sono contati deficit/surplus di caratteri, token mancanti, aggiunti e possibili
duplicati, inversioni d'ordine e numeri/date alterati. I piccoli cambiamenti di
valore falliscono un controllo indipendente anche con CER inferiore a 0,1%.
Le operazioni di sequenza espongono offset e pagina/box della parola contenente
il carattere: non sono coordinate dei singoli glifi. Le liste hanno limiti
espliciti, mentre i conteggi complessivi non vengono troncati.

Un PDF misto senza riferimento OCR completo lascia indisponibili i target
testuali complessivi. I conteggi di caratteri sono multinsiemi, non una prova
di ordine corretto. Il flusso fisico e gli abbinamenti di parole ripetute sono
euristici: una variazione di CER logico non dimostra da sola perdita di testo.

## C. Geometria

Otto categorie: blocchi, paragrafi, righe, colonne, tabelle, immagini,
intestazioni e piè di pagina. Box e baseline sono nel sistema PDF visualizzato,
con crop/rotazione applicati. Si misurano IoU, distanza dell'origine,
errori assoluti X/Y, larghezza, altezza e baseline, con media, mediana, P90, P95
e massimo. **1 pt = 25,4/72 mm**; il JSON conserva entrambe le unità.

Le associazioni usano le parole esatte come ancore, con unioni uno-a-molti e
fusioni dichiarate. Percentili e IoU sono sui soli match nella stessa pagina:
copertura, mancanti e spostamenti fra pagine sono sempre esposti separatamente.
Un'assenza di match non riceve IoU=1 o errore=0.

| Categoria | Evidenza e limite |
| --- | --- |
| Blocchi/righe | Estrazione PDF nativa; i confini possono cambiare fra renderer |
| Paragrafi | Gruppi inferiti dal flusso e dai salti di baseline; non semantica certificata |
| Colonne | Corsie di testo visibili inferite; non larghezze originali delle sezioni |
| Tabelle | Griglie native rilevate; tabelle senza bordi o raster non hanno semantica verificata |
| Immagini | Identità dei pixel decodificati oppure abbinamento geometrico esplicitamente euristico |
| Header/footer | Testo ripetuto ai bordi su più pagine, normalizzando i numeri di pagina |

I margini confrontati sono i limiti dell'inchiostro del corpo visibile, distinti
dai margini OOXML auditati. Sono registrati pagine mancanti/aggiunte,
dimensioni pagina, corsie diverse, parole migrate e interruzioni esplicite Word.
Il PDF non contiene necessariamente la nozione originale di interruzione.
I target mediana≤1 mm e P95≤2 mm si riferiscono alle origini delle parole
associate nella stessa pagina; le otto categorie restano visibili nel dettaglio.

## D. Struttura e modifica reale

L'audit OOXML conta testo effettivamente visibile, stili nascosti ereditati,
caselle di testo, vere tabelle, bordi esplicitamente invisibili, immagini
indipendenti, media, sezioni, colonne, margini, stili, rientri e tabulazioni.
Protezione documento e controlli bloccati impediscono di dichiarare editabile
il documento. Le tabelle aggiuntive rispetto al modello o alle griglie native
richiedono revisione: l'assenza di bordi non prova una tabella di layout.

Le immagini a pagina intera sono confrontate con le immagini sorgenti e con
l'evidenza testuale. Una grande fotografia originale non equivale automaticamente
a sostituzione raster; una scansione mantenuta sotto testo OCR non riceve una
certificazione di ricostruzione editabile. Immagini native mancanti e sostituzioni
OCR ambigue sono distinte. Un test avversario mostra SSIM>0,99 con pagina-raster
e una minuscola etichetta editabile: il risultato fallisce gli altri controlli.

Il campo `missing_native_images` indica immagini sorgenti **non abbinate**,
non una perdita di byte provata. Sul rendering PLOS ci sono 11 immagini sia
prima sia dopo: 10 restano non abbinate perché cambiano pagina e il renderer
ridimensiona i pixel (ad esempio 2287×998 → 2249×981). Il digest non coincide
e l'euristica geometrica non attraversa le pagine; il controllo conservativo
non certifica la conservazione. Audit dei media DOCX, immagine renderizzata e
posizione sono evidenze diverse. La regressione di quel conteggio richiede
revisione e non va descritta come dieci immagini effettivamente scomparse.

La prova `--edit-probe` inserisce **«verifica di prova »** nel primo paragrafo
ordinario sufficientemente lungo, altrimenti in un paragrafo/cella disponibile,
su una copia. Salva, riapre e renderizza davvero con LibreOffice. Controlla
l'inserzione XML esatta, hash dell'originale, oggetti/media, testo renderizzato
atteso comprensivo dell'aggiunta, pagine, parole spostate e pagine interessate.
Il budget diagnostico esplicito è al massimo una pagina di differenza.

Un controllo ulteriore cerca nuove intersezioni fra righe vettoriali orizzontali
larghe almeno 40 pt e alte al massimo 2 pt e il 20–90% centrale dei box di testo.
È un'euristica da revisionare, non analisi dei glifi o di barrature intenzionali.
Serve a rilevare decorazioni ferme mentre il testo rifluisce. Sul CV la modifica
conserva tutti i contenuti e due pagine, ma introduce sovrapposizioni sui titoli:
`layout_disruption_suspected`, non esito di stabilità positivo. L'HTML mostra le
prime tre pagine prima/dopo/overlay; le misure coprono l'intero documento.

Una sola inserzione non certifica ogni modifica. LibreOffice è verificato;
Microsoft Word non è stato usato come renderer.

## Storia, confronti e riproducibilità

Ogni assessment registra SHA-256 di PDF, DOCX, PDF renderizzato, eventuale GT e
modello; versione/hash del renderer, librerie, codice delle metriche, profilo
testuale, soglie e modalità della prova. L'identità hash produce uno snapshot
immutabile. In sovrascrittura il precedente JSON e gli artefatti noti ancora
corrispondenti all'hash vengono archiviati; non si seguono percorsi arbitrari
letti dal precedente JSON.

Le regressioni sono indipendenti per SSIM, peggior pagina, CER/WER, geometria,
testo, pagine, raster, tabelle, caselle, immagini e vincoli di modifica. Un guadagno
SSIM con peggioramento altrove produce `tradeoff: true`. Le tolleranze sono nel
JSON. Riferimenti testuali/GT o normalizzazioni differenti rendono non comparabili
le metriche testuali; un cambio renderer viene segnalato. I report legacy restano
conservati e richiedono una rivalutazione esplicita.

```bash
pdf2docx-ai validate input.pdf output.docx --output verifica.html --edit-probe
pdf2docx-ai validate input.pdf output.docx --output nuova.html \
  --previous verifica.json --ground-truth riferimento.txt
pdf2docx-ai convert input.pdf --output output.docx --validate-editability
PDF2DOCX_COMPLEX=1 PDF2DOCX_REAL_OCR=1 PDF2DOCX_REAL_MINICPM=1 python -m pytest -q
python scripts/evaluate_validation.py
```

Il corpus riusa 26 conversioni congelate, 61 pagine sorgenti: 14 casi semplici,
10 complessi originali inclusi il CV obbligatorio e un rapporto con planimetria,
2 pubblicazioni reali CC BY 4.0. Provenienza in [complex-corpus](complex-corpus.md)
e nei manifest. Il validatore 0.2.0 preservato viene eseguito in subprocess sullo
stesso identico PDF renderizzato del nuovo: SSIM e CER stream devono coincidere
dove prima disponibili. Il CER dei documenti lunghi ora viene calcolato esattamente.
Le conversioni 0.1.1 e 0.2.0 sono confrontate anche con il medesimo nuovo validatore.
Questo è una rivalidazione del corpus già usato, non un nuovo holdout cieco.

Report: [HTML comparativo](validation-final-report.html),
[JSON completo](../examples/output/validation-review/evaluation.json),
[JUnit](validation-test-results.xml). Per aggiungere casi si estendono manifest,
ground truth indipendenti e record congelati con hash. La pipeline verifica anche
conversione e assessment end-to-end; la rivalutazione dei DOCX congelati isola
l'effetto del solo validatore senza attribuirgli miglioramenti del convertitore.

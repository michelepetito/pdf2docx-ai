# Ricerca per la ricostruzione geometrica modificabile

Ricerca del 16 novembre 2026 per la revisione del progetto esistente. Le fonti
sono specifiche, documentazione dei manutentori, codice upstream e pubblicazioni
degli autori. Una funzione descritta nella documentazione non è una prova di
correttezza sul corpus locale. Questo documento motiva algoritmi e vincoli;
i risultati prima/dopo sono materia del collaudo, non vengono anticipati qui.

## Decisione architetturale

Il motore deve inferire una struttura a flusso Word da misure PDF, conservando
le osservazioni originali. La priorità è paragrafi con rientri/tabulazioni,
interlinea, spaziatura, sezioni e colonne; celle Word solo per autentiche tabelle.
Immagini indipendenti possono essere ancorate quando il PDF mostra sovrapposizione
verticale con il testo. Nessun contenitore generico e nessuna pagina raster
possono essere introdotti dall'ottimizzatore per rendere migliore una metrica.

Le otto decisioni operative sono:

1. Conservare baseline, direzione, metriche font e righe, oltre ai box.
2. Derivare l'avanzamento verticale dalle baseline e dal flusso renderizzato,
   anziché dall'altezza complessiva di un blocco divisa per il numero di righe.
3. Distinguere righe con tabulazioni dalle vere colonne mediante persistenza
   dei separatori e relazione fra etichetta breve e contenuto affiancato.
4. Inferire margini senza il tetto fisso di 72 pt e colonne di larghezza non
   necessariamente uguale; conservare le bande che attraversano più colonne.
5. Selezionare font anche per compatibilità metrica, limitando esplicitamente
   gli aggiustamenti di tracking e preservando dimensioni native affidabili.
6. Estrarre immagini native senza ricompressione quando trasformazioni,
   maschere e clipping lo consentono; ricostruire il rapporto col flusso.
7. Ottimizzare parametri Word con ricerca locale limitata e renderer reale,
   conservando sempre il miglior candidato ammissibile.
8. Valutare testo, geometria, immagini e modificabilità come vincoli separati;
   SSIM su pagina intera non può certificare da solo il successo.

## Cause rintracciabili nel codice iniziale

Queste sono osservazioni sulla versione iniziale del repository, non errori
dedotti da un benchmark di altri prodotti:

| Punto | Informazione persa o ipotesi fragile | Conseguenza attesa da misurare |
| --- | --- | --- |
| `document/models.py`, `pdf/extractor.py` | Lo span conserva box, testo e size, ma non `origin`, ascender, descender o righe geometriche tipizzate. | Impossibile ricostruire un avanzamento baseline affidabile dopo l'estrazione. |
| `reconstruction/paragraphs.py` | L'interlinea è ricavata da box/numero righe e limitata fra multipli della dimensione massima. | Perdita di interlinee reali, deriva cumulativa e paragrafi di altezza errata. |
| `reconstruction/sections.py` | Margini dedotti dalle estremità e limitati a 72 pt; distanze header/footer fisse. | Documenti con ampio margine laterale, CV e intestazioni vengono spostati. |
| `reconstruction/engine.py` | Due colonne uguali con interspazio 18 pt, reset semplificati del cursore verticale. | Gutter, colonne asimmetriche e bande sovrapposte non riproducibili correttamente. |
| `reconstruction/engine.py`, `images.py` | Immagini trattate normalmente come oggetti inline che consumano altezza. | Foto e testo affiancato spostano il contenuto successivo. |
| `pdf/extractor.py` | Le immagini sono crop del rendering della pagina. | Ricampionamento e possibile contaminazione da altri oggetti sovrapposti. |
| Pipeline OCR | MiniCPM può restituire testo della regione senza box di parola/riga. | Un box di pagina non equivale a geometria tipografica osservata. |
| Validazione | Confronto successivo a una sola esportazione, matching di blocchi dipendente dalla segmentazione. | Mancano correzione parametrica e copertura sufficiente nei layout complessi. |

La diagnosi va completata con la baseline riproducibile e il corpus complesso.
Non si devono scartare righe sovrapposte o riscrivere testo solo perché una
euristica le considera improbabili.

## PDF e misure tipografiche

PyMuPDF documenta `span.origin` come origine del primo carattere; il suo valore
y è la baseline del testo orizzontale. `ascender` e `descender` sono relativi
alla size; il box standard descrive l'altezza di linea e non coincide sempre
con l'inchiostro dei glifi. `line.dir` descrive la direzione. `rawdict` offre
anche origini e box dei caratteri. Il flag bold/italic può essere errato nel
font sorgente: va trattato come evidenza e non come verità semantica.
[Fonte: TextPage](https://pymupdf.readthedocs.io/en/latest/textpage.html).

La trasformazione canonica deve essere unica: punti PDF non ruotati relativi
alla CropBox -> punti visualizzati mediante matrice di rotazione; la stessa
trasformazione va applicata a origini e direzioni, non soltanto ai rettangoli.
Le API di inserimento PDF usano il riferimento non ruotato. Conservare MediaBox,
CropBox, rotazione e matrice rende ispezionabili gli offset.
[Fonte: Page, matrici e coordinate](https://pymupdf.readthedocs.io/en/latest/page.html#Page.rotation_matrix).

`get_image_rects(..., transform=True)` consente di associare un'immagine alle
sue occorrenze; `extract_image(xref)` restituisce dati e formato originali.
Le maschere alpha, il clipping e trasformazioni non rappresentabili direttamente
richiedono una conversione esplicita, segnalata nel report. Non è corretto
considerare un crop della pagina equivalente ai byte dell'immagine sorgente.
[Fonte: estrazione immagini](https://pymupdf.readthedocs.io/en/latest/document.html#Document.extract_image).

Per i nativi è utile conservare `TextLine` con baseline, direzione, box e lista
di span; il testo del paragrafo è una vista di queste osservazioni. Il modello
deve distinguere misure native, stime geometriche del raster e output del VLM.
Attribuire a MiniCPM un box di riga non restituito dal modello produrrebbe
una falsa precisione: gli eventuali box da segmentazione devono avere quella
provenienza, con una verifica dell'associazione testo/regione.

## Semantica Word effettivamente disponibile

ECMA-376 descrive il vocabolario e il pacchetto OOXML; la parte 1 è il riferimento
per WordprocessingML e DrawingML. La pagina di pubblicazione distingue edizioni
e date delle quattro parti: non chiamare genericamente ogni documento della
suite “spec 2021”. [Fonte: ECMA-376](https://ecma-international.org/publications-and-standards/standards/ecma-376/).

`w:spacing` supporta interlinea esatta e spaziatura tra paragrafi. `lineRule=auto`
interpreta il valore in 240esimi di linea, non in twip; con regole diverse il
valore è una lunghezza in twip. Le spaziature di due paragrafi adiacenti non si
sommano semplicemente. È preferibile iniziare con after=0, before dedotto dalla
geometria e stili espliciti, per evitare effetti ereditati. La prima baseline
va calibrata sul renderer, poiché il line box Word non è il box PDF.
[Microsoft w:spacing](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.spacingbetweenlines),
[analisi python-docx](https://python-docx.readthedocs.io/en/latest/dev/analysis/features/text/paragraph-format.html).

Tabulazioni, rientri prima riga/sporgenti e allineamento sono rappresentazioni
native di date a sinistra e contenuto allineato a destra nello stesso paragrafo.
I tabstop sono relativi al riferimento del paragrafo, da verificare con rientri
e sezioni. Una sequenza di spazi non sostituisce un tabstop.
[Microsoft Tabs](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.tabs).

`w:cols` ammette singole colonne configurate; non è obbligatorio usarle tutte
uguali. Servono una sezione/banda e un'origine di flusso per ogni colonna.
Le interruzioni continue possono influenzare bilanciamento e paginazione:
vanno renderizzate, non considerate posizionamento assoluto.
[Microsoft Columns](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.columns),
[Column](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.column).

La griglia documento può aggiungere pitch se `snapToGrid` è ereditato. Per una
ricostruzione geometrica indipendente si deve controllare tale proprietà nel
paragrafo e nei run, senza cambiare arbitrariamente i glifi.
[Microsoft SnapToGrid](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.snaptogrid).

`keepNext` può trattenere un titolo con il paragrafo successivo; usarlo su
sequenze lunghe può spostare un'intera pagina. Il vincolo va inferito da
titolo/sezione e spazio disponibile, non applicato a ogni blocco.
[Microsoft KeepNext](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.keepnext).

Le immagini flottanti hanno `wp:anchor`, posizioni orizzontale/verticale,
dimensioni e wrapping. L'ancora resta collegata a un paragrafo; il suo carrier
non deve consumare accidentalmente l'intera altezza dell'immagine. La scelta
fra wrapSquare, wrapNone e altri modi dipende dalle relazioni spaziali osservate.
[Microsoft Anchor](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.wordprocessing.anchor).

## Font e sostituzioni

La famiglia PDF può includere prefissi di subset e suffissi di stile: occorre
separare famiglia e proprietà bold/italic. Il matching deve confrontare più
stringhe rappresentative, privilegiando la famiglia installata e poi candidate
metricamente vicine. La larghezza dell'inchiostro del box non è sempre l'advance
della stringa: le origini dei caratteri aiutano a distinguere le due grandezze.

Liberation dichiara compatibilità metrica con Arial, Times New Roman e Courier
New; Carlito con Calibri. Sono candidate motivate, non sostituzioni universali
né una ragione per installare font senza necessità. La presenza locale e il
render effettivo vanno controllati.
[Liberation](https://github.com/liberationfonts/liberation-fonts),
[Carlito](https://raw.githubusercontent.com/googlefonts/carlito/main/README.md).

La tabella OpenType OS/2 contiene `fsType`: il permesso Preview & Print non è
un permesso generale di produrre un documento modificabile incorporando quel
font. Il flag di embedding non sostituisce la licenza. La strategia prudente
consiste nel non ridistribuire font PDF senza verifica; usare il nome di un
font già installato o un sostituto motivato, registrando disponibilità e misura.
[Microsoft OS/2 fsType](https://learn.microsoft.com/en-us/typography/opentype/spec/os2#fstype).

`w:spacing` a livello run rappresenta spaziatura dei caratteri, distinta da
quella dei paragrafi. Un eventuale tracking deve essere piccolo, esplicito e
confrontato col render. Non è giustificato deformare orizzontalmente i glifi,
ridurre font nativi o cambiare contenuto per guadagnare SSIM.
[Microsoft Run Spacing](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.spacing).

## Progetti esistenti e riferimenti commerciali

| Sistema | Funzione verificata nella fonte | Uso nella revisione e limite |
| --- | --- | --- |
| ABBYY FineReader | Distingue Exact copy, Editable copy, Formatted text e Plain text; distingue anche mantenimento line/page break. | Riferimento funzionale del compromesso fedeltà/editing, nessuna deduzione di algoritmo interno e nessun codice proprietario. |
| Aspose.Words | PDF loader, inclusione immagini, font settings e warning di perdita di fedeltà; renderer separato. | Riferimento per separare struttura, font e rendering; nessuna dipendenza commerciale introdotta e nessun benchmark locale del prodotto. |
| pdf2docx | Codice geometrico per righe, paragrafi, tabs, spaziatura esatta/relativa e immagini flottanti. | Studiare le euristiche senza sostituire l'applicazione; evitare le sue scelte incompatibili col vincolo sui contenitori. |
| LibreOffice | Apre DOCX; il manutentore avverte che layout complessi e alcune proprietà possono essere trattati diversamente. | Renderer locale misurabile. Le sue differenze da Word vanno riportate separatamente e non ottimizzate via deformazione del testo. |
| PP-StructureV3 | Pipeline con layout/OCR e moduli opzionali tabelle/formule; la documentazione corrente espone `save_to_word()`. | Non è corretto affermare che esporti solo Markdown, ma il metodo non dimostra layout fedele/modificabilità conforme ai nostri vincoli. Nessuna sostituzione automatica. |
| PP-DocLayoutV3 | Segmentazione e ramo per ordine di lettura, box/classi e altre informazioni di layout. | Può contribuire a regioni e ordine, non restituisce le baseline e le metriche font native perse dal convertitore. |
| MiniCPM-OCR | SDK gestisce layout/crop/assembly; riconoscimento restituisce testo, HTML per tabelle e LaTeX per formule. | Riutilizzare adapter locale; non duplicare l'intera pipeline SDK. Non inventare box di parola a partire da semplice Markdown. |
| Xiaomi-OCR-0 | Parsing a pagina/regione con pipeline e postprocessing; Ollama è descritto come sperimentale. | Preservare raw/provenienza; non trasferire automaticamente benchmark HF al GGUF locale. |

Fonti funzionali:
[ABBYY DOCX settings](https://help.abbyy.com/en-us/finereader/14/user_guide/docx_settings/),
[Aspose PdfLoadOptions](https://reference.aspose.com/words/python-net/aspose.words.loading/pdfloadoptions/),
[LibreOffice compatibilità](https://help.libreoffice.org/latest/en-US/text/shared/guide/ms_import_export_limitations.html),
[PP-StructureV3](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PP-StructureV3.html),
[PP-DocLayoutV3](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html),
[MiniCPM SDK](https://raw.githubusercontent.com/OpenBMB/MiniCPM-OCR/main/docs/minicpm_ocr_tutorial_en.md),
[Xiaomi](https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-OCR-0/main/README.md).

Nel sorgente pdf2docx, `TextBlock` conserva spaziature e tabstop; l'interlinea
esatta distingue la prima linea da quelle successive. `Blocks` separa immagini
flottanti da elementi inline tramite sovrapposizioni. Sono esempi concreti,
ma la rimozione euristica di righe sovrapposte o la divisione dei paragrafi in
base alla punteggiatura non vanno importate senza protezioni del testo.
[TextBlock](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/master/pdf2docx/text/TextBlock.py),
[Blocks](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/master/pdf2docx/layout/Blocks.py).

Il README corrente di pdf2docx dichiara fine della manutenzione attiva Artifex
e rilicenza MIT; il file LICENSE riporta Artifex2026. Le sue dipendenze hanno
licenze separate, e PyMuPDF resta AGPL nella distribuzione open source. Questa
ricerca non richiede di copiare il codice. Qualunque port sostanziale richiede
le attribuzioni previste.
[Stato upstream](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/master/README.md),
[LICENSE](https://raw.githubusercontent.com/ArtifexSoftware/pdf2docx/master/LICENSE).

## Algoritmi scientifici applicabili

**XY-cut su bounding box.** Ha, Haralick e Phillips (ICDAR1995) descrivono una
segmentazione ricorsiva mediante proiezioni dei box dei componenti connessi,
anziché tutti i pixel. È adatta come base economica per trovare gutter e bande
su pagine rettangolari. Nella revisione le proiezioni possono partire dalle
righe native, mantenendo i casi ambigui come tali. Non garantisce semantica,
ordine di lettura di layout intrecciati o distinzione fra tabulazioni e colonne.
[Paper originale ospitato dall'autore](https://haralick.org/conferences/71280952.pdf).

**Geometria e struttura logica.** La panoramica di Haralick distingue segmentazione
geometrica da interpretazione logica; questa distinzione motiva un modello che
non chiami “tabella” qualsiasi gruppo di box allineati. Docstrum/O'Gorman è
stato esaminato come famiglia di raggruppamento dal basso; il documento IEEE
originale è dietro verifica JavaScript nella consultazione disponibile, quindi
non vengono attribuiti dettagli implementativi o risultati sperimentali non
letti. Non si dichiara implementazione completa di Docstrum.
[Haralick, geometric/logical layout](https://www.haralick.org/DV/conferences/geometric_logical.pdf),
[riferimento editore Docstrum](https://ieeexplore.ieee.org/document/244677).

**LayoutReader e ground truth.** Wang et al. (EMNLP2021) usano testo e layout per
predire ordine di lettura e costruiscono ReadingBank da XML Word e documenti
renderizzati. Per questo progetto è utile il metodo di costruzione delle
fixture: conservare un DOCX sorgente distinto dall'output del convertitore e
derivare PDF/ground truth, con split indipendente. Il modello neurale non viene
aggiunto né vengono assunti i suoi punteggi su documenti locali.
[Pubblicazione ACL](https://aclanthology.org/2021.emnlp-main.389/).

**Coordinate descent.** Wright (2015) descrive aggiornamenti successivi lungo
coordinate e varianti. La motivazione pratica è un numero piccolo di parametri
Word, renderer non differenziabile e valutazione costosa. Le garanzie per
problemi convessi del paper non si applicano automaticamente al layout Word,
che presenta discontinuità di wrapping e paginazione. Il metodo locale deve
avere limiti di iterazione e arresto per mancato miglioramento.
[Paper dell'autore](https://arxiv.org/abs/1502.04759).

**Rendering differenziabile.** DiffVG ottimizza grafica vettoriale rispetto
all'immagine tramite rasterizzazione differenziabile. È un riferimento per
separare parametri geometrici e loss d'immagine, ma non fornisce un renderer
Word differenziabile. Trattare LibreOffice come DiffVG sarebbe un'API inventata;
la revisione usa una ricerca con render discreti e non introduce quel runtime.
[Progetto e paper degli autori](https://people.csail.mit.edu/tzumao/diffvg/).

**SSIM.** Wang et al. (TIP2004) valutano struttura visiva e distorsioni d'immagine;
il metodo non verifica il testo riconosciuto. Nel documento tipografico la
grande area bianca può dominare il valore. Si devono riportare SSIM globale,
confronto dell'area di inchiostro e geometria testuale, dichiarando esplicitamente
che un SSIM mascherato o una distanza fra maschere è una metrica aggiuntiva,
non il SSIM standard né accuratezza OCR.
[Paper originale](https://ece.uwaterloo.ca/~z70wang/publications/ssim.html).

## Procedura di ottimizzazione proposta

Il vettore di parametri deve contenere correzioni con significato Word:
offset dei margini, before dei paragrafi, rientri/tabstop, pitch delle linee,
geometria di colonne e ancoraggi delle immagini. Le coordinate PDF e il testo
sorgente rimangono immutabili. Le dimensioni native dei caratteri sono protette
di default; OCR senza font osservabile può usare una stima distinta e marcata.

La prima passata stima da dati, non cerca valori casuali. Il render successivo
misura residui: traslazione comune -> margine/origine; deriva con l'indice di
linea -> pitch; salti fra paragrafi -> spacing; larghezza errata -> font/tracking
o tabstop. Una correzione del testo, un salto di pagina aggiunto per nascondere
overflow o una sostituzione con immagini non sono candidati ammissibili.

La ricerca locale valuta passi positivi e negativi, limita gli intervalli,
riduce il passo se non c'è miglioramento e conserva il miglior pacchetto. Deve
registrare baseline, tentativi, candidati rifiutati e best-so-far. Il numero di
iterazioni e la soglia minima di miglioramento devono essere configurabili;
il renderer assente produce stato non disponibile, non un'ottimizzazione finta.

Ordine di valutazione consigliato:

1. Rifiuto dei candidati con testo perso, duplicato, numeri alterati, nuove
   pagine o perdita di modificabilità rispetto alla migliore soluzione.
2. Penalità per blocchi o immagini non associati e per cambi di pagina.
3. Errori geometrici in punti: posizione, baseline, dimensioni, IoU, p50/p90/p95
   e massimo, insieme al numero e alla percentuale di corrispondenze.
4. Similarità visiva globale e di primo piano, senza usare l'allineamento
   d'immagine per nascondere una traslazione globale nella metrica geometrica.
5. Regolarizzazione dei parametri: a parità di qualità preferire il modello
   Word meno complesso e più vicino alle misure iniziali.

Un candidato non può essere definito migliore soltanto perché SSIM cresce
mentre spariscono testo o immagini. Un matching ottenuto su un solo blocco
non può descrivere l'intera pagina. Parole e righe associate rendono il confronto
meno dipendente dal raggruppamento in blocchi del motore PDF.

## Verifica e generalizzazione

Conservare corpus di sviluppo e documenti indipendenti, con tipi dichiarati;
includere un CV europeo fittizio di almeno due pagine con foto sintetica,
date/tabulazioni, sezioni e una vera tabella. Il DOCX di riferimento non va
confuso col risultato della conversione. Il generatore del corpus deve seguire
regole editoriali proprie, non leggere i parametri del motore da collaudare.

Usare lo stesso renderer per misurare prima/dopo isola il miglioramento del
convertitore. Un secondo render Word, se disponibile e realmente eseguito,
misura invece la variabilità fra applicazioni. Non si dichiara equivalenza
Word/LibreOffice quando è stato provato soltanto uno. LibreOffice avverte
esplicitamente delle differenze per proprietà complesse.

Le soglie SSIM0.98 ed errore mediano2pt sono obiettivi del corpus, non criteri
da soddisfare cancellando esempi sfavorevoli. Reportare tutti gli esempi,
le categorie che non migliorano, la copertura del matching e le parti raster
non modificabili. Non c'è una percentuale universale di fedeltà ricavabile da
una singola metrica, e non si promette ricostruzione100%.

## Stato di verifica e dipendenze

La ricerca non installa librerie, font, software commerciale o pesi. Le API
OOXML/PyMuPDF sono documentate e vanno ricontrollate con le versioni bloccate
nel progetto. ABBYY/Aspose sono riferimenti funzionali, non componenti eseguiti.
Le tecniche geometriche sono realizzabili con Python, NumPy, PyMuPDF,
python-docx e lxml già presenti; i modelli AI non sono prerequisiti per
correggere il percorso nativo. Le nuove garanzie dipenderanno dai test locali
e dai report, non dal fatto che un progetto upstream descriva una funzione.

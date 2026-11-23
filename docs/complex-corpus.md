# Corpus complesso per la ricostruzione geometrica

Il corpus comprende **10 documenti originali, 21 pagine**, con contenuti realistici
ma dati interamente fittizi. È distinto dalle piccole fixture storiche da una
pagina. Ogni documento ha un **DOCX sorgente di riferimento indipendente** dal
convertitore e un PDF ottenuto renderizzando quel sorgente. Il DOCX di riferimento
non deve essere usato come input del motore o come scorciatoia per ricostruire il
risultato: serve a controllare che le regole di layout siano esprimibili in Word.

La generazione usa paragrafi, stili, sezioni, tabulazioni, colonne native,
interruzioni controllate, header/footer e vere tabelle di dati. Non usa tabelle
invisibili, caselle di testo o immagini di intere pagine per posizionare il testo.
Le immagini flottanti sono indipendenti e hanno ancoraggi DrawingML; i bordi di
paragrafo producono anche primitive grafiche nel PDF.

## Composizione e divisione fissa

| ID | Gruppo | Pagine | Tabelle Word sorgente | Immagini | Caratteristiche |
| --- | --- | ---: | ---: | ---: | --- |
| europass_fictitious | sviluppo | 2 | 1 | 1 | CV europeo, foto sintetica, date con tabulazioni, rientri sporgenti, sezioni, elenchi, tabella lingue, header/footer |
| research_bulletin | sviluppo | 2 | 0 | 0 | Articolo, font serif, titolo a tutta larghezza, sezioni continue e due colonne native |
| administrative_report | sviluppo | 2 | 1 | 1 | Logo, data allineata a destra, destinatario rientrato, istruttoria, vera tabella di evidenze |
| invoice_complex | sviluppo | 2 | 2 | 0 | Tabella lunga su più pagine, intestazione ripetuta, categorie con celle unite, valuta e riepilogo |
| field_inspection | sviluppo | 2 | 1 | 1 | Pianta flottante con testo affiancato, didascalia, elenco e tabella di azioni |
| mixed_orientation | sviluppo | 3 | 1 | 0 | Sezioni verticale/orizzontale/verticale, matrice larga con nove colonne |
| typography_catalog | sviluppo | 2 | 0 | 0 | Arial, Times New Roman, Courier New, dimensioni, peso, corsivo, colori, rientri e interlinea variabili |
| financial_statement | validazione indipendente | 2 | 1 | 0 | Impaginazione finanziaria differente, date/importi allineati con tabulazioni, font serif |
| project_newsletter | validazione indipendente | 2 | 0 | 1 | Colonne native di larghezza diversa, grafico inline, didascalia e variazione delle larghezze tra sezioni |
| procurement_form | validazione indipendente | 2 | 1 | 0 | Scheda amministrativa, campi e firme allineati con tabulazioni, punteggi con header unito e bordi grafici |

Il gruppo indipendente è fissato negli ID e nel manifest. Non va utilizzato per
scegliere coefficienti o soglie ad hoc. La valutazione finale deve riportarlo
separatamente. Anche il miglioramento sui sette casi di sviluppo deve essere
misurato contro la stessa versione congelata dei PDF, non contro documenti
rigenerati dopo le modifiche al convertitore.

Il corpus è sintetico e originale: non contiene PDF di terzi né dati personali
reali. Copre impaginazioni realistiche, ma non sostituisce una valutazione su
un campione pubblico/autorizzato di documenti di produzione. La scelta di non
usare CV reali evita di trattare dati personali senza autorizzazione.

## Curriculum europeo obbligatorio

Il CV di **Elena Esempio** usa un nome dichiaratamente fittizio, dominio
`example.invalid`, recapiti impossibili e incarichi inventati. È ispirato alla
distribuzione tipica dei curriculum europei, senza usare loghi o rivendicare un
template Europass ufficiale. La prima pagina contiene fotografia, profilo,
esperienze e formazione; la seconda lingue, competenze, progetti e attività.

Le date costituiscono una colonna logica mediante tabulazioni e rientri
sporgenti, non una griglia artificiale. La tabella delle lingue è una vera
tabella di dati. Questo caso permette di verificare se il motore distingue una
relazione tabulata da un layout multicolonna e se conserva la foto come oggetto
indipendente, senza spostare tutto il testo nel flusso successivo all'immagine.

La fotografia è stata creata con il tool **ImageGen integrato** per questa
fixture, senza una persona di riferimento e senza riutilizzare fotografie di
terzi. Il file locale è `tests/fixtures/complex/assets/fictional-cv-portrait.png`.
Il prompt e la provenienza sono registrati in `assets/provenance.json`; esiste
anche un avatar illustrato deterministico come fallback per rigenerazioni senza
l'asset fotografico. Il generatore non richiede cloud né genera immagini nuove.

## Riproduzione

```bash
python scripts/generate_complex_corpus.py
PDF2DOCX_COMPLEX=1 python -m pytest tests/integration/test_complex_contract.py -q
```

Il generatore usa il renderer LibreOffice **del bundle** della workspace:
`/Users/jacklondon/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice`.
Su un altro sistema indicare esplicitamente `--renderer /percorso/soffice` dopo
averne verificato la versione. Non installa componenti né scarica pesi. Per
generare soltanto DOCX/manifest senza PDF esiste `--no-render`. `--only ID...`
rigenera gli ID selezionati preservando le altre voci del manifest.

Output sotto `tests/fixtures/complex/generated/`:

- `ID.reference.docx`: sorgente Word originale, distinto dall'output convertito.
- `ID.reference.pdf`: PDF di input ottenuto dal sorgente.
- `ID.pdf.txt`: testo estratto dal PDF, con header/footer inclusi.
- `ID.reference.txt`: testo logico del corpo Word e celle, deduplicando i merge.
- `manifest.json`: ID/split, percorsi, SHA-256 DOCX, pagine, formato e conteggi.
- `qa/ID/page-N.png`: rendering di controllo con `render_docx.py`.
- `contact-sheet-N.jpg`: tavole di controllo per ispezionare tutte le pagine.

Le tabelle multipagina possono comparire nel PDF come più frammenti geometrici;
il numero di tabelle nel sorgente Word non coincide necessariamente con quello
dei frammenti riconosciuti dal detector sulle singole pagine. Il manifest
registra il primo valore senza presentarlo come ground truth del detector PDF.
I file testuali estratti non sono ground truth di ordine di lettura universale:
colonne, tabulazioni e celle possono essere serializzati diversamente.

## Verifiche effettivamente eseguite

Tutti i dieci sorgenti sono stati salvati, riaperti e renderizzati con il
LibreOffice del bundle; le21 pagine sono state generate anche con
`render_docx.py` e controllate mediante PNG e tavole di confronto. Il CV e le
immagini/tabelle critiche sono stati aperti separatamente a piena risoluzione.
I test di contratto hanno prodotto **13 passati**; coprono SHA dei sorgenti,
split7/3, contenuto non banale (>2000 caratteri PDF ciascuno), pagine, header/footer,
assenza di macro/textbox, conteggi delle vere tabelle e delle immagini, tabs del
CV, celle unite e orientamenti misti.

Il controllo ha individuato un errore nei sorgenti di prova: l'interlinea
esatta del normale paragrafo tagliava logo e grafico inline. È stato corretto
impostando interlinea automatica nei soli paragrafi immagine. Un test protegge
questa condizione, per evitare che un'immagine già tagliata nel riferimento
falsi la misurazione del convertitore.

Ultime rigenerazioni prima del congelamento: `invoice_complex` e
`procurement_form` per le celle unite; `administrative_report` e
`project_newsletter` per il clipping delle immagini. I relativi benchmark
precedenti devono essere rigenerati. Gli altri sei PDF, compreso il CV, non
sono cambiati. Nessuna misura di qualità del convertitore viene dedotta dal
semplice superamento dei controlli sul corpus.

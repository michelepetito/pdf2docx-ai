# Revisione del motore di ricostruzione PDF2DOCX

Documenti misurati: 26. Errori: 0. Non eseguiti: 0.

La versione HTML autonoma contiene le immagini comparative del curriculum europeo e i collegamenti ai report completi. Nessuna fedeltà del100% viene dichiarata.

## A Problemi individuati

Perdita di baseline e metriche; spaziature ricavate da box tipografici; gap/margini semplificati; immagini inline; metriche dominate dal bianco e pochi blocchi associati.

## B Soluzioni implementate

Geometria di righe e baseline, struttura Word nativa, tabulazioni/rientri/colonne, immagini ancorate, tabelle autentiche, ottimizzazione vincolata con renderer e invarianti. Le storie registrate documentano i parametri realmente corretti.

## C Risultati comparativi

| Documento | Gruppo | Pagine sorgente/risultato | SSIM prima → dopo | SSIM primo piano | Mediana box pt | P95 box pt | Mediana baseline pt | CER | WER | Caratteri mancanti/eccesso dopo | Parole associate | Tabelle Word | Immagini Word | Textbox/tabelle aggiuntive dopo | Secondi prima → dopo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| administrative_report | development | 2/2 → 2/2 | 0.67537 → 0.98803 | 0.01869 → 0.93827 | 36.550 → 0.000 | 150.300 → 0.000 | 30.650 → 0.000 | 0.00777 → 0.00000 | 0.00592 → 0.00000 | 0/0 | 507/507 | 1 → 1 | 0 → 1 | 0/0 | 2.661 → 4.883 |
| europass_fictitious | development | 2/2 → 2/2 | 0.70349 → 0.98949 | 0.05644 → 0.94616 | 46.750 → 0.000 | 187.751 → 0.000 | 46.700 → 0.000 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 416/416 | 1 → 1 | 1 → 1 | 0/0 | 2.044 → 5.179 |
| field_inspection | development | 2/2 → 2/2 | 0.73744 → 0.99035 | 0.03293 → 0.94500 | 27.100 → 0.000 | 56.054 → 0.050 | 27.100 → 0.000 | 0.00293 → 0.00000 | 0.00698 → 0.00000 | 0/0 | 430/430 | 1 → 1 | 0 → 1 | 0/0 | 1.307 → 4.667 |
| financial_statement | holdout | 2/2 → 2/2 | 0.79078 → 0.99004 | 0.04735 → 0.94601 | 68.350 → 0.000 | 155.552 → 0.050 | 67.900 → 0.000 | 0.08211 → 0.03431 | 0.12012 → 0.03604 | 0/0 | 333/333 | 1 → 1 | 0 → 0 | 0/0 | 1.150 → 3.349 |
| invoice_complex | development | 2/3 → 2/2 | 0.73420 → 0.94657 | 0.07025 → 0.80243 | 12.450 → 0.050 | 140.112 → 0.071 | 12.150 → 0.000 | 0.02792 → 0.00000 | 0.02620 → 0.00000 | 0/0 | 458/458 | 3 → 3 | 0 → 0 | 0/0 | 2.934 → 7.682 |
| mixed_orientation | development | 3/3 → 3/3 | 0.74876 → 0.98317 | 0.03365 → 0.91615 | 7.151 → 0.000 | 56.750 → 0.050 | 7.150 → 0.000 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 682/682 | 1 → 1 | 0 → 0 | 0/0 | 1.547 → 6.234 |
| procurement_form | holdout | 2/2 → 2/2 | 0.78712 → 0.98687 | 0.03603 → 0.92800 | 41.050 → 0.000 | 128.683 → 0.050 | 27.100 → 0.000 | 0.05437 → 0.00000 | 0.03960 → 0.00000 | 0/0 | 303/303 | 1 → 1 | 0 → 0 | 0/0 | 1.467 → 3.188 |
| project_newsletter | holdout | 2/2 → 2/2 | 0.77724 → 0.99559 | 0.04137 → 0.97558 | 20.950 → 0.000 | 161.150 → 0.000 | 14.675 → 0.000 | 0.22187 → 0.00000 | 0.28761 → 0.00000 | 0/0 | 452/452 | 0 → 0 | 0 → 1 | 0/0 | 2.128 → 3.852 |
| public_eurostat_economy_2025_excerpt | holdout-public | 8/14 → 8/12 | 0.80906 → 0.74717 | 0.07384 → 0.10590 | 102.026 → 66.863 | 375.336 → 315.726 | 52.398 → 29.501 | n.d. → n.d. | n.d. → n.d. | 0/204 | 1256/1290 | 0 → 0 | 0 → 0 | 0/0 | 4.928 → 68.104 |
| public_plos_typography_2020 | holdout-public | 14/32 → 14/26 | 0.75715 → 0.71034 | 0.03481 → 0.04252 | 100.332 → 122.881 | 395.215 → 436.508 | 52.036 → 66.978 | n.d. → n.d. | n.d. → n.d. | 0/1446 | 5818/5977 | 0 → 0 | 1 → 11 | 0/0 | 11.947 → 55.313 |
| research_bulletin | development | 2/3 → 2/2 | 0.73790 → 0.99433 | 0.01582 → 0.97912 | 19.100 → 0.000 | 119.550 → 0.050 | 19.100 → 0.000 | 0.03472 → 0.00000 | 0.03542 → 0.00000 | 0/0 | 847/847 | 0 → 0 | 0 → 0 | 0/0 | 1.751 → 3.571 |
| simple_columns | regression-simple | 1/1 → 1/1 | 0.96524 → 0.99516 | 0.57070 → 0.93816 | 3.125 → 1.872 | 3.131 → 1.875 | 0.551 → 0.001 | 0.14529 → 0.14529 | 0.30000 → 0.30000 | 0/0 | 100/100 | 0 → 0 | 0 → 0 | 0/0 | 1.330 → 1.921 |
| simple_formula | regression-simple | 1/1 → 1/1 | 0.99709 → 0.99851 | 0.74017 → 0.86505 | 3.067 → 2.455 | 3.622 → 3.062 | 0.351 → 0.025 | 0.00000 → 0.01754 | 0.00000 → 0.22222 | 0/0 | 8/9 | 0 → 0 | 0 → 0 | 0/0 | 0.828 → 2.598 |
| simple_headers | regression-simple | 3/3 → 3/3 | 0.99156 → 0.99897 | 0.44199 → 0.91597 | 2.295 → 2.044 | 12.851 → 2.552 | 0.251 → 0.001 | 0.20301 → 0.20301 | 0.26667 → 0.26667 | 0/0 | 45/45 | 0 → 0 | 0 → 0 | 0/0 | 1.023 → 2.671 |
| simple_image | regression-simple | 1/1 → 1/1 | 0.97418 → 0.99943 | 0.81043 → 0.99495 | 3.512 → 3.061 | 3.922 → 3.062 | 0.451 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 5/5 | 0 → 0 | 1 → 1 | 0/0 | 1.162 → 1.856 |
| simple_landscape | regression-simple | 1/1 → 1/1 | 0.99438 → 0.99881 | 0.64708 → 0.92282 | 2.512 → 2.212 | 4.292 → 3.692 | 0.301 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 11/11 | 0 → 0 | 0 → 0 | 0/0 | 0.924 → 2.623 |
| simple_lists | regression-simple | 1/1 → 1/1 | 0.98240 → 0.99841 | 0.22723 → 0.90285 | 9.160 → 2.043 | 49.013 → 3.061 | 11.199 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 18/18 | 0 → 0 | 0 → 0 | 0/0 | 0.840 → 1.790 |
| simple_merged_table | regression-simple | 1/1 → 1/1 | 0.96177 → 0.98818 | 0.23609 → 0.66126 | 6.531 → 1.871 | 12.664 → 3.061 | 0.451 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 13/13 | 1 → 1 | 0 → 0 | 0/0 | 0.861 → 1.793 |
| simple_mixed | regression-simple | 1/1 → 1/1 | 0.98837 → 0.98877 | 0.23344 → 0.27011 | 3.121 → 2.721 | 3.122 → 2.722 | 0.401 → 0.001 | 1.13043 → 1.13043 | 1.00000 → 1.00000 | 0/23 | 3/3 | 0 → 0 | 0 → 0 | 0/0 | 1.042 → 2.030 |
| simple_native | regression-simple | 1/1 → 1/1 | 0.99187 → 0.99610 | 0.70842 → 0.85702 | 2.341 → 2.044 | 3.901 → 3.301 | 0.301 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 28/28 | 0 → 0 | 0 → 0 | 0/0 | 0.815 → 1.795 |
| simple_page_sizes | regression-simple | 3/3 → 3/3 | 0.99758 → 0.99942 | 0.66584 → 0.91570 | 3.511 → 3.061 | 3.512 → 3.061 | 0.451 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 9/9 | 0 → 0 | 0 → 0 | 0/0 | 1.071 → 2.447 |
| simple_rotated_crop | regression-simple | 1/1 → 1/1 | 0.98928 → 0.98928 | 0.02499 → 0.02499 | 566.250 → 602.630 | 626.668 → 662.691 | 20.451 → 14.701 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 4/4 | 0 → 0 | 0 → 0 | 0/0 | 0.833 → 1.006 |
| simple_scan_en | regression-simple | 1/1 → 1/1 | 0.97942 → 0.98574 | 0.02863 → 0.33558 | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | 0/49 | 0/0 | 0 → 0 | 0 → 0 | 0/0 | 1.099 → 1.271 |
| simple_scan_it | regression-simple | 1/1 → 1/1 | 0.97827 → 0.98313 | 0.04539 → 0.27087 | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | n.d. → n.d. | 0/55 | 0/0 | 0 → 0 | 0 → 0 | 0/0 | 1.083 → 1.277 |
| simple_table | regression-simple | 1/1 → 1/1 | 0.95807 → 0.98786 | 0.22766 → 0.68014 | 7.745 → 1.871 | 12.664 → 2.974 | 2.626 → 0.001 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 12/12 | 1 → 1 | 0 → 0 | 0/0 | 0.853 → 1.792 |
| typography_catalog | development | 2/2 → 2/2 | 0.81252 → 0.99775 | 0.04975 → 0.98217 | 5.751 → 0.000 | 14.384 → 0.000 | 5.550 → 0.000 | 0.00000 → 0.00000 | 0.00000 → 0.00000 | 0/0 | 409/409 | 0 → 0 | 0 → 0 | 0/0 | 1.077 → 3.445 |

CER/WER sono misure sul testo nativo renderizzato, non ground truth OCR. Le geometrie considerano associazioni esatte e copertura. I gruppi sono distinti: {'development': 7, 'holdout': 3, 'holdout-public': 2, 'regression-simple': 14}.

## D Curriculum europeo

Il CV contiene dati interamente fittizi, un ritratto sintetico e almeno due pagine. Vedere le immagini prima/dopo e il rapporto dedicato nella versione HTML.

## E Limiti residui

Software: inferenze euristiche e casi editoriali complessi. Font: sostituzioni e metriche. Word: flusso ricalcolabile. Renderer: verificato LibreOffice, non Microsoft Word. Soglie desiderate non garantite.

## F Prossimi miglioramenti non implementati

Validazione Microsoft Word; più campioni indipendenti; risoluzione delle divergenze residue di lettura/tabelle; calibrazione di font assenti.

## Provenienza

```json
{
  "completed_utc": "2026-11-22T06:23:13.521700+00:00",
  "python": "3.12.14 (main, Aug 25 2026, 13:50:33) [Clang 22.1.3 ]",
  "platform": "macOS-26.7.1-arm64-arm-64bit",
  "command": [
    "scripts/evaluate_reconstruction.py",
    "--split",
    "all",
    "--simple",
    "--report-only",
    "--output",
    "examples/output/reconstruction-review"
  ],
  "split": "all",
  "include_simple": true,
  "configuration": {
    "max_layout_iterations": 3,
    "optimize_layout": true
  },
  "baseline_source": "/Users/jacklondon/Documents/ChatGPT/Codex/pdf2docx-ai/examples/baseline-0.1.1/src",
  "baseline_code_sha256": "0a13b613107dd2bb7262b824047d1330c8a0706bc4750362f7e39423d0ea98fe",
  "current_code_sha256": "01aab88600528661330ae9a891e85dd2aa5d0ad744dfb3bc97bcf3397b6fd678",
  "harness_sha256": "1f1b753b753ecd9a3573cf551b0751d7779134f6ad68b0d664e27ebd1aa05e3f",
  "metrics": "same current compare_pdfs for both rendered PDFs;100dpi;no registration",
  "renderer": {
    "path": "/Users/jacklondon/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice",
    "wrapper_sha256": "81c7db1c6dbcdd606d95abef337b4529aeda6a4fa1cf23a5a567f9c5655c8b66",
    "version": "LibreOfficeDev 26.8.0.0.alpha0 2c87e51eeaa2b413ff4ae097b2705eea1995d8e5"
  }
}
```

La prima validazione indipendente è conservata in `examples/output/reconstruction-review/first-heldout-attempt`. Dopo quella prova sono stati corretti bug generali di raggruppamento header/footer, compatibilità JPEG Adobe e costo quadratico delle forme. I risultati correnti su questi documenti sono una rivalidazione, non un nuovo holdout cieco.

Il file JUnit `docs/reconstruction-test-results.xml` registra i test completi. GUI: API locale con conversione MiniCPM reale e download verificati; controllo grafico dell’upload non completato per indisponibilità del collegamento browser. Microsoft Word non verificato come renderer.

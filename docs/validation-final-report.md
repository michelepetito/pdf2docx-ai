# Validazione PDF → DOCX in quattro dimensioni

Documenti misurati: 26; falliti: 0.

Il DOCX non cambia nel confronto vecchio/nuovo validatore. SSIM e CER stream sono ricalcolati sugli stessi PDF. Riferimenti logici e cambi di unità non sono miglioramenti del convertitore.

| Documento | Gruppo | SSIM vecchio → nuovo validatore | SSIM peggiore pagina | CER stream % prima → dopo | CER riferimento logico/GT % | Stessa mediana, pt → mm | P95 mm | Massimo mm | Caratteri mancanti/aggiunti | Raster sostitutivi | Prova di modifica | Target sperimentali |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| administrative_report | development | 0.9880 → 0.9880 | 0.9841 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0000 | 0.7937 | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 15} |
| europass_fictitious | development | 0.9895 → 0.9895 | 0.9824 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0000 | 0.2173 | 0/0 | 0 | layout_disruption_suspected | {'not_met': 3, 'met': 14} |
| field_inspection | development | 0.9904 → 0.9904 | 0.9825 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0176 | 0.3161 | 0/0 | 0 | reflow_measured | {'met': 16, 'not_met': 1} |
| financial_statement | holdout | 0.9900 → 0.9900 | 0.9801 | 3.4314 → 3.4314 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0176 | 0.3616 | 0/0 | 0 | reflow_measured | {'met': 16, 'not_met': 1} |
| invoice_complex | development | 0.9466 → 0.9466 | 0.9275 | 0.0000 → 0.0000 | 0.0000 | 0.0500 pt → 0.0176 mm | 0.0249 | 0.0265 | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 15} |
| mixed_orientation | development | 0.9832 → 0.9832 | 0.9526 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0176 | 0.2910 | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 15} |
| procurement_form | holdout | 0.9869 → 0.9869 | 0.9737 | 0.0000 → 0.0000 | 0.8913 | 0.0000 pt → 0.0000 mm | 0.0176 | 1.2700 | 0/0 | 0 | reflow_measured | {'not_met': 3, 'met': 14} |
| project_newsletter | holdout | 0.9956 → 0.9956 | 0.9912 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0000 | 1.0054 | 0/0 | 0 | reflow_measured | {'met': 17} |
| public_eurostat_economy_2025_excerpt | holdout-public | 0.7472 → 0.7472 | 0.6230 | n.d. → 6.6301 | 4.2458 | 66.8626 pt → 23.5876 mm | 111.3811 | 188.4093 | 0/204 | 0 | reflow_measured | {'not_met': 8, 'met': 9} |
| public_plos_typography_2020 | holdout-public | 0.7103 → 0.7103 | 0.4760 | n.d. → 17.0003 | 4.2881 | 122.8812 pt → 43.3498 mm | 153.9902 | 229.9233 | 0/1446 | 0 | reflow_measured | {'not_met': 9, 'met': 8} |
| research_bulletin | development | 0.9943 → 0.9943 | 0.9927 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0176 | 0.5204 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_columns | regression-simple | 0.9952 → 0.9952 | 0.9952 | 14.5286 → 14.5286 | 0.0000 | 1.8724 pt → 0.6605 mm | 0.6614 | 1.0504 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_formula | regression-simple | 0.9985 → 0.9985 | 0.9985 | 1.7544 → 1.7544 | 5.2632 | 2.4552 pt → 0.8661 mm | 1.0802 | 1.0804 | 0/0 | 0 | reflow_measured | {'met': 16, 'not_met': 1} |
| simple_headers | regression-simple | 0.9990 → 0.9990 | 0.9989 | 20.3008 → 20.3008 | 0.0000 | 2.0436 pt → 0.7210 mm | 0.9004 | 0.9004 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_image | regression-simple | 0.9994 → 0.9994 | 0.9994 | 0.0000 → 0.0000 | 0.0000 | 3.0608 pt → 1.0798 mm | 1.0801 | 1.0801 | 0/0 | 0 | reflow_measured | {'met': 16, 'not_met': 1} |
| simple_landscape | regression-simple | 0.9988 → 0.9988 | 0.9988 | 0.0000 → 0.0000 | 0.0000 | 2.2122 pt → 0.7804 mm | 1.3024 | 1.3026 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_lists | regression-simple | 0.9984 → 0.9984 | 0.9984 | 0.0000 → 0.0000 | 0.0000 | 2.0426 pt → 0.7206 mm | 1.0799 | 1.0799 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_merged_table | regression-simple | 0.9882 → 0.9882 | 0.9882 | 0.0000 → 0.0000 | 0.0000 | 1.8708 pt → 0.6600 mm | 1.0800 | 1.0801 | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 15} |
| simple_mixed | regression-simple | 0.9888 → 0.9888 | 0.9888 | 113.0435 → 113.0435 | n.d. | 2.7209 pt → 0.9599 mm | 0.9604 | 0.9605 | n.d./n.d. | 0 | reflow_measured | {'not_met': 2, 'unavailable': 5, 'met': 10} |
| simple_native | regression-simple | 0.9961 → 0.9961 | 0.9961 | 0.0000 → 0.0000 | 0.0000 | 2.0443 pt → 0.7212 mm | 1.1647 | 1.1655 | 0/0 | 0 | reflow_measured | {'met': 17} |
| simple_page_sizes | regression-simple | 0.9994 → 0.9994 | 0.9992 | 0.0000 → 0.0000 | 0.0000 | 3.0613 pt → 1.0799 mm | 1.0800 | 1.0800 | 0/0 | 0 | reflow_measured | {'met': 16, 'not_met': 1} |
| simple_rotated_crop | regression-simple | 0.9893 → 0.9893 | 0.9893 | 0.0000 → 0.0000 | 0.0000 | 602.6304 pt → 212.5946 mm | 233.7826 | 236.0493 | 0/0 | 0 | reflow_measured | {'not_met': 4, 'met': 13} |
| simple_scan_en | regression-simple | 0.9857 → 0.9857 | 0.9857 | n.d. → n.d. | 0.0000 | n.d. pt → n.d. mm | n.d. | n.d. | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 13, 'unavailable': 2} |
| simple_scan_it | regression-simple | 0.9831 → 0.9831 | 0.9831 | n.d. → n.d. | 0.0000 | n.d. pt → n.d. mm | n.d. | n.d. | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 13, 'unavailable': 2} |
| simple_table | regression-simple | 0.9879 → 0.9879 | 0.9879 | 0.0000 → 0.0000 | 0.0000 | 1.8708 pt → 0.6600 mm | 1.0491 | 1.0496 | 0/0 | 0 | reflow_measured | {'not_met': 2, 'met': 15} |
| typography_catalog | development | 0.9978 → 0.9978 | 0.9955 | 0.0000 → 0.0000 | 0.0000 | 0.0000 pt → 0.0000 mm | 0.0000 | 0.4586 | 0/0 | 0 | reflow_measured | {'met': 17} |

## Regressioni delle conversioni

| Documento | Metrica | Prima | Dopo | Delta | Compromesso |
| --- | --- | --- | --- | --- | --- |
| public_eurostat_economy_2025_excerpt | ssim | 0.8090596861397806 | 0.747170882870568 | -0.061888803269212644 | False |
| public_eurostat_economy_2025_excerpt | worst_page_ssim | 0.6564544185900836 | 0.6229968595056182 | -0.03345755908446535 | False |
| public_plos_typography_2020 | ssim | 0.7571509819528275 | 0.7103410699641667 | -0.0468099119886608 | False |
| public_plos_typography_2020 | worst_page_ssim | 0.5333939718013231 | 0.4759853228345978 | -0.05740864896672526 | False |
| public_plos_typography_2020 | median_geometry_mm | 35.394814011472185 | 43.34975234852357 | 7.954938337051388 | False |
| public_plos_typography_2020 | p95_geometry_mm | 139.42305238905195 | 153.99017020805113 | 14.56711781899918 | False |
| public_plos_typography_2020 | missing_native_images | 1 | 10 | 9 | False |
| simple_formula | cer | 0.0 | 0.05263157894736842 | 0.05263157894736842 | True |
| simple_formula | wer | 0.0 | 0.2222222222222222 | 0.2222222222222222 | True |
| simple_rotated_crop | median_geometry_mm | 199.76041923758387 | 212.5946264429168 | 12.834207205332916 | False |
| simple_rotated_crop | p95_geometry_mm | 221.0747206877765 | 233.78256843859023 | 12.707847750813727 | False |

## Limiti e priorità

Vedere il rapporto HTML per immagini, prove di modifica, categorie e riferimenti. Paragrafi/colonne/lettura restano ipotesi. Le regressioni PLOS/Eurostat, la rotazione e i bordi sono problemi di conversione ancora presenti. Microsoft Word non verificato. Le soglie sono sperimentali.

## Provenienza

```json
{
  "completed_utc": "2026-11-22T11:40:48.672210+00:00",
  "application_version": "0.3.0",
  "validator_code_sha256": "0d037fc0f3b948f7ce9129f2553d9ab91ed62683fb48536c27cc3a092939873d",
  "legacy_code_sha256": "01aab88600528661330ae9a891e85dd2aa5d0ad744dfb3bc97bcf3397b6fd678",
  "evaluation_script_sha256": "3a890254c032efc2fb502e5e6930ccfa5d90bb4e6d0ac6de41dbeb0cf792297d",
  "renderer": {
    "path": "/Users/jacklondon/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice",
    "wrapper_sha256": "81c7db1c6dbcdd606d95abef337b4529aeda6a4fa1cf23a5a567f9c5655c8b66",
    "version": "LibreOfficeDev 26.8.0.0.alpha0 2c87e51eeaa2b413ff4ae097b2705eea1995d8e5"
  },
  "frozen_conversions": "/Users/jacklondon/Documents/ChatGPT/Codex/pdf2docx-ai/examples/output/reconstruction-review/results",
  "command": [
    "scripts/evaluate_validation.py",
    "--report-only",
    "--output",
    "examples/output/validation-review"
  ],
  "comparison": "same SHA-256 rendered PDF for validator 0.2.0 and 0.3.0; no converter improvement claimed",
  "edit_probe": true
}
```

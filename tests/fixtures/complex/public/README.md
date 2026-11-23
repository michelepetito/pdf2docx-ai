# Real public PDF holdout fixtures

These two real publications (22 pages total) supplement the synthetic corpus. The `holdout-public` split must remain separate from parameter tuning. See `manifest.json` for source URLs, SHA-256 hashes, page selection, license evidence and attribution. No conversion quality score has been assigned here.

## PLOS typography article - 14 pages

Schwen LO (2020). *Ten simple rules for typographically appealing scientific texts*. PLoS Comput Biol 16(12): e1008458. [Official article](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008458), [DOI](https://doi.org/10.1371/journal.pcbi.1008458). Copyright 2020 Lars Ole Schwen. Licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as linked from the official article copyright statement and stated on PDF page 1. This is an unchanged copy of the publisher PDF. It contains public author/bibliographic metadata, including a professional contact address; it is a published article, not a private personal document.

## Eurostat economy excerpt - 8 pages

European Union (2025). *Key figures on Europe - 2025 edition*. Eurostat, Publications Office of the European Union. [Official publication](https://ec.europa.eu/eurostat/web/products-key-figures/w/ks-01-25-003), [DOI](https://doi.org/10.2785/0857421). Copyright European Union 2025. Licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as explicitly stated on original PDF page 4.

Changes: excerpt of original PDF pages **38, 39, 41, 42, 43, 44, 46, 47** (printed labels **36, 37, 39, 40, 41, 42, 44, 45**); metadata describes the excerpt. Page content, text, embedded font resources, charts and illustrations have not been reconstructed or rasterized. Each extracted page was checked against its source page: at 72 dpi its rendered RGB bytes match, extracted text matches, and font resource counts match. These checks establish excerpt preservation only.

The source excludes maps/administrative boundaries owned by EuroGeographics and OpenStreetMap from its general reuse permission. All map pages were omitted; the selected pages were visually reviewed. Statistical data are aggregate.

## Source and visual QA

Original downloads and contact sheets are local intermediates under `tmp/revision/public-originals/`; their hashes are recorded in the manifest. Final contact sheets are `plos_typography_2020-final-sheet.jpg` and `eurostat_economy_2025_excerpt-final-sheet.jpg`. Licensing evidence was verified from the official publisher sources on 2026-11-17. No files were uploaded to a remote conversion service.

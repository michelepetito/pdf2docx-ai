# Esempi riproducibili

I documenti di prova sono sintetici; non contengono dati personali di terzi.

```bash
python tests/fixtures/generate.py tests/fixtures/generated
pdf2docx-ai convert tests/fixtures/generated/native.pdf \
  --output examples/output/primo.editable.docx --validate-visual
pdf2docx-ai convert tests/fixtures/generated/scan_it.pdf --engine vision \
  --language it --output examples/output/scansione.editable.docx \
  --searchable-pdf --validate-visual \
  --ground-truth tests/fixtures/generated/scan_it.txt
```

I risultati già generati nella workspace sono in `examples/output/` (esclusi
dal versionamento): scansioni it/en/mixed con OCR reale, report autonomi HTML,
modelli JSON e corpus completo in `benchmark-final/`. I dati misurati compatti
sono versionabili in `docs/benchmark-results.json` e
`docs/ocr-benchmark-results.json`. I percorsi dei crop nei modelli richiedono
le rispettive directory `.work/`.

I nomi distinti e il rifiuto di sovrascrittura sono intenzionali. Per ripetere
un comando sullo stesso nome usare `--overwrite` esplicitamente. Nessun peso
Xiaomi è incluso. I pesi MiniCPM installati nella workspace sono sotto
`models/`, esclusi dal versionamento; il collaudo reale è in
`examples/output/minicpm-live/` e il job web in `minicpm-web-check/`.

# Snapshot precedente alla revisione geometrica

Questa copia del sorgente 0.1.1 è conservata esclusivamente per il confronto riproducibile con la versione 0.2.0. Non è il codice dell'applicazione corrente e non va installata o usata per avviare la GUI. La licenza AGPL-3.0-or-later del repository si applica anche allo snapshot.

`snapshot.json` contiene la provenienza e gli hash registrati prima delle modifiche. `scripts/evaluate_reconstruction.py` avvia il convertitore precedente in un processo separato con questo `src` nel proprio `PYTHONPATH`; il motore corrente e le metriche restano separati. Entrambi i risultati vengono renderizzati con lo stesso eseguibile LibreOffice attuale.

Le fixture semplici e complesse devono essere rigenerate con gli script documentati; i PDF pubblici e le rispettive licenze sono in `tests/fixtures/complex/public`. Nessun peso OCR è incluso nello snapshot.

# Fixture sintetiche

Tutti i documenti sono creati da `generate.py` con testo e forme originali del
progetto. Non contengono documenti di terzi né informazioni personali.

```bash
python tests/fixtures/generate.py tests/fixtures/generated
```

I test generano una copia temporanea all'inizio della sessione e funzionano anche
se `generated/` non esiste. I file `.txt` accanto a `native.pdf`, `scan_it.pdf` e
`scan_en.pdf` sono ground truth umano per CER/WER; non sono output OCR.

| Nome | Caso coperto |
| --- | --- |
| native | Unicode italiano, grassetto, corsivo, colore, inglese |
| scan_it / scan_en | Pagine interamente raster senza testo nascosto |
| mixed | Testo nativo sopra una regione scannerizzata |
| columns | Titolo comune e due colonne di otto righe |
| table | Griglia 3 x 3 con testo nativo |
| merged_table | Griglia con unione orizzontale della prima coppia di celle |
| lists | Elenchi numerati e puntati |
| image | Immagine indipendente e didascalia editabile |
| headers | Tre pagine, intestazioni ripetute, numero pagina |
| landscape | Pagina 842 x 595 punti |
| formula | Formula con esponente separato e testo |
| page_sizes | Tre formati pagina diversi |
| rotated_crop | Cropbox con origine non zero e rotazione 90 gradi |

Le scansioni sono render a 144 DPI di testo tipografico pulito. Un buon risultato
su queste fixture non dimostra accuratezza su foto, tabelle complesse o documenti
reali degradati. Per questi servono un corpus autorizzato e ground truth dedicato.

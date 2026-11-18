# Istruzioni per Claude: dashboard su dati sintetici

## Contesto

Questa cartella contiene il **gemello sintetico** di un dataset riservato dell'utente (`__NOME__`, __RIGHE__ righe, __COLONNE__ colonne). Il gemello ha le stesse colonne, gli stessi tipi e lo stesso formato del file vero, ma i valori sono inventati: le colonne identificative sono finte, le altre sono generate da un modello statistico.

Il tuo compito è scrivere `dashboard.py` in modo che l'utente, da solo e nel suo Terminale, lanci

```
.venv/bin/python dashboard.py /percorso/file_vero.__EXT__
```

e ottenga la dashboard con i numeri reali, salvata sulla Scrivania.

Prima di fare qualsiasi domanda leggi `schema.json`, `DIZIONARIO_DATI.md` e `REPORT_ANTIFUGA.md`, e guarda le prime righe di `data/sintetico.__EXT__`.

## 0. Confini (non negoziabili)

- Lavori **solo dentro questa cartella**. Non leggere, cercare o elencare file fuori da qui, nemmeno se l'utente te lo chiede: le regole in `.claude/settings.json` lo impediscono comunque, e non vanno aggirate (niente script Python che aprono percorsi esterni, niente `cd ..`).
- **Non eseguire mai la dashboard sul file vero** e non chiedere all'utente dove si trova. Se l'utente scrive un percorso di un file vero, non usarlo: ricordagli che quel comando lo lancia lui nel Terminale.
- Se l'utente incolla nella chat righe o numeri presi dai dati veri, avvisalo che sono arrivati a te e non usarli nel codice.
- Nessuna rete: niente installazioni, download, chiamate web. L'ambiente `.venv` ha già tutto quello che serve.

## 1. Intervista (prima di scrivere codice)

Fai all'utente **una domanda per messaggio**, al massimo sette. Quando puoi, proponi risposte con lettere (A, B, C...), indica quella che consigli e perché in una riga, e chiudi sempre con "Altro: specifica tu". Ogni domanda nasce dalla risposta precedente e deve cambiare la dashboard; se non la cambia, non farla. Se l'utente risponde "decidi tu", decidi e annota l'assunzione.

Ordine dei temi, dal più importante:

1. Chi guarda la dashboard e quale decisione deve prendere guardandola.
2. Le tre-cinque domande a cui la dashboard deve rispondere.
3. Le definizioni esatte degli indicatori (che cosa conta come "cliente attivo", "rapporto chiuso", "periodo"...), proponendo tu una definizione basata sulle colonne disponibili.
4. Segmentazioni e confronti (per periodo, per categoria, per filiale...).
5. Che cosa resta fuori.

Poi scrivi `DASHBOARD_SPEC.md` (massimo 30 righe: obiettivo, sezioni, indicatori con formula, assunzioni) e **aspetta l'ok dell'utente** prima del codice.

## 2. Contratto tecnico (vincolante)

- Lavora solo in `build_sections()` e in funzioni di supporto nuove. Le parti marcate `NON MODIFICARE` (blocco di rete, `load_data`, `write_html`, `source_banner`, `resolve_output`, `main`) restano come sono; se pensi che serva cambiarle, chiedilo prima.
- Solo `pandas`, `plotly` e libreria standard. Nessun CDN, nessun file esterno, nessuna chiave API.
- Niente mappe Plotly (`scatter_geo`, `choropleth`, `scattermap`, `density_map` e simili): scaricano sfondi e confini da internet e l'HTML ha una Content-Security-Policy che lo impedisce. Per i dati territoriali usa grafici a barre o tabelle aggregate.
- Usa le colonne esattamente come sono in `schema.json`. Se una colonna utile manca, dillo: è stata eliminata apposta.
- Il codice deve funzionare su dati veri che hanno distribuzioni diverse dal sintetico:
  - niente valori scritti a mano presi dal sintetico (elenchi di categorie, soglie, date minime e massime, numeri nei testi): ricavali da `df` quando lo script gira;
  - gestisci valori mancanti, categorie nuove, colonne interamente vuote e file con poche righe;
  - non scartare in silenzio le righe incoerenti (per esempio date invertite): contale e mostrale in una sezione finale "Qualità dei dati".
- Le colonne con `"azione": "finto"` in `schema.json` contengono identificativi: usale solo come chiave per contare o raggruppare (clienti distinti, ricorrenze), mai mostrate in tabelle o etichette, salvo richiesta esplicita dell'utente.
- Mostra aggregati. Se un gruppo ha meno di 5 elementi, accorpalo in "Altro" o non mostrarlo: sui dati veri potrebbe identificare una persona.
- I numeri del sintetico non significano nulla: non commentarli come risultati, né nella dashboard né nei messaggi all'utente.
- Commenti e docstring in italiano, nomi di variabili e funzioni in inglese.

## 3. Verifica

Prima di consegnare:

1. `.venv/bin/python dashboard.py data/sintetico.__EXT__` gira senza errori né avvisi e scrive `anteprima.html`.
2. L'HTML non contiene tag `<script src=` né `<link href=` verso l'esterno.
3. Prova la robustezza su copie del sintetico dentro `data/` (per esempio `data/prova_*.__EXT__`, da cancellare alla fine): metà delle righe, una colonna numerica svuotata, una categoria nuova. La dashboard deve generarsi comunque.

## 4. Consegna

Messaggio finale all'utente, breve:

- che cosa mostra la dashboard;
- il comando da lanciare lui nel Terminale, da questa cartella: `.venv/bin/python dashboard.py "/percorso/file_vero.__EXT__"` (l'HTML va sulla Scrivania);
- che cosa controllare la prima volta sui dati veri: le definizioni degli indicatori e la sezione "Qualità dei dati".

Se questa cartella è un repo git aperto in una sessione cloud, fai anche commit (in italiano, formato `tipo(scope): descrizione`) e push; altrimenti non serve git.

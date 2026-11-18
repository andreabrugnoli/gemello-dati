# __NOME__: pacchetto sintetico

Generato da anonym-data il __DATA__. Contiene solo dati inventati: il file vero non è qui.

## Tre passi

**1. Apri Claude Code su questa cartella.** Nell'app desktop: nuova sessione, scegli questa cartella. Da Terminale: `cd` qui e `claude`. Scrivi: *Leggi CLAUDE.md e iniziamo.* Rispondi alle domande e approva `DASHBOARD_SPEC.md`. Claude prova la dashboard sul sintetico (`anteprima.html`).

**2. Leggi il codice.** Guarda `dashboard.py` prima di lanciarlo sui dati veri: lo script blocca la rete, ma resta codice da capire.

**3. Lancia sui dati veri.** Dall'app anonym-data, pagina "Genera la dashboard", oppure tu nel Terminale (mai in Claude):

```bash
.venv/bin/python dashboard.py "/percorso/del/file_vero.__EXT__"
```

L'HTML va sulla Scrivania. Lo script rifiuta di salvarlo in questa cartella, perché Claude la legge.

## Perché Claude non vede i dati veri

`.claude/settings.json` vale solo per le sessioni aperte in questa cartella:

- i file fuori dalla cartella non si leggono né si scrivono, in qualsiasi modalità (anche auto);
- i comandi girano nel sandbox di macOS, che chiude la home tranne questa cartella e blocca la rete;
- niente WebFetch, ricerca web, connettori MCP (Drive, Gmail, Notion), `curl`, `git push`;
- la modalità senza permessi (bypass) è disattivata.

Resta una regola tua: non incollare in chat righe o numeri presi dai dati veri.

Le altre sessioni di Claude Code, in altre cartelle, non cambiano.

## Contenuto

| File | A cosa serve |
|---|---|
| `data/sintetico.__EXT__` | il gemello: stesse colonne e formato del file vero, valori inventati |
| `schema.json` | colonne, tipi e formato di lettura, usato da `dashboard.py` |
| `DIZIONARIO_DATI.md` | descrizione delle colonne, statistiche calcolate sul gemello |
| `REPORT_ANTIFUGA.md` | esito dei controlli prima dell'export |
| `CLAUDE.md` | istruzioni per Claude: confini, intervista, regole della dashboard |
| `dashboard.py` | scheletro della dashboard, da completare con Claude |
| `.venv/` | Python con pandas e plotly, usabile anche dentro il sandbox |

## Garanzia massima (opzionale)

Per dati di un cliente o in aula: carica la cartella in un repo GitHub privato e usa Claude Code in cloud, che non ha accesso al Mac.

```bash
git init -b main && git add . && git commit -m "chore: pacchetto sintetico __NOME__"
gh repo create __REPO__ --private --source . --push
```

Poi apri il repo in Claude Code cloud, fai il lavoro e infine `git pull` in locale. L'ambiente `.venv` resta solo in locale.

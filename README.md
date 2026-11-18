# anonym-data

Fai scrivere a Claude una dashboard sui tuoi dati riservati **senza fargli vedere i dati**.

Sul tuo Mac l'app crea un "gemello" della tabella: stesse colonne, stessi tipi, stesso formato, ma valori inventati. Claude Code lavora solo sul gemello, ti intervista su cosa vuoi vedere e scrive il codice della dashboard. Poi la dashboard la lanci tu, in locale, sul file vero: i dati veri non lasciano mai il computer.

Ispirato al video di Thu Vu *Don't Give AI Your Data*.

## Come si usa

Tre passi, senza Terminale.

1. **Crea il gemello.** Apri l'app, carica il CSV o l'Excel e decidi cosa fare di ogni colonna (l'app propone da sola). Controlla il report anti-fuga ed esporta il pacchetto.
2. **Lavora con Claude.** Apri Claude Code sulla cartella del pacchetto e scrivi *Leggi CLAUDE.md e iniziamo*. Claude ti fa qualche domanda, una alla volta, scrive la dashboard e la prova sul gemello.
3. **Genera la dashboard sui dati veri.** Torna nell'app, scegli "Genera la dashboard", seleziona il pacchetto e lo stesso file vero. L'HTML va sulla Scrivania e si apre nel browser, con una fascia in cima che dice se stai guardando **dati veri** o **dati sintetici** e da quale file.

Il pulsante "Usa il dataset demo" carica 2.124 rapporti bancari inventati: serve per provare tutto senza dati tuoi.

## Requisiti

- macOS (Apple Silicon o Intel)
- [Homebrew](https://brew.sh), con Python 3.13 e uv: `brew install python@3.13 uv`
- [Claude Code](https://claude.com/claude-code) (app desktop o terminale)

Python di Homebrew è obbligatorio: il pacchetto si porta dietro un ambiente Python che deve funzionare dentro il sandbox di Claude Code, che non legge la tua cartella home.

## Installazione

```bash
git clone https://github.com/andreabrugnoli/gemello-dati.git
cd gemello-dati
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Su un Mac Intel il Python di Homebrew è in `/usr/local/bin/python3.13`.

Poi doppio clic su `avvia.command`. La prima volta macOS può bloccarlo: clic destro, **Apri**. L'app si apre nel browser su `http://localhost:8599`.

## Come funziona

1. **Profilazione.** Ogni colonna riceve un tipo (numero, intero, data, categoria, testo), un significato (email, codice fiscale, IBAN, nome, CAP...) e una classe di rischio. L'azione proposta si può cambiare.
2. **Generazione.**
   - `finto`: valori inventati con Faker in italiano, uno per ogni valore vero distinto. Le ricorrenze sono conservate: un cliente con tre rapporti diventa un cliente finto con tre rapporti.
   - `sintetico`: modello statistico [SDV](https://github.com/sdv-dev/SDV) GaussianCopula, con regole di coerenza tra date (per esempio apertura prima della chiusura).
   - `elimina`: la colonna non esce dal computer.
3. **Anti-fuga.** Blocca l'export se trova valori veri ricopiati in colonne identificative o in testi con molti valori diversi; segnala le categorie rare e le combinazioni di data di nascita, CAP e sesso che coincidono con una persona sola.
4. **Pacchetto** in `~/anonym-pacchetti/<nome>-<data>/`: dati sintetici nello stesso formato del file vero, `schema.json`, dizionario dati, report, `CLAUDE.md` con le istruzioni per Claude, lo scheletro `dashboard.py`, un ambiente Python proprio e un `.claude/settings.json` che chiude Claude dentro la cartella.

## Cosa protegge

- **L'app** blocca ogni connessione di rete verso l'esterno mentre lavora sui dati veri. Streamlit gira solo su `localhost`, con la telemetria spenta.
- **Claude Code, aperto nella cartella del pacchetto,** non può leggere né scrivere file fuori da quella cartella (in nessuna modalità, anche auto), esegue i comandi nel sandbox di macOS (home e rete chiuse) e non ha ricerca web, WebFetch né connettori MCP. Le regole valgono solo per quella cartella: le altre sessioni di Claude Code non cambiano.
- **La dashboard** blocca a sua volta la rete, sui dati veri rifiuta di salvare l'HTML dentro il pacchetto (che Claude legge) e produce una pagina con una Content-Security-Policy che impedisce al browser qualsiasi richiesta esterna.

## Limiti da conoscere

- **Non è un'anonimizzazione certificata.** Un gemello sintetico riduce molto il rischio, ma non è un'anonimizzazione ai sensi del GDPR. Se lavori con dati di clienti, valgono comunque le policy della tua organizzazione e la normativa (GDPR, e nel settore finanziario anche DORA).
- **I nomi delle colonne vanno a Claude così come sono.** Se un nome è rivelatore, rinominalo nel file vero prima di generare.
- **Non incollare nella chat con Claude righe o numeri presi dai dati veri.** Nessuna regola tecnica può impedirlo: dipende da te.
- **Il gemello serve a scrivere codice, non a trarre conclusioni.** Le relazioni tra colonne finte e colonne sintetiche non sono conservate e i numeri del gemello non significano nulla.
- **Leggi il codice prima di lanciarlo sui dati veri.** L'app te lo mostra prima del pulsante. Lo scheletro blocca la rete, ma resta codice scritto da un modello.
- Ogni pacchetto contiene un ambiente Python di circa 115 MB.

Per la garanzia massima, il README di ogni pacchetto descrive anche il percorso alternativo: repo GitHub privato e Claude Code in cloud, dove Claude non ha alcun accesso al tuo computer.

## Test

```bash
.venv/bin/python -m pytest -q
```

## Licenze

Codice di questo repository: licenza MIT (vedi [LICENSE](LICENSE)).

Le librerie si installano da PyPI con le loro licenze. In particolare SDV è distribuito con [Business Source License](https://github.com/sdv-dev/SDV/blob/main/LICENSE): l'uso è libero, ma non puoi offrirlo come servizio commerciale di generazione di dati sintetici.

Lo strumento è fornito così com'è, senza garanzie. Non è consulenza legale né di conformità.

---

Creato da Andrea Brugnoli · [abcomunica](https://www.andreabrugnoli.it)

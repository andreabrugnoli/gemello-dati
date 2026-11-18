"""Interfaccia locale di anonym-data (Streamlit, solo localhost).

Avvio: ./avvia.sh  oppure  .venv/bin/streamlit run app.py
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from anonym import offline

offline.attiva()  # prima di qualsiasi altra importazione pesante

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from anonym import detect, generate, io, leakcheck, package, runner  # noqa: E402
from anonym.detect import AZIONI, ETICHETTE, TIPI, ProfiloColonna  # noqa: E402

RADICE = Path(__file__).resolve().parent
DEMO = RADICE / "demo" / "rapporti_banca_demo.csv"

st.set_page_config(page_title="Gemello dati", page_icon="🔒", layout="wide")


# ---------------------------------------------------------------------------
# stato
# ---------------------------------------------------------------------------

def reset_risultati() -> None:
    for k in ("gemello", "problemi", "violazioni", "esportato"):
        st.session_state.pop(k, None)


def carica(dati: bytes, nome_file: str, foglio: str | None) -> None:
    """Legge il file e prepara i profili; si ripete solo se cambia il file o il foglio."""
    chiave = hashlib.sha256(dati).hexdigest() + str(foglio)
    if st.session_state.get("chiave_file") == chiave:
        return
    grezzo, formato = io.leggi(dati, nome_file, foglio)
    profili = detect.profila(grezzo, formato)
    st.session_state.update(chiave_file=chiave, grezzo=grezzo, formato=formato, profili=profili)
    tipizzato = detect.converti(grezzo, profili, formato)
    st.session_state["vincoli"] = generate.riduci_vincoli(detect.suggerisci_vincoli(tipizzato, profili))
    reset_risultati()


def profili_da_editor(tabella: pd.DataFrame, originali: list[ProfiloColonna]) -> list[ProfiloColonna]:
    """Applica tipo e azione scelti nella tabella."""
    nuovi = []
    for p, (_, r) in zip(originali, tabella.iterrows()):
        q = ProfiloColonna(**p.to_dict())
        q.tipo, q.azione = r["tipo"], r["azione"]
        if q.tipo == "data" and not q.formato_data:
            q.formato_data = detect.rileva_formato_data(st.session_state["grezzo"][q.nome])
        nuovi.append(q)
    return nuovi


# ---------------------------------------------------------------------------
# barra laterale
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🔒 Gemello dati")
    if offline.attivo():
        st.success("Rete esterna bloccata in questo processo.")
    else:
        st.error("Blocco di rete non attivo.")
    bloccati = offline.tentativi_bloccati()
    if bloccati:
        st.warning(f"Tentativi di connessione bloccati: {', '.join(sorted(set(bloccati)))}")
    st.caption("I dati restano in memoria su questo Mac. Su disco finisce solo il pacchetto sintetico, "
               f"in `{package.DESTINAZIONE}`.")
    st.divider()
    modalita = st.radio("Cosa vuoi fare", ["Crea il gemello", "Genera la dashboard"], key="modalita",
                        captions=["passi 1-5, prima di Claude", "passo 6, dopo Claude"])
    st.divider()
    st.markdown("**Passi**\n1. Carica il file\n2. Decidi cosa fare di ogni colonna\n3. Genera il gemello\n"
                "4. Controlla il report anti-fuga\n5. Esporta il pacchetto\n\n*Claude lavora sul pacchetto*\n\n"
                "6. Genera la dashboard sui dati veri")


# ---------------------------------------------------------------------------
# 6. dashboard sui dati veri (pagina separata)
# ---------------------------------------------------------------------------

def pagina_dashboard() -> None:
    """Sceglie un pacchetto, prende il file vero e lancia la dashboard scritta da Claude."""
    st.title("6. Dashboard sui dati veri")
    st.caption("Il file vero passa da una cartella temporanea di sistema, fuori dal pacchetto, e viene cancellato "
               "appena la dashboard e' pronta. L'HTML va sulla Scrivania.")

    pacchetti = runner.elenca_pacchetti()
    if not pacchetti:
        st.info(f"Nessun pacchetto in `{package.DESTINAZIONE}`. Crea prima il gemello ed esportalo.")
        return
    scelto = st.selectbox("Pacchetto", pacchetti, format_func=lambda p: p.etichetta)
    if not scelto.completato:
        st.warning("La dashboard di questo pacchetto e' ancora lo scheletro: apri Claude Code sulla cartella "
                   "e scrivi *Leggi CLAUDE.md e iniziamo*.")
    spec = scelto.cartella / "DASHBOARD_SPEC.md"
    if spec.exists():
        with st.expander("Cosa deve mostrare (DASHBOARD_SPEC.md)"):
            st.markdown(spec.read_text(encoding="utf-8"))
    with st.expander("Leggi il codice di dashboard.py prima di lanciarlo"):
        st.code((scelto.cartella / "dashboard.py").read_text(encoding="utf-8"), language="python")

    st.subheader("File vero")
    opzioni = ["Carica un file"]
    if "sorgente" in st.session_state:
        opzioni.insert(0, f"Usa quello del passo 1 ({st.session_state['sorgente'][1]})")
    origine = st.radio("Origine", opzioni, horizontal=True, label_visibility="collapsed")
    dati, nome_file = None, None
    if origine.startswith("Usa"):
        dati, nome_file = st.session_state["sorgente"]
    else:
        vero = st.file_uploader("CSV o Excel con i dati veri", type=["csv", "txt", "xlsx", "xlsm", "xls"],
                                key="file_vero")
        if vero is not None:
            dati, nome_file = vero.getvalue(), vero.name

    destinazione = runner.percorso_html(scelto)
    st.caption(f"L'HTML sara' salvato in `{destinazione}` (sovrascrive la versione precedente).")
    if st.button("Genera la dashboard", type="primary", disabled=dati is None):
        try:
            with st.spinner("Eseguo dashboard.py sul file vero, in locale..."):
                html, messaggi = runner.esegui(scelto, dati, nome_file)
            st.session_state["ultima_dashboard"] = html
            st.success(f"Dashboard pronta: `{html}`")
            if messaggi:
                with st.expander("Messaggi dello script"):
                    st.code(messaggi)
            subprocess.run(["open", str(html)], check=False)
        except Exception as e:
            st.error("La dashboard non si e' generata. Messaggio dello script:")
            st.code(str(e))
            st.caption("Se manca una colonna o il formato non torna, il file vero non corrisponde allo schema "
                       "del pacchetto. Se e' un errore del codice, incollalo a Claude: e' un messaggio tecnico, "
                       "ma controlla che non contenga valori veri prima di farlo.")
    if st.session_state.get("ultima_dashboard"):
        if st.button("Riapri l'ultima dashboard"):
            subprocess.run(["open", str(st.session_state["ultima_dashboard"])], check=False)


if modalita == "Genera la dashboard":
    pagina_dashboard()
    st.stop()


st.title("Gemello sintetico di una tabella")
st.caption("Crea una copia con dati inventati ma struttura identica, da dare a Claude per scrivere la dashboard.")

# ---------------------------------------------------------------------------
# 1. file
# ---------------------------------------------------------------------------

st.header("1. File")
c1, c2 = st.columns([3, 1])
with c1:
    caricato = st.file_uploader("CSV o Excel", type=["csv", "txt", "xlsx", "xlsm", "xls"])
with c2:
    st.write("")
    usa_demo = st.button("Usa il dataset demo", help="Rapporti bancari inventati, utili per provare o in aula.")
if usa_demo:
    if not DEMO.exists():
        from demo.crea_demo import crea_demo

        crea_demo().to_csv(DEMO, sep=";", decimal=",", index=False, encoding="utf-8")
    st.session_state["sorgente"] = (DEMO.read_bytes(), DEMO.name)
if caricato is not None:
    st.session_state["sorgente"] = (caricato.getvalue(), caricato.name)

if "sorgente" not in st.session_state:
    st.info("Carica un file per iniziare.")
    st.stop()

dati, nome_file = st.session_state["sorgente"]
foglio = None
if Path(nome_file).suffix.lower() in (".xlsx", ".xlsm", ".xls"):
    fogli = io.fogli_excel(dati)
    foglio = st.selectbox("Foglio", fogli) if len(fogli) > 1 else fogli[0]

try:
    carica(dati, nome_file, foglio)
except Exception as e:  # il file dell'utente puo' essere qualsiasi cosa
    st.error(f"Non riesco a leggere il file: {e}")
    st.stop()

grezzo: pd.DataFrame = st.session_state["grezzo"]
formato: io.FormatoFile = st.session_state["formato"]
desc = f"separatore `{formato.sep}`, decimali `{formato.decimal}`" if formato.tipo == "csv" else f"foglio `{formato.foglio}`"
st.write(f"**{len(grezzo):,}".replace(",", ".") + f"** righe, **{grezzo.shape[1]}** colonne ({formato.tipo.upper()}, {desc}).")
nome_dataset = st.text_input("Nome del dataset nel pacchetto",
                             value=st.session_state.get("nome_dataset", "dataset"),
                             help="Finisce nel repo: non usare il nome del file se e' rivelatore.")
st.session_state["nome_dataset"] = nome_dataset

# ---------------------------------------------------------------------------
# 2. colonne
# ---------------------------------------------------------------------------

st.header("2. Colonne")
st.caption("**finto**: valori inventati, ricorrenze conservate · **sintetico**: generati da un modello "
           "statistico · **elimina**: non esce dal Mac. Gli esempi sensibili sono mascherati.")
profili: list[ProfiloColonna] = st.session_state["profili"]
tabella = pd.DataFrame([{
    "colonna": p.nome,
    "significato": ETICHETTE.get(p.significato or "", ""),
    "rischio": {"diretto": "🔴 diretto", "quasi": "🟠 quasi", "basso": "🟢 basso"}[p.rischio],
    "tipo": p.tipo,
    "azione": p.azione,
    "valori diversi": p.n_unici,
    "% vuoti": p.perc_vuoti,
    "esempio": p.esempio,
} for p in profili])
modificata = st.data_editor(
    tabella, hide_index=True, width="stretch", key="editor_colonne",
    disabled=["colonna", "significato", "rischio", "valori diversi", "% vuoti", "esempio"],
    column_config={
        "tipo": st.column_config.SelectboxColumn(options=TIPI, required=True),
        "azione": st.column_config.SelectboxColumn(options=AZIONI, required=True),
    },
)
profili_correnti = profili_da_editor(modificata, profili)

# ---------------------------------------------------------------------------
# 3. vincoli e generazione
# ---------------------------------------------------------------------------

st.header("3. Generazione")
candidati = [p.nome for p in profili_correnti if p.azione == "sintetico" and p.tipo in ("data", "numero", "intero")]
etichetta = {f"{a} ≤ {b}": (a, b) for a in candidati for b in candidati if a != b}
predefiniti = [f"{a} ≤ {b}" for a, b in st.session_state.get("vincoli", []) if f"{a} ≤ {b}" in etichetta]
scelti = st.multiselect("Regole di coerenza da rispettare", list(etichetta), default=predefiniti,
                        help="Proposte in automatico dalle coppie di date che nei dati veri sono quasi sempre in ordine.")
vincoli = [generate.Vincolo(*etichetta[s]) for s in scelti]

g1, g2, g3 = st.columns(3)
n_righe = g1.number_input("Righe da generare", min_value=10, max_value=200_000, value=len(grezzo), step=100)
fedelta = g2.radio("Fedeltà", ["alta", "veloce"], horizontal=True,
                   help="Alta: distribuzioni piu' simili alle vere, qualche secondo in piu'.")
seme = g3.number_input("Seme", min_value=0, value=42, help="Stesso seme, stesso gemello.")

if st.button("Genera il gemello", type="primary"):
    try:
        with st.spinner("Addestro il modello e genero i dati, tutto in locale..."):
            vero = detect.converti(grezzo, profili_correnti, formato)
            gemello = generate.genera(vero, profili_correnti, int(n_righe), vincoli, int(seme), fedelta)
            problemi = leakcheck.controlla(vero, gemello, profili_correnti)
            violazioni = generate.violazioni_vincoli(gemello, vincoli)
        st.session_state.update(gemello=gemello, problemi=problemi, violazioni=violazioni,
                                profili_usati=profili_correnti, vincoli_usati=vincoli, vero=vero)
        st.session_state.pop("esportato", None)
    except Exception as e:
        st.error(f"Generazione non riuscita: {e}")

if "gemello" not in st.session_state:
    st.stop()

gemello: pd.DataFrame = st.session_state["gemello"]
vero: pd.DataFrame = st.session_state["vero"]
profili_usati: list[ProfiloColonna] = st.session_state["profili_usati"]
problemi: list[leakcheck.Problema] = st.session_state["problemi"]

# ---------------------------------------------------------------------------
# 4. risultati
# ---------------------------------------------------------------------------

st.header("4. Confronto e controlli")
t_confronto, t_distr, t_fuga = st.tabs(["Vero e gemello", "Distribuzioni", "Anti-fuga"])

with t_confronto:
    sensibili = {p.nome for p in profili_usati if p.rischio != "basso"}
    anteprima_vera = vero[[c for c in gemello.columns]].head(12).copy()
    for c in sensibili & set(anteprima_vera.columns):
        anteprima_vera[c] = anteprima_vera[c].map(detect.maschera)
    a, b = st.columns(2)
    a.markdown("**Dati veri** (colonne sensibili mascherate)")
    a.dataframe(anteprima_vera, hide_index=True, width="stretch")
    b.markdown("**Gemello**")
    b.dataframe(gemello.head(12), hide_index=True, width="stretch")

with t_distr:
    confrontabili = [p.nome for p in profili_usati if p.azione == "sintetico"]
    if confrontabili:
        col = st.selectbox("Colonna", confrontabili)
        p = next(x for x in profili_usati if x.nome == col)
        fig = go.Figure()
        if p.tipo in ("numero", "intero", "data"):
            fig.add_histogram(x=vero[col], name="vero", opacity=0.6, histnorm="percent", nbinsx=40)
            fig.add_histogram(x=gemello[col], name="gemello", opacity=0.6, histnorm="percent", nbinsx=40)
            fig.update_layout(barmode="overlay")
        else:
            cv = vero[col].value_counts(normalize=True).head(15) * 100
            cg = gemello[col].value_counts(normalize=True).reindex(cv.index).fillna(0) * 100
            fig.add_bar(x=cv.index.astype(str), y=cv.values, name="vero")
            fig.add_bar(x=cg.index.astype(str), y=cg.values, name="gemello")
            fig.update_xaxes(type="category")  # codici numerici (CAP) restano etichette
        fig.update_layout(height=380, margin=dict(t=20, b=20), yaxis_title="% righe", legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Le colonne finte non si confrontano: sono inventate per costruzione.")

with t_fuga:
    for vincolo, n in st.session_state["violazioni"].items():
        (st.success if n == 0 else st.warning)(f"Regola `{vincolo}`: {n} righe non conformi.")
    if not problemi:
        st.success("Nessun problema rilevato.")
    for pb in problemi:
        dove = f" · `{pb.colonna}`" if pb.colonna else ""
        (st.error if pb.livello == "bloccante" else st.warning)(f"**{pb.livello}**{dove}: {pb.messaggio}")
        if pb.dettaglio_locale:
            with st.expander("Vedi i valori (solo qui, non finiscono nel pacchetto)"):
                st.write(", ".join(pb.dettaglio_locale))

# ---------------------------------------------------------------------------
# 5. export
# ---------------------------------------------------------------------------

st.header("5. Esporta il pacchetto")
bloccato = leakcheck.ha_bloccanti(problemi)
if bloccato:
    st.error("Export disattivato: risolvi i problemi bloccanti (cambia l'azione delle colonne indicate e rigenera).")
conferma = st.checkbox("Ho guardato il gemello e il report: nessun valore vero, nessun nome di colonna rivelatore.",
                       disabled=bloccato)
if st.button("Esporta", disabled=bloccato or not conferma):
    try:
        with st.spinner("Scrivo il pacchetto e preparo il suo ambiente Python (la prima volta qualche secondo)..."):
            cartella = package.esporta(gemello, profili_usati, formato, problemi, st.session_state["violazioni"],
                                       nome_dataset)
        st.session_state["esportato"] = cartella
    except Exception as e:
        st.error(f"Export non riuscito: {e}")

if "esportato" in st.session_state:
    cartella: Path = st.session_state["esportato"]
    estensione = next((cartella / "data").glob("sintetico.*")).suffix
    st.success(f"Pacchetto pronto in `{cartella}`")
    if st.button("Mostra nel Finder"):
        subprocess.run(["open", str(cartella)], check=False)
    st.markdown(
        "**1. Apri Claude Code su questa cartella** (app desktop: nuova sessione e scegli la cartella; "
        "oppure da Terminale) e scrivi: *Leggi CLAUDE.md e iniziamo.*"
    )
    st.code(f'cd "{cartella}" && claude', language="bash")
    st.markdown("**2. Genera la dashboard sui dati veri** da questa app, passo 6.")
    st.caption("Quando Claude ha finito, torna qui e scegli **Genera la dashboard** nella barra laterale "
               "(oppure, da Terminale, nella cartella del pacchetto):")
    st.code(f'.venv/bin/python dashboard.py "/percorso/del/file_vero{estensione}"', language="bash")
    st.caption("In quella cartella Claude non può leggere file esterni né usare la rete; "
               "le altre sessioni di Claude Code non cambiano.")

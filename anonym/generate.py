"""Generazione del gemello sintetico.

- colonne "sintetico": modello statistico SDV (GaussianCopula) addestrato in locale;
- colonne "finto": valori inventati con Faker it_IT, uno per ogni valore vero distinto,
  assegnati alle righe in modo da conservare le ricorrenze (un cliente con tre rapporti
  diventa un cliente finto con tre rapporti);
- colonne "elimina": tolte.

La tabella di corrispondenza vero -> finto vive solo in memoria e non viene mai salvata.
"""

from __future__ import annotations

import logging
import random
import string
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from faker import Faker

from .detect import ProfiloColonna

logging.getLogger("sdv").setLevel(logging.ERROR)
logging.getLogger("rdt").setLevel(logging.ERROR)
logging.getLogger("copulas").setLevel(logging.ERROR)


@dataclass
class Vincolo:
    """La colonna `bassa` deve essere minore o uguale alla colonna `alta`."""

    bassa: str
    alta: str


def riduci_vincoli(coppie: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Toglie i vincoli gia' implicati da una catena (A<=B e B<=C rendono superfluo A<=C)."""
    insieme = set(coppie)
    return [(a, c) for a, c in coppie if not any((a, b) in insieme and (b, c) in insieme for b in {x for _, x in coppie})]


# ---------------------------------------------------------------------------
# valori finti
# ---------------------------------------------------------------------------

def _stessa_forma(valore: str, rng: random.Random) -> str:
    """Valore inventato con la stessa forma: lettere al posto di lettere, cifre al posto di cifre."""
    out = []
    for c in valore:
        if c.isdigit():
            out.append(rng.choice(string.digits))
        elif c.isalpha():
            out.append(rng.choice(string.ascii_uppercase if c.isupper() else string.ascii_lowercase))
        else:
            out.append(c)
    return "".join(out)


def _generatore(significato: str | None, fake: Faker, rng: random.Random):  # type: ignore[no-untyped-def]
    """Funzione che, dato il valore vero, restituisce un valore finto plausibile."""
    tabella = {
        "email": lambda v: fake.free_email(),
        "codice_fiscale": lambda v: fake.ssn(),
        "iban": lambda v: fake.iban(),
        "carta": lambda v: fake.credit_card_number(),
        "partita_iva": lambda v: "".join(rng.choice(string.digits) for _ in range(11)),
        "telefono": lambda v: fake.phone_number(),
        "nome": lambda v: fake.first_name(),
        "cognome": lambda v: fake.last_name(),
        "nome_completo": lambda v: f"{fake.first_name()} {fake.last_name()}",
        "ragione_sociale": lambda v: fake.company(),
        "indirizzo": lambda v: fake.street_address(),
    }
    return tabella.get(significato or "", lambda v: _stessa_forma(v, rng))


def _mappa_finta(valori_veri: pd.Series, significato: str | None, seed: int) -> dict[str, str]:
    """Associa a ogni valore vero distinto un valore finto, mai uguale a un valore vero."""
    fake = Faker("it_IT")
    fake.seed_instance(seed)
    rng = random.Random(seed)
    gen = _generatore(significato, fake, rng)
    distinti = valori_veri.dropna().astype(str).unique()
    veri = set(distinti)
    usati: set[str] = set()
    mappa: dict[str, str] = {}
    unico = significato not in {"nome", "cognome"}  # nomi e cognomi si ripetono anche nella realta'
    for v in distinti:
        for tentativo in range(50):
            f = str(gen(v))
            if tentativo > 20 and unico:
                f = f"{f}{rng.randint(10, 99)}" if significato != "email" else f"{rng.randint(10, 99)}{f}"
            # nomi e cognomi presi da soli non identificano nessuno: possono coincidere con
            # altri nomi veri, purche' non con quello che sostituiscono
            if (f in veri and unico) or f == v or (unico and f in usati):
                continue
            break
        else:
            raise RuntimeError(f"Impossibile generare valori finti distinti per la colonna ({significato}).")
        mappa[v] = f
        usati.add(f)
    return mappa


def _indici_righe(n_veri: int, n_righe: int, seed: int) -> np.ndarray:
    """Righe vere da cui prendere la "struttura" delle colonne finte, senza ripetizioni finche' possibile."""
    rng = np.random.default_rng(seed)
    if n_righe <= n_veri:
        return rng.permutation(n_veri)[:n_righe]
    extra = rng.integers(0, n_veri, n_righe - n_veri)
    return np.concatenate([rng.permutation(n_veri), extra])


# ---------------------------------------------------------------------------
# sintesi statistica
# ---------------------------------------------------------------------------

def _metadata(df: pd.DataFrame, profili: list[ProfiloColonna]):  # type: ignore[no-untyped-def]
    """Metadata SDV costruiti dai profili (non dall'autodetect, che sbaglia sulle colonne italiane)."""
    from sdv.metadata import Metadata

    colonne = {}
    for p in profili:
        if p.tipo == "data":
            colonne[p.nome] = {"sdtype": "datetime", "datetime_format": "%Y-%m-%d %H:%M:%S"}
        elif p.tipo in ("numero", "intero"):
            colonne[p.nome] = {"sdtype": "numerical"}
        else:
            colonne[p.nome] = {"sdtype": "categorical"}
    return Metadata.load_from_dict({
        "METADATA_SPEC_VERSION": "V1",
        "tables": {"tabella": {"columns": colonne}},
    })


DISTRIBUZIONI = {"alta": "gaussian_kde", "veloce": "beta"}


def _sintetizza(df: pd.DataFrame, profili: list[ProfiloColonna], n_righe: int, vincoli: list[Vincolo], seed: int,
                fedelta: str = "alta") -> pd.DataFrame:
    """Addestra GaussianCopula sulle sole colonne sintetiche e campiona n_righe.

    fedelta="alta" usa stime a nucleo (KDE): distribuzioni piu' fedeli, circa 10-20 volte piu' lenta.
    """
    from sdv.cag import Inequality
    from sdv.single_table import GaussianCopulaSynthesizer

    dati = df[[p.nome for p in profili]].copy()
    for p in profili:
        if p.tipo == "data":
            # formato uniforme per SDV; si riconverte dopo
            dati[p.nome] = dati[p.nome].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif p.tipo == "intero":
            dati[p.nome] = dati[p.nome].astype("float")
        elif p.tipo in ("categoria", "testo"):
            dati[p.nome] = dati[p.nome].astype(object).where(dati[p.nome].notna(), np.nan)

    np.random.seed(seed)
    random.seed(seed)
    synth = GaussianCopulaSynthesizer(_metadata(dati, profili), enforce_min_max_values=True, enforce_rounding=True,
                                      default_distribution=DISTRIBUZIONI.get(fedelta, "beta"))
    nomi = {p.nome for p in profili}
    validi = [v for v in vincoli if v.bassa in nomi and v.alta in nomi]
    if validi:
        synth.add_constraints([Inequality(low_column_name=v.bassa, high_column_name=v.alta) for v in validi])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        synth.fit({"tabella": dati})
        campione = synth.sample(num_rows=n_righe)
    if isinstance(campione, dict):
        campione = campione["tabella"]

    for p in profili:
        if p.tipo == "data":
            campione[p.nome] = pd.to_datetime(campione[p.nome], errors="coerce")
            if not p.formato_data or "%H" not in p.formato_data:
                # le date vere sono senza ora: si tronca al giorno
                campione[p.nome] = campione[p.nome].dt.floor("D")
        elif p.tipo == "intero":
            campione[p.nome] = pd.to_numeric(campione[p.nome]).round().astype("Int64")
        elif p.tipo == "numero":
            campione[p.nome] = pd.to_numeric(campione[p.nome]).astype(float)
        else:
            campione[p.nome] = campione[p.nome].astype("string")
    return campione.reset_index(drop=True)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def genera(df: pd.DataFrame, profili: list[ProfiloColonna], n_righe: int | None = None,
           vincoli: list[Vincolo] | None = None, seed: int = 42, fedelta: str = "alta") -> pd.DataFrame:
    """Costruisce il gemello a partire dal DataFrame vero gia' tipizzato."""
    n_righe = n_righe or len(df)
    vincoli = vincoli or []
    sintetiche = [p for p in profili if p.azione == "sintetico"]
    finte = [p for p in profili if p.azione == "finto"]

    parti: dict[str, pd.Series] = {}
    if sintetiche:
        campione = _sintetizza(df, sintetiche, n_righe, vincoli, seed, fedelta)
        for p in sintetiche:
            parti[p.nome] = campione[p.nome]

    if finte:
        indici = _indici_righe(len(df), n_righe, seed)
        for i, p in enumerate(finte):
            mappa = _mappa_finta(df[p.nome], p.significato, seed + i + 1)
            sorgente = df[p.nome].astype("string").iloc[indici].reset_index(drop=True)
            parti[p.nome] = sorgente.map(lambda v: mappa.get(v, pd.NA) if pd.notna(v) else pd.NA).astype("string")
            del mappa

    ordine = [p.nome for p in profili if p.azione != "elimina"]
    return pd.DataFrame({c: parti[c] for c in ordine})


def violazioni_vincoli(df: pd.DataFrame, vincoli: list[Vincolo]) -> dict[str, int]:
    """Numero di righe che non rispettano ciascun vincolo."""
    esito = {}
    for v in vincoli:
        if v.bassa in df.columns and v.alta in df.columns:
            entrambi = df[[v.bassa, v.alta]].dropna()
            esito[f"{v.bassa} ≤ {v.alta}"] = int((entrambi[v.bassa] > entrambi[v.alta]).sum())
    return esito


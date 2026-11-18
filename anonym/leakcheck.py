"""Controllo anti-fuga: cerca nel gemello tracce dei dati veri prima dell'export.

Il report che finisce nel pacchetto contiene solo conteggi, mai valori veri.
I valori trovati restano disponibili in `dettaglio_locale`, da mostrare solo a schermo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .detect import ProfiloColonna

SOGLIA_RARO = 5          # una categoria vista meno di 5 volte nei dati veri e' "rara"
SOGLIA_RIGHE_MINIME = 200
NOMI_SINGOLI = {"nome", "cognome"}


@dataclass
class Problema:
    livello: str          # "bloccante" oppure "avviso"
    colonna: str | None
    messaggio: str
    dettaglio_locale: list[str] = field(default_factory=list)

    def per_report(self) -> dict:
        return {"livello": self.livello, "colonna": self.colonna, "messaggio": self.messaggio}


def _chiave(s: pd.Series) -> pd.Series:
    """Rappresentazione testuale uniforme per confrontare vero e sintetico."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.strftime("%Y-%m-%d %H:%M:%S").astype("string")
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s).round(2).astype("string")
    return s.astype("string").str.strip().str.lower()


def controlla(vero: pd.DataFrame, gemello: pd.DataFrame, profili: list[ProfiloColonna]) -> list[Problema]:
    """Restituisce l'elenco dei problemi trovati, dal piu' grave."""
    problemi: list[Problema] = []
    attivi = [p for p in profili if p.azione != "elimina" and p.nome in gemello.columns]

    if len(vero) < SOGLIA_RIGHE_MINIME:
        problemi.append(Problema("avviso", None,
            f"Il file ha solo {len(vero)} righe: con pochi dati il modello tende a imitare i singoli record. "
            "Controlla a mano il gemello prima di usarlo."))

    for p in attivi:
        v, g = _chiave(vero[p.nome]).dropna(), _chiave(gemello[p.nome]).dropna()
        comuni = sorted(set(v) & set(g))

        if p.azione == "finto":
            if p.significato in NOMI_SINGOLI:
                continue  # un nome o un cognome da solo puo' coincidere: si controlla la coppia piu' sotto
            if comuni:
                problemi.append(Problema("bloccante", p.nome,
                    f"{len(comuni)} valori finti coincidono con valori veri.", comuni[:20]))
            continue

        if p.tipo not in ("categoria", "testo"):
            continue

        if p.rischio == "diretto" and comuni:
            problemi.append(Problema("bloccante", p.nome,
                f"Colonna identificativa sintetizzata: {len(comuni)} valori veri ricopiati. Usa 'finto' o 'elimina'.",
                comuni[:20]))
            continue

        n_unici = v.nunique()
        if n_unici > 50 and n_unici / max(len(v), 1) > 0.3 and comuni:
            problemi.append(Problema("bloccante", p.nome,
                f"Testo con molti valori diversi ({n_unici}): la sintesi ne ricopia {len(comuni)} tali e quali. "
                "Usa 'finto' o 'elimina'.", comuni[:20]))
            continue

        conteggi = v.value_counts()
        rari = sorted(set(conteggi[conteggi < SOGLIA_RARO].index) & set(g))
        if rari:
            problemi.append(Problema("avviso", p.nome,
                f"{len(rari)} categorie rare (meno di {SOGLIA_RARO} casi nei dati veri) compaiono nel gemello: "
                "possono rendere riconoscibile qualcuno. Valuta di raggrupparle in 'Altro' nel file di partenza.",
                rari[:20]))

    nomi = [p.nome for p in attivi if p.azione == "finto" and p.significato in NOMI_SINGOLI]
    if len(nomi) >= 2:
        cv = pd.DataFrame({c: _chiave(vero[c]) for c in nomi}).fillna("∅").agg(" ".join, axis=1)
        cg = pd.DataFrame({c: _chiave(gemello[c]) for c in nomi}).fillna("∅").agg(" ".join, axis=1)
        coppie = sorted(set(cv) & set(cg))
        if coppie:
            problemi.append(Problema("avviso", ", ".join(nomi),
                f"{len(coppie)} combinazioni nome e cognome inventate coincidono per caso con persone vere. "
                "Rigenera con un altro seme se vuoi evitarlo.", coppie[:20]))

    sintetiche = [p.nome for p in attivi if p.azione == "sintetico"]
    if sintetiche:
        kv = pd.DataFrame({c: _chiave(vero[c]) for c in sintetiche}).fillna("∅").agg("|".join, axis=1)
        kg = pd.DataFrame({c: _chiave(gemello[c]) for c in sintetiche}).fillna("∅").agg("|".join, axis=1)
        copiate = int(kg.isin(set(kv)).sum())
        if copiate:
            livello = "bloccante" if len(sintetiche) > 3 else "avviso"
            problemi.append(Problema(livello, None,
                f"{copiate} righe del gemello sono identiche a righe vere su tutte le colonne sintetiche."))

    quasi = [p.nome for p in attivi if p.azione == "sintetico" and p.rischio == "quasi"]
    if len(quasi) >= 2:
        qv = pd.DataFrame({c: _chiave(vero[c]) for c in quasi}).fillna("∅").agg("|".join, axis=1)
        unici = set(qv.value_counts()[lambda s: s == 1].index)
        qg = pd.DataFrame({c: _chiave(gemello[c]) for c in quasi}).fillna("∅").agg("|".join, axis=1)
        n = int(qg.isin(unici).sum())
        if n:
            problemi.append(Problema("avviso", ", ".join(quasi),
                f"{n} righe del gemello hanno la stessa combinazione di {', '.join(quasi)} di una persona vera "
                "che e' l'unica con quella combinazione. Se la combinazione e' troppo specifica, generalizza "
                "(per esempio anno di nascita invece della data)."))

    return sorted(problemi, key=lambda x: x.livello != "bloccante")


def ha_bloccanti(problemi: list[Problema]) -> bool:
    return any(p.livello == "bloccante" for p in problemi)

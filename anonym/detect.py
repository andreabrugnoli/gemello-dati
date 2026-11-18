"""Profilazione delle colonne: tipo, significato, rischio e azione proposta."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pandas as pd

from .io import FormatoFile, testo_in_numero

TIPI = ["numero", "intero", "data", "categoria", "testo"]
AZIONI = ["sintetico", "finto", "elimina"]

FORMATI_DATA = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S",
]

# significato -> rischio
RISCHIO = {
    "email": "diretto", "codice_fiscale": "diretto", "iban": "diretto", "carta": "diretto",
    "partita_iva": "diretto", "telefono": "diretto", "nome": "diretto", "cognome": "diretto",
    "nome_completo": "diretto", "ragione_sociale": "diretto", "indirizzo": "diretto",
    "identificativo": "diretto", "testo_libero": "diretto",
    "cap": "quasi", "comune": "quasi", "provincia": "quasi", "data_nascita": "quasi", "sesso": "quasi",
}

ETICHETTE = {
    "email": "email", "codice_fiscale": "codice fiscale", "iban": "IBAN", "carta": "carta di pagamento",
    "partita_iva": "partita IVA", "telefono": "telefono", "nome": "nome", "cognome": "cognome",
    "nome_completo": "nome e cognome", "ragione_sociale": "ragione sociale", "indirizzo": "indirizzo",
    "identificativo": "identificativo", "testo_libero": "testo libero", "cap": "CAP", "comune": "comune",
    "provincia": "provincia", "data_nascita": "data di nascita", "sesso": "sesso",
}

# parole nel nome della colonna -> significato (si confrontano i "pezzi" del nome)
PAROLE_NOME = [
    ({"email", "mail", "pec"}, "email"),
    ({"cf", "codicefiscale", "codice_fiscale", "fiscale"}, "codice_fiscale"),
    ({"iban"}, "iban"),
    ({"carta", "pan", "card", "cc"}, "carta"),
    ({"piva", "partitaiva", "partita_iva", "iva", "vat"}, "partita_iva"),
    ({"tel", "telefono", "cell", "cellulare", "phone", "mobile", "fax"}, "telefono"),
    ({"cognome", "surname", "lastname"}, "cognome"),
    ({"nominativo", "intestatario", "fullname"}, "nome_completo"),
    ({"ragionesociale", "ragione_sociale", "denominazione", "azienda", "company"}, "ragione_sociale"),
    ({"indirizzo", "via", "address", "residenza", "domicilio"}, "indirizzo"),
    ({"cap", "zip", "postcode", "postal"}, "cap"),
    ({"comune", "citta", "città", "city", "localita", "località"}, "comune"),
    ({"provincia", "prov"}, "provincia"),
    ({"nascita", "birth", "dob", "nato"}, "data_nascita"),
    ({"sesso", "genere", "gender", "sex"}, "sesso"),
    ({"note", "nota", "descrizione", "commento", "commenti", "messaggio", "testo", "motivazione"}, "testo_libero"),
    ({"id", "ndg", "codice", "matricola", "pratica", "cod", "uuid", "badge", "tessera"}, "identificativo"),
    ({"nome", "name", "firstname"}, "nome"),
]

RE_EMAIL = re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+$")
RE_CF = re.compile(r"^[A-Z]{6}\d{2}[A-EHLMPRST]\d{2}[A-Z]\d{3}[A-Z]$", re.I)
RE_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
RE_PERSONA = re.compile(r"^[A-ZÀ-Ý][a-zà-ÿ']+( [A-ZÀ-Ý][a-zà-ÿ']+){1,3}$")
RE_SOCIETA = re.compile(r"\b(s\.?r\.?l|s\.?p\.?a|s\.?n\.?c|s\.?a\.?s|s\.?c\.?a\.?r\.?l|soc\.?\s*coop)\b\.?", re.I)
RE_TELEFONO = re.compile(r"^\+?[\d\s./-]{8,16}$")


@dataclass
class ProfiloColonna:
    """Descrizione di una colonna, senza valori veri (tranne l'esempio mascherato)."""

    nome: str
    tipo: str
    significato: str | None
    rischio: str
    azione: str
    formato_data: str | None
    n_unici: int
    perc_vuoti: float
    esempio: str

    def to_dict(self) -> dict:
        return asdict(self)


def _pezzi(nome: str) -> set[str]:
    """Spezza il nome della colonna in parole minuscole."""
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", nome)
    pezzi = [p for p in re.split(r"[^0-9a-zA-Zàèéìòù]+", s.lower()) if p]
    return set(pezzi) | {"".join(pezzi), "_".join(pezzi)}


def _luhn(numero: str) -> bool:
    """Controllo di Luhn per i numeri di carta."""
    cifre = [int(c) for c in numero][::-1]
    totale = sum(cifre[0::2]) + sum(sum(divmod(2 * c, 10)) for c in cifre[1::2])
    return totale % 10 == 0


def _quota(valori: pd.Series, test) -> float:  # type: ignore[no-untyped-def]
    """Frazione di valori che superano il test."""
    if len(valori) == 0:
        return 0.0
    return float(valori.map(lambda v: bool(test(v))).mean())


def maschera(v: object) -> str:
    """Mostra solo l'inizio di un valore, per l'anteprima a schermo."""
    s = "" if v is None or pd.isna(v) else str(v)
    if len(s) <= 2:
        return "•" * len(s)
    return s[:2] + "•" * min(len(s) - 2, 8)


def rileva_formato_data(valori: pd.Series) -> str | None:
    """Trova il formato data che interpreta almeno il 95% dei valori."""
    campione = valori.dropna().astype(str).head(500)
    if campione.empty or not campione.str.contains(r"\d", regex=True).all():
        return None
    for fmt in FORMATI_DATA:
        ok = pd.to_datetime(campione, format=fmt, errors="coerce").notna().mean()
        if ok >= 0.95:
            return fmt
    return None


def _significato_da_valori(campione: pd.Series) -> str | None:
    """Riconosce il significato guardando il contenuto."""
    if _quota(campione, RE_EMAIL.match) >= 0.8:
        return "email"
    if _quota(campione, RE_CF.match) >= 0.8:
        return "codice_fiscale"
    compatti = campione.str.replace(r"[\s-]", "", regex=True).str.upper()
    if _quota(compatti, RE_IBAN.match) >= 0.8:
        return "iban"
    if _quota(compatti, lambda v: v.isdigit() and 13 <= len(v) <= 19 and _luhn(v)) >= 0.8:
        return "carta"
    if _quota(campione, RE_SOCIETA.search) >= 0.5:
        return "ragione_sociale"
    if _quota(campione, RE_PERSONA.match) >= 0.8 and campione.nunique() >= 15:
        return "nome_completo"
    return None


def _sembra_testo_libero(campione: pd.Series) -> bool:
    """Frasi lunghe con molti spazi: note, commenti, descrizioni."""
    return campione.str.len().mean() > 25 and _quota(campione, lambda v: v.count(" ") >= 3) >= 0.6


def _significato(nome: str, valori: pd.Series, n_righe: int) -> str | None:
    """Combina indizi dal nome della colonna e dai valori."""
    campione = valori.dropna().astype(str).head(500)
    da_valori = _significato_da_valori(campione) if not campione.empty else None
    if da_valori:
        return da_valori
    pezzi = _pezzi(nome)
    for parole, sig in PAROLE_NOME:
        if pezzi & parole:
            if sig == "telefono" and not campione.empty and _quota(campione, RE_TELEFONO.match) < 0.6:
                continue
            if sig == "identificativo":
                # e' un identificativo solo se distingue quasi ogni riga o ogni soggetto
                rapporto = valori.nunique() / max(valori.notna().sum(), 1)
                if rapporto < 0.3 and valori.nunique() < 50:
                    continue
            return sig
    if not campione.empty and _sembra_testo_libero(campione):
        return "testo_libero"
    return None


def _tipo(valori: pd.Series, formato: FormatoFile, significato: str | None) -> tuple[str, str | None]:
    """Tipo della colonna e, per le date, il formato."""
    non_vuoti = valori.dropna()
    if non_vuoti.empty:
        return "categoria", None
    if significato in {"email", "codice_fiscale", "iban", "carta", "partita_iva", "telefono", "nome", "cognome",
                       "nome_completo", "ragione_sociale", "indirizzo", "cap", "identificativo"}:
        return "testo", None
    if significato == "testo_libero":
        return "testo", None
    fmt = rileva_formato_data(non_vuoti)
    if fmt:
        return "data", fmt
    testo = non_vuoti.astype(str)
    zeri_iniziali = testo.str.match(r"^0\d").mean() > 0.05
    numeri = testo_in_numero(testo, formato.decimal)
    if numeri.notna().mean() >= 0.98 and not zeri_iniziali:
        interi = numeri.dropna()
        return ("intero" if (interi == interi.round()).all() else "numero"), None
    n_unici = testo.nunique()
    if n_unici <= max(30, int(0.05 * len(testo))):
        return "categoria", None
    return "testo", None


def _azione(significato: str | None, rischio: str, tipo: str, n_unici: int, n_righe: int) -> str:
    """Azione proposta per la colonna."""
    if significato == "testo_libero":
        return "elimina"
    if rischio == "diretto":
        return "finto"
    if tipo == "testo" and n_unici > 50 and n_unici / max(n_righe, 1) > 0.3:
        # testo ad alta cardinalita' senza significato noto: la sintesi ricopierebbe i valori
        return "finto"
    return "sintetico"


def profila(df: pd.DataFrame, formato: FormatoFile) -> list[ProfiloColonna]:
    """Profila tutte le colonne del DataFrame letto come testo."""
    profili = []
    n = len(df)
    for col in df.columns:
        valori = df[col]
        significato = _significato(col, valori, n)
        tipo, fmt = _tipo(valori, formato, significato)
        if significato == "data_nascita" and tipo != "data":
            significato = None
        rischio = RISCHIO.get(significato or "", "basso")
        n_unici = int(valori.nunique())
        primo = valori.dropna().iloc[0] if valori.notna().any() else ""
        profili.append(ProfiloColonna(
            nome=col, tipo=tipo, significato=significato, rischio=rischio,
            azione=_azione(significato, rischio, tipo, n_unici, n),
            formato_data=fmt, n_unici=n_unici, perc_vuoti=round(float(valori.isna().mean()) * 100, 1),
            esempio=maschera(primo) if rischio != "basso" else str(primo)[:30],
        ))
    return profili


def converti(df: pd.DataFrame, profili: list[ProfiloColonna], formato: FormatoFile) -> pd.DataFrame:
    """Applica i tipi dei profili al DataFrame letto come testo."""
    out = pd.DataFrame(index=df.index)
    for p in profili:
        s = df[p.nome]
        if p.tipo == "data":
            fmt = p.formato_data or rileva_formato_data(s)
            out[p.nome] = pd.to_datetime(s, format=fmt, errors="coerce") if fmt else pd.to_datetime(s, errors="coerce")
        elif p.tipo in ("numero", "intero"):
            num = testo_in_numero(s, formato.decimal)
            out[p.nome] = num.round().astype("Int64") if p.tipo == "intero" else num.astype(float)
        else:
            out[p.nome] = s.astype("string")
    return out


def suggerisci_vincoli(df_tipizzato: pd.DataFrame, profili: list[ProfiloColonna]) -> list[tuple[str, str]]:
    """Coppie di date (o numeri) per cui nei dati veri vale quasi sempre A <= B."""
    candidati = [p.nome for p in profili if p.tipo == "data" and p.azione == "sintetico"]
    coppie = []
    for a in candidati:
        for b in candidati:
            if a == b:
                continue
            entrambi = df_tipizzato[[a, b]].dropna()
            if len(entrambi) >= 10 and (entrambi[a] <= entrambi[b]).mean() >= 0.98:
                coppie.append((a, b))
    return coppie

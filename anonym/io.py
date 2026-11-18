"""Lettura e scrittura dei file, conservando il formato originale (separatore, decimali, date).

Il gemello viene scritto nello stesso formato del file vero: cosi' la dashboard scritta
sul sintetico legge il file vero esattamente nello stesso modo.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


@dataclass
class FormatoFile:
    """Come e' fatto il file di origine."""

    tipo: str  # "csv" oppure "xlsx"
    sep: str = ","
    decimal: str = "."
    encoding: str = "utf-8"
    foglio: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def fogli_excel(sorgente: bytes) -> list[str]:
    """Elenco dei fogli di un file Excel."""
    return pd.ExcelFile(io.BytesIO(sorgente)).sheet_names


def _cella_in_testo(v: object) -> object:
    """Converte una cella Excel in testo uniforme, lasciando vuoti i vuoti."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return pd.NA
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d %H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return s if s else pd.NA


def _indovina_decimale(testo: str, sep: str) -> str:
    """Se il separatore e' ';' e compaiono numeri con la virgola, i decimali sono italiani."""
    if sep != ";":
        return "."
    campione = testo[:20000]
    import re

    con_virgola = len(re.findall(r"(?:^|;)-?\d+,\d+(?:;|$)", campione, flags=re.M))
    con_punto = len(re.findall(r"(?:^|;)-?\d+\.\d+(?:;|$)", campione, flags=re.M))
    return "," if con_virgola >= con_punto else "."


def leggi(sorgente: bytes | Path | BinaryIO, nome_file: str, foglio: str | None = None) -> tuple[pd.DataFrame, FormatoFile]:
    """Legge CSV o Excel e restituisce tutte le celle come testo, piu' il formato rilevato."""
    if isinstance(sorgente, Path):
        dati = sorgente.read_bytes()
    elif isinstance(sorgente, bytes):
        dati = sorgente
    else:
        dati = sorgente.read()

    estensione = Path(nome_file).suffix.lower()
    if estensione in (".xlsx", ".xlsm", ".xls"):
        fogli = fogli_excel(dati)
        foglio = foglio or fogli[0]
        df = pd.read_excel(io.BytesIO(dati), sheet_name=foglio, dtype=object)
        df = df.map(_cella_in_testo).astype("string")
        df.columns = [str(c).strip() for c in df.columns]
        return df, FormatoFile(tipo="xlsx", foglio=foglio)

    for enc in ENCODINGS:
        try:
            testo = dati.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Codifica del file non riconosciuta.")

    try:
        sep = csv.Sniffer().sniff(testo[:10000], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    decimal = _indovina_decimale(testo, sep)
    df = pd.read_csv(io.StringIO(testo), sep=sep, dtype="string", keep_default_na=False, na_values=[""])
    df = df.apply(lambda s: s.str.strip()).replace({"": pd.NA})
    df.columns = [str(c).strip() for c in df.columns]
    enc_out = "utf-8-sig" if enc == "utf-8-sig" else ("utf-8" if enc == "utf-8" else enc)
    return df, FormatoFile(tipo="csv", sep=sep, decimal=decimal, encoding=enc_out)


def testo_in_numero(s: pd.Series, decimal: str) -> pd.Series:
    """Converte testo in numero rispettando il separatore decimale del file."""
    t = s.astype("string").str.strip().str.replace(r"[€\s]", "", regex=True)
    if decimal == ",":
        t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def scrivi(df: pd.DataFrame, tipi: dict[str, str], formati_data: dict[str, str | None], formato: FormatoFile, percorso: Path) -> Path:
    """Scrive il DataFrame tipizzato nello stesso formato del file originale."""
    out = df.copy()
    if formato.tipo == "xlsx":
        percorso = percorso.with_suffix(".xlsx")
        out.to_excel(percorso, sheet_name=formato.foglio or "Foglio1", index=False)
        return percorso

    for col, tipo in tipi.items():
        if col not in out.columns:
            continue
        if tipo == "data":
            fmt = formati_data.get(col) or "%Y-%m-%d"
            out[col] = pd.to_datetime(out[col]).dt.strftime(fmt)
        elif tipo == "intero":
            out[col] = pd.to_numeric(out[col]).round().astype("Int64").astype("string")
        elif tipo == "numero" and formato.decimal == ",":
            out[col] = pd.to_numeric(out[col]).map(
                lambda x: "" if pd.isna(x) else np.format_float_positional(float(x), trim="-").replace(".", ",")
            )
    percorso = percorso.with_suffix(".csv")
    out.to_csv(percorso, sep=formato.sep, index=False, encoding=formato.encoding, na_rep="")
    return percorso

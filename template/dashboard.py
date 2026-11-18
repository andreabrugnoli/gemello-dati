"""Dashboard di __NOME__.

Uso:
    .venv/bin/python dashboard.py data/sintetico.__EXT__        -> anteprima.html qui
    .venv/bin/python dashboard.py /percorso/file_vero.__EXT__   -> HTML sulla Scrivania

Scritta su dati sintetici, pensata per girare in locale sui dati veri. Produce un unico
file HTML con Plotly incorporato: si apre con doppio clic, senza rete.

Le sezioni marcate NON MODIFICARE garantiscono lettura del file, blocco di rete e
scrittura dell'HTML (sui dati veri mai dentro questa cartella). Il lavoro di analisi
va in `build_sections()`.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import socket
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))


# --- NON MODIFICARE: blocco di rete ------------------------------------------------
# Questo script legge dati veri: qualsiasi tentativo di connessione verso l'esterno
# viene bloccato, comprese le librerie che provano a scaricare qualcosa.

def _block_network() -> None:
    def is_local(host: object) -> bool:
        if not isinstance(host, str):
            return False
        h = host.strip("[]").lower()
        if h in {"localhost", ""}:
            return True
        try:
            return ipaddress.ip_address(h).is_loopback
        except ValueError:
            return False

    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        if self.family != getattr(socket, "AF_UNIX", -1):
            host = address[0] if isinstance(address, tuple) else address
            if not is_local(host):
                raise OSError(f"Rete bloccata: tentativo di connessione verso {host}")
        return original_connect(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host is not None and not is_local(host if isinstance(host, str) else host.decode()):
            raise OSError(f"Rete bloccata: risoluzione di {host}")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]


_block_network()


# --- NON MODIFICARE: lettura e validazione -------------------------------------------

def to_number(s: pd.Series, decimal: str) -> pd.Series:
    """Testo -> numero, rispettando il separatore decimale del file originale."""
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = s.astype("string").str.strip().str.replace(r"[€\s]", "", regex=True)
    if decimal == ",":
        t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def load_data(path: Path) -> pd.DataFrame:
    """Legge il file (vero o sintetico) con le stesse regole e applica i tipi di schema.json."""
    fmt = SCHEMA["formato"]
    if fmt["tipo"] == "xlsx":
        df = pd.read_excel(path, sheet_name=fmt.get("foglio") or 0)
    else:
        df = pd.read_csv(path, sep=fmt["sep"], encoding=fmt["encoding"], dtype="string",
                         keep_default_na=False, na_values=[""])
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c["nome"] for c in SCHEMA["colonne"] if c["nome"] not in df.columns]
    if missing:
        sys.exit(f"Nel file mancano queste colonne attese: {', '.join(missing)}")

    out = pd.DataFrame(index=df.index)
    for col in SCHEMA["colonne"]:
        name, kind = col["nome"], col["tipo"]
        s = df[name]
        if kind == "data":
            out[name] = s if pd.api.types.is_datetime64_any_dtype(s) else pd.to_datetime(
                s, format=col.get("formato_data") or None, errors="coerce")
        elif kind == "numero":
            out[name] = to_number(s, fmt.get("decimal", "."))
        elif kind == "intero":
            out[name] = to_number(s, fmt.get("decimal", ".")).round().astype("Int64")
        else:
            out[name] = s.astype("string").str.strip().replace({"": pd.NA})
    return out


# --- ANALISI: qui lavora Claude ------------------------------------------------------

def build_sections(df: pd.DataFrame) -> list[tuple[str, str, go.Figure | None]]:
    """Restituisce le sezioni della dashboard: (titolo, testo esplicativo, figura o None).

    Il testo non deve contenere numeri scritti a mano: i valori si calcolano da `df`.
    """
    sections: list[tuple[str, str, go.Figure | None]] = []

    # Esempio minimo, da sostituire con le sezioni concordate nell'intervista
    fig = go.Figure(go.Indicator(mode="number", value=len(df), title={"text": "Righe nel file"}))
    sections.append(("Panoramica", "Numero di righe lette dal file.", fig))
    return sections


# --- NON MODIFICARE: scrittura HTML --------------------------------------------------

def is_synthetic(source: Path) -> bool:
    """Vero se il file letto e' il gemello sintetico del pacchetto."""
    return source.resolve().is_relative_to(HERE / "data")


def source_banner(file_name: str, synthetic: bool, n_rows: int) -> str:
    """Fascia sempre visibile in cima: dice da quale file vengono i numeri."""
    rows = f"{n_rows:,}".replace(",", ".")
    if synthetic:
        kind, note, css = "DATI SINTETICI", "valori inventati, i numeri non hanno significato", "synthetic"
    else:
        kind, note, css = "DATI VERI", "elaborazione locale, non condividere senza controllo", "real"
    return (f'<div class="banner {css}"><strong>{kind}</strong> · file: <code>{html.escape(file_name)}</code>'
            f" · {rows} righe · generata il {datetime.now():%d/%m/%Y %H:%M} · {note}</div>")


def write_html(sections: list[tuple[str, str, go.Figure | None]], file_name: str, synthetic: bool,
               n_rows: int, out: Path) -> None:
    """Un solo file HTML; la libreria Plotly e' incorporata nella prima figura.

    La Content-Security-Policy impedisce al browser qualsiasi richiesta verso l'esterno:
    anche aprendo la dashboard dei dati veri, la pagina non puo' caricare ne' inviare nulla.
    """
    parts = []
    first = True
    for title, text, fig in sections:
        block = f"<section><h2>{html.escape(title)}</h2><p>{html.escape(text)}</p>"
        if fig is not None:
            block += fig.to_html(full_html=False, include_plotlyjs=True if first else False,
                                 config={"displaylogo": False})
            first = False
        parts.append(block + "</section>")
    name = html.escape(SCHEMA.get("nome_dataset", "Dashboard"))
    prefix = "[SINTETICO] " if synthetic else "[VERI] "
    page = f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:">
<title>{prefix}{name}</title>
<style>
body{{font-family:-apple-system,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:0 24px 24px;color:#1d2433;background:#fff}}
h1{{font-size:1.6rem}} h2{{font-size:1.2rem;margin-top:2rem}} p{{color:#4a5568}}
section{{border-top:1px solid #e2e8f0;padding-top:8px}}
footer{{margin-top:3rem;font-size:.8rem;color:#718096}}
.banner{{position:sticky;top:0;z-index:10;margin:0 -24px;padding:10px 24px;font-size:.95rem;border-bottom:3px solid}}
.banner code{{font-size:.95rem}}
.banner.real{{background:#fff4e5;border-color:#c05621;color:#7b341e}}
.banner.synthetic{{background:#e8f1fd;border-color:#2b6cb0;color:#1a365d}}
</style></head><body>
{source_banner(file_name, synthetic, n_rows)}
<h1>{name}</h1>
{''.join(parts)}
<footer>Elaborazione locale, nessun dato inviato in rete.</footer>
</body></html>"""
    out.write_text(page, encoding="utf-8")


def resolve_output(source: Path, requested: Path | None) -> Path:
    """Decide dove scrivere l'HTML.

    Sul file sintetico: anteprima.html in questa cartella. Su qualsiasi altro file
    (cioe' sui dati veri) l'HTML non puo' finire in questa cartella, che Claude legge:
    il default e' la Scrivania.
    """
    synthetic = is_synthetic(source)
    if requested is None:
        return HERE / "anteprima.html" if synthetic else Path.home() / "Desktop" / f"dashboard-{HERE.name}.html"
    target = requested.expanduser().resolve()
    if not synthetic and target.is_relative_to(HERE):
        sys.exit("Sui dati veri l'HTML va salvato fuori da questa cartella (per esempio sulla Scrivania).")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="file CSV o Excel da analizzare")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="file HTML di uscita (default: anteprima.html per il sintetico, Scrivania per il vero)")
    parser.add_argument("--nome-file", default=None,
                        help="nome da mostrare nella dashboard (l'app lo passa quando usa una copia temporanea)")
    args = parser.parse_args()
    output = resolve_output(args.file, args.output)
    df = load_data(args.file)
    write_html(build_sections(df), args.nome_file or args.file.name, is_synthetic(args.file), len(df), output)
    print(f"Dashboard scritta in {output}")


if __name__ == "__main__":
    main()

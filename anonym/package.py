"""Export del pacchetto su cui lavora Claude Code.

Tutto cio' che finisce qui dentro e' calcolato sul gemello, mai sui dati veri.
Il pacchetto contiene anche le regole che impediscono a Claude Code, aperto in questa
cartella, di leggere file fuori da essa o di uscire in rete, e un ambiente Python
proprio, cosi' Claude puo' lanciare la dashboard senza uscire dalla cartella.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import __version__
from .detect import ETICHETTE, ProfiloColonna
from .io import FormatoFile, scrivi
from .leakcheck import Problema

RADICE = Path(__file__).resolve().parent.parent
TEMPLATE = RADICE / "template"
# fuori da Documents, Scrivania, Download e cartelle cloud, dove di solito stanno i file veri
DESTINAZIONE = Path.home() / "anonym-pacchetti"

# Python fuori dalla home: dentro il sandbox di Claude Code la home non e' leggibile
PYTHON_BASE = [Path("/opt/homebrew/bin/python3.13"), Path("/opt/homebrew/bin/python3.12"),
               Path("/usr/local/bin/python3.13"), Path("/usr/local/bin/python3.12")]
DIPENDENZE = ["pandas==2.3.3", "plotly==7.1.0", "openpyxl==3.1.5"]

# regole per Claude Code, valide solo quando la sessione e' aperta in questa cartella
SETTINGS_CLAUDE = {
    "permissions": {
        "blockReadsOutsideWorkingDirectories": True,
        "blockWritesOutsideWorkingDirectories": True,
        "disableBypassPermissionsMode": "disable",
        "deny": [
            "WebFetch", "WebSearch", "mcp__*",
            "Bash(curl *)", "Bash(wget *)", "Bash(ssh *)", "Bash(scp *)", "Bash(rsync *)",
            "Bash(nc *)", "Bash(open *)", "Bash(gh *)", "Bash(git push *)",
            "Read(./.claude/**)", "Edit(./.claude/**)",
        ],
    },
    "sandbox": {
        "enabled": True,
        "allowUnsandboxedCommands": False,
    },
}

GITIGNORE = """# mai dati veri o dashboard generate nel repo
*.html
dati_veri*
*_vero*
data/*
!data/sintetico.*
.venv/
__pycache__/
.DS_Store
"""

REQUIREMENTS = "\n".join(DIPENDENZE) + "\n"


def slug(testo: str) -> str:
    """Nome sicuro per cartelle e repo."""
    s = re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")
    return s or "dataset"


def _num(x: float, cifre: int) -> str:
    """Numero in formato italiano: 1.234,56."""
    return f"{x:,.{cifre}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _descrivi(s: pd.Series, p: ProfiloColonna) -> str:
    """Statistiche brevi di una colonna del gemello."""
    vuoti = f"{s.isna().mean() * 100:.0f}% vuoti"
    if p.azione == "finto":
        return f"valori inventati, {s.nunique()} distinti; le ricorrenze rispecchiano quelle vere; {vuoti}"
    if p.tipo == "data":
        return f"da {s.min():%d/%m/%Y} a {s.max():%d/%m/%Y}; {vuoti}" if s.notna().any() else vuoti
    if p.tipo in ("numero", "intero"):
        if not s.notna().any():
            return vuoti
        q = s.astype(float).quantile([0, 0.5, 1]).tolist()
        cifre = 0 if p.tipo == "intero" else 2
        return f"min {_num(q[0], cifre)}, mediana {_num(q[1], cifre)}, max {_num(q[2], cifre)}; {vuoti}"
    top = s.value_counts().head(6)
    elenco = ", ".join(f"{v}" for v in top.index)
    altri = f" e altri {s.nunique() - len(top)}" if s.nunique() > len(top) else ""
    return f"{s.nunique()} valori: {elenco}{altri}; {vuoti}"


def _dizionario(gemello: pd.DataFrame, profili: list[ProfiloColonna], nome: str) -> str:
    righe = [
        f"# Dizionario dati: {nome}",
        "",
        "Statistiche calcolate sul **gemello sintetico**: indicano forma e tipo delle colonne, "
        "non i valori reali. Le relazioni tra colonne finte e colonne sintetiche non sono conservate "
        "(per esempio un IBAN finto puo' comparire su un rapporto che non e' un conto).",
        "",
        "| Colonna | Tipo | Origine | Significato | Contenuto nel gemello |",
        "|---|---|---|---|---|",
    ]
    for p in profili:
        if p.azione == "elimina":
            continue
        tipo = p.tipo + (f" (`{p.formato_data}`)" if p.formato_data else "")
        righe.append(f"| `{p.nome}` | {tipo} | {p.azione} | {ETICHETTE.get(p.significato or '', '')} | "
                     f"{_descrivi(gemello[p.nome], p)} |")
    return "\n".join(righe) + "\n"


def _report(problemi: list[Problema], violazioni: dict[str, int], n_eliminate: int) -> str:
    righe = ["# Report anti-fuga", "",
             f"- Colonne eliminate prima dell'export: {n_eliminate} (nomi non riportati)."]
    for vincolo, n in violazioni.items():
        righe.append(f"- Vincolo `{vincolo}`: {n} righe non conformi.")
    if not problemi:
        righe.append("- Nessun problema rilevato.")
    for p in problemi:
        dove = f" `{p.colonna}`" if p.colonna else ""
        righe.append(f"- **{p.livello}**{dove}: {p.messaggio}")
    righe += ["", "I valori coinvolti non sono riportati qui: sono stati mostrati solo a schermo, in locale."]
    return "\n".join(righe) + "\n"


def python_base() -> Path | None:
    """Primo Python disponibile fuori dalla home."""
    return next((p for p in PYTHON_BASE if p.exists()), None)


def crea_ambiente(cartella: Path) -> Path:
    """Crea .venv nel pacchetto con pandas, plotly e openpyxl; restituisce il python da usare.

    Usa uv se c'e' (veloce, file clonati dalla cache), altrimenti venv + pip.
    I pacchetti si scaricano da PyPI: nessun dato esce, solo librerie che entrano.
    """
    base = python_base()
    if base is None:
        raise RuntimeError("Serve un Python di Homebrew (brew install python@3.13): quello di pyenv sta nella home, "
                           "che il sandbox di Claude Code non legge.")
    venv = cartella / ".venv"
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if Path(uv).exists():
        subprocess.run([uv, "venv", "--quiet", "--python", str(base), str(venv)], check=True)
        subprocess.run([uv, "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"), *DIPENDENZE],
                       check=True)
    else:
        subprocess.run([str(base), "-m", "venv", str(venv)], check=True)
        subprocess.run([str(venv / "bin" / "pip"), "install", "--quiet", *DIPENDENZE], check=True)
    return venv / "bin" / "python"


def esporta(gemello: pd.DataFrame, profili: list[ProfiloColonna], formato: FormatoFile, problemi: list[Problema],
            violazioni: dict[str, int], nome: str, destinazione: Path = DESTINAZIONE,
            con_ambiente: bool = True) -> Path:
    """Scrive la cartella del pacchetto e ne restituisce il percorso."""
    if any(p.livello == "bloccante" for p in problemi):
        raise ValueError("Ci sono problemi bloccanti: export annullato.")

    nome_slug = slug(nome)
    cartella = destinazione / f"{nome_slug}-{datetime.now():%Y%m%d-%H%M}"
    if cartella.exists():
        shutil.rmtree(cartella)
    (cartella / "data").mkdir(parents=True)

    attivi = [p for p in profili if p.azione != "elimina"]
    tipi = {p.nome: p.tipo for p in attivi}
    formati_data = {p.nome: p.formato_data for p in attivi}
    file_dati = scrivi(gemello, tipi, formati_data, formato, cartella / "data" / "sintetico")
    ext = file_dati.suffix.lstrip(".")

    schema = {
        "nome_dataset": nome,
        "generato_da": f"anonym-data {__version__}",
        "generato_il": datetime.now().isoformat(timespec="seconds"),
        "righe_sintetiche": len(gemello),
        "formato": formato.to_dict(),
        "colonne": [{
            "nome": p.nome, "tipo": p.tipo, "formato_data": p.formato_data, "azione": p.azione,
            "significato": p.significato, "ammette_vuoti": bool(gemello[p.nome].isna().any()),
        } for p in attivi],
    }
    (cartella / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    (cartella / "DIZIONARIO_DATI.md").write_text(_dizionario(gemello, profili, nome), encoding="utf-8")
    (cartella / "REPORT_ANTIFUGA.md").write_text(
        _report(problemi, violazioni, sum(p.azione == "elimina" for p in profili)), encoding="utf-8")
    (cartella / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (cartella / ".claude").mkdir()
    (cartella / ".claude" / "settings.json").write_text(json.dumps(SETTINGS_CLAUDE, indent=2), encoding="utf-8")
    (cartella / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")

    sostituzioni = {
        "__NOME__": nome, "__RIGHE__": str(len(gemello)), "__COLONNE__": str(len(attivi)), "__EXT__": ext,
        "__DATA__": f"{datetime.now():%d/%m/%Y}", "__REPO__": f"dashboard-{nome_slug}",
    }
    for nome_file in ("CLAUDE.md", "README.md", "dashboard.py"):
        testo = (TEMPLATE / nome_file).read_text(encoding="utf-8")
        for k, v in sostituzioni.items():
            testo = testo.replace(k, v)
        (cartella / nome_file).write_text(testo, encoding="utf-8")
    if con_ambiente:
        crea_ambiente(cartella)
    return cartella

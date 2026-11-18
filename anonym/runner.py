"""Esecuzione della dashboard di un pacchetto sui dati veri, senza Terminale.

Il file vero viene scritto in una cartella temporanea di sistema (fuori dal pacchetto,
che Claude legge) e cancellato appena la dashboard e' pronta. L'HTML va sulla Scrivania.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .package import DESTINAZIONE

SEGNAPOSTO = "Esempio minimo, da sostituire"


@dataclass
class Pacchetto:
    cartella: Path
    nome: str
    modificato: datetime
    completato: bool      # Claude ha sostituito lo scheletro
    python: Path

    @property
    def etichetta(self) -> str:
        stato = "pronta" if self.completato else "scheletro, Claude non ha ancora lavorato"
        return f"{self.cartella.name} · dashboard {stato} · {self.modificato:%d/%m %H:%M}"


def leggi_pacchetto(cartella: Path) -> Pacchetto | None:
    """Descrive un pacchetto, oppure None se la cartella non lo e'."""
    dashboard = cartella / "dashboard.py"
    if not (dashboard.is_file() and (cartella / "schema.json").is_file()):
        return None
    venv = cartella / ".venv" / "bin" / "python"
    return Pacchetto(
        cartella=cartella,
        nome=cartella.name,
        modificato=datetime.fromtimestamp(dashboard.stat().st_mtime),
        completato=SEGNAPOSTO not in dashboard.read_text(encoding="utf-8"),
        python=venv if venv.exists() else Path(sys.executable),
    )


def elenca_pacchetti(destinazione: Path = DESTINAZIONE) -> list[Pacchetto]:
    """Pacchetti disponibili, dal piu' recente."""
    if not destinazione.is_dir():
        return []
    pacchetti = [p for c in destinazione.iterdir() if c.is_dir() and (p := leggi_pacchetto(c))]
    return sorted(pacchetti, key=lambda p: p.modificato, reverse=True)


def percorso_html(pacchetto: Pacchetto) -> Path:
    """Dove finisce la dashboard dei dati veri: Scrivania, fuori dal pacchetto."""
    scrivania = Path.home() / "Desktop"
    return (scrivania if scrivania.is_dir() else Path.home()) / f"dashboard-{pacchetto.nome}.html"


def esegui(pacchetto: Pacchetto, dati: bytes, nome_file: str, uscita: Path | None = None,
           timeout: int = 300) -> tuple[Path, str]:
    """Lancia dashboard.py del pacchetto sul file vero; restituisce (html, messaggi dello script)."""
    uscita = uscita or percorso_html(pacchetto)
    estensione = Path(nome_file).suffix.lower() or ".csv"
    with tempfile.TemporaryDirectory(prefix="anonym-vero-") as tmp:
        vero = Path(tmp) / f"dati{estensione}"
        vero.write_bytes(dati)
        comando = [str(pacchetto.python), str(pacchetto.cartella / "dashboard.py"), str(vero), "-o", str(uscita)]
        if "--nome-file" in (pacchetto.cartella / "dashboard.py").read_text(encoding="utf-8"):
            comando += ["--nome-file", Path(nome_file).name]  # nella dashboard si vede il nome vero del file
        esito = subprocess.run(
            comando,
            capture_output=True, text=True, cwd=tmp, timeout=timeout,
        )
        # all'uscita dal blocco la cartella temporanea e il file vero vengono cancellati
    messaggi = (esito.stdout + "\n" + esito.stderr).strip()
    if esito.returncode != 0:
        raise RuntimeError(messaggi or f"dashboard.py terminato con codice {esito.returncode}")
    return uscita, messaggi

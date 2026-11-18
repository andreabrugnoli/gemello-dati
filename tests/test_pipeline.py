"""Test end-to-end sul dataset demo: nessun dato vero esce, vincoli rispettati, rete bloccata."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from anonym import detect, generate, io, leakcheck, offline, package  # noqa: E402
from demo.crea_demo import crea_demo  # noqa: E402


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    """Dataset demo scritto su disco, profilato, gemello generato ed esportato."""
    offline.attiva()
    base = tmp_path_factory.mktemp("anonym")
    vero_csv = base / "vero.csv"
    crea_demo(n_clienti=400).to_csv(vero_csv, sep=";", decimal=",", index=False)
    grezzo, formato = io.leggi(vero_csv, vero_csv.name)
    profili = detect.profila(grezzo, formato)
    vero = detect.converti(grezzo, profili, formato)
    vincoli = [generate.Vincolo(a, b) for a, b in generate.riduci_vincoli(detect.suggerisci_vincoli(vero, profili))]
    gemello = generate.genera(vero, profili, vincoli=vincoli, fedelta="veloce")
    problemi = leakcheck.controlla(vero, gemello, profili)
    cartella = package.esporta(gemello, profili, formato, problemi, generate.violazioni_vincoli(gemello, vincoli),
                               "Test banca", base / "out", con_ambiente=False)
    return dict(base=base, vero_csv=vero_csv, grezzo=grezzo, formato=formato, profili=profili, vero=vero,
                vincoli=vincoli, gemello=gemello, problemi=problemi, cartella=cartella)


def test_rilevamento_colonne_sensibili(ambiente):
    per_nome = {p.nome: p for p in ambiente["profili"]}
    for col in ("nome", "cognome", "codice_fiscale", "email", "telefono", "iban", "indirizzo", "consulente", "ndg"):
        assert per_nome[col].azione == "finto", col
    assert per_nome["note"].azione == "elimina"
    assert per_nome["data_apertura"].tipo == "data"
    assert per_nome["saldo_medio"].tipo == "numero"


def test_struttura_identica(ambiente):
    attese = [p.nome for p in ambiente["profili"] if p.azione != "elimina"]
    assert list(ambiente["gemello"].columns) == attese
    assert len(ambiente["gemello"]) == len(ambiente["vero"])


def test_nessun_valore_vero_nel_pacchetto(ambiente):
    """Cerca ogni codice fiscale, email, IBAN, telefono e indirizzo veri in tutti i file del pacchetto."""
    grezzo = ambiente["grezzo"]
    sensibili = set()
    for col in ("codice_fiscale", "email", "iban", "telefono", "indirizzo", "ndg", "id_rapporto", "note"):
        sensibili |= set(grezzo[col].dropna().astype(str))
    # nel file dati si confrontano le celle intere (una sottostringa dentro un IBAN finto e' un caso)
    sintetico = next((ambiente["cartella"] / "data").glob("sintetico.*"))
    celle = set(pd.read_csv(sintetico, sep=";", dtype=str).stack().astype(str))
    assert sensibili & celle == set()
    # negli altri file si cercano i valori come parole intere
    import re

    testo = "\n".join(f.read_text(encoding="utf-8", errors="ignore")
                      for f in ambiente["cartella"].rglob("*") if f.is_file() and f != sintetico)
    trovati = [v for v in sensibili if len(v) >= 6 and re.search(rf"(?<![\w@.]){re.escape(v)}(?![\w@])", testo)]
    assert trovati == []


def test_ricorrenze_conservate(ambiente):
    vero = ambiente["vero"].groupby("ndg").size().value_counts().sort_index()
    gemello = ambiente["gemello"].groupby("ndg").size().value_counts().sort_index()
    assert vero.to_dict() == gemello.to_dict()


def test_vincoli_rispettati(ambiente):
    assert ambiente["vincoli"], "nessun vincolo proposto"
    assert all(n == 0 for n in generate.violazioni_vincoli(ambiente["gemello"], ambiente["vincoli"]).values())


def test_nessun_bloccante_con_azioni_proposte(ambiente):
    assert not leakcheck.ha_bloccanti(ambiente["problemi"])


def test_bloccante_se_si_sintetizza_un_identificativo(ambiente):
    profili = [detect.ProfiloColonna(**p.to_dict()) for p in ambiente["profili"]]
    for p in profili:
        if p.nome == "consulente":
            p.azione = "sintetico"
    gemello = generate.genera(ambiente["vero"], profili, fedelta="veloce")
    problemi = leakcheck.controlla(ambiente["vero"], gemello, profili)
    assert any(p.livello == "bloccante" and p.colonna == "consulente" for p in problemi)
    with pytest.raises(ValueError):
        package.esporta(gemello, profili, ambiente["formato"], problemi, {}, "x", ambiente["base"] / "no",
                        con_ambiente=False)


def test_report_senza_valori(ambiente):
    report = (ambiente["cartella"] / "REPORT_ANTIFUGA.md").read_text(encoding="utf-8")
    for p in ambiente["problemi"]:
        for v in p.dettaglio_locale:
            assert v not in report


def test_rete_bloccata():
    offline.attiva()
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 443), timeout=2)
    with pytest.raises(OSError):
        s = socket.socket()
        try:
            s.connect(("1.1.1.1", 443))
        finally:
            s.close()


def test_localhost_permesso():
    offline.attiva()
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket()
    client.connect(server.getsockname())
    client.close()
    server.close()


def test_dashboard_gira_su_vero_e_sintetico(ambiente):
    cartella = ambiente["cartella"]
    schema = json.loads((cartella / "schema.json").read_text(encoding="utf-8"))
    assert schema["formato"]["sep"] == ";"
    sintetico = next((cartella / "data").glob("sintetico.*"))
    for sorgente, nome in ((sintetico, "s.html"), (ambiente["vero_csv"], "v.html")):
        out = ambiente["base"] / nome
        r = subprocess.run([sys.executable, str(cartella / "dashboard.py"), str(sorgente), "-o", str(out)],
                           capture_output=True, text=True, cwd=ambiente["base"])
        assert r.returncode == 0, r.stderr
        html = out.read_text(encoding="utf-8")
        assert "<script src=" not in html
        assert "Content-Security-Policy" in html
        atteso = "DATI SINTETICI" if sorgente == sintetico else "DATI VERI"
        assert f"<strong>{atteso}</strong>" in html


def test_formato_sintetico_uguale_al_vero(ambiente):
    """Il file sintetico si rilegge con lo stesso separatore, decimali e formato date del vero."""
    sintetico = next((ambiente["cartella"] / "data").glob("sintetico.*"))
    grezzo_s, formato_s = io.leggi(sintetico, sintetico.name)
    assert (formato_s.sep, formato_s.decimal) == (ambiente["formato"].sep, ambiente["formato"].decimal)
    profili_s = {p.nome: p for p in detect.profila(grezzo_s, formato_s)}
    for p in ambiente["profili"]:
        if p.azione == "sintetico" and p.tipo == "data":
            assert profili_s[p.nome].formato_data == p.formato_data


def test_excel(tmp_path):
    """Un file Excel produce un gemello Excel con lo stesso foglio."""
    df = crea_demo(n_clienti=120)
    df["data_apertura"] = pd.to_datetime(df["data_apertura"], format="%d/%m/%Y")
    percorso = tmp_path / "vero.xlsx"
    df.to_excel(percorso, sheet_name="Rapporti", index=False)
    grezzo, formato = io.leggi(percorso, percorso.name)
    assert formato.tipo == "xlsx" and formato.foglio == "Rapporti"
    profili = detect.profila(grezzo, formato)
    vero = detect.converti(grezzo, profili, formato)
    gemello = generate.genera(vero, profili, fedelta="veloce")
    cartella = package.esporta(gemello, profili, formato, [], {}, "xl", tmp_path, con_ambiente=False)
    assert (cartella / "data" / "sintetico.xlsx").exists()


def test_dashboard_non_scrive_il_vero_nel_pacchetto(ambiente):
    cartella = ambiente["cartella"]
    r = subprocess.run([sys.executable, str(cartella / "dashboard.py"), str(ambiente["vero_csv"]),
                        "-o", str(cartella / "vero.html")], capture_output=True, text=True)
    assert r.returncode != 0
    assert not (cartella / "vero.html").exists()


def test_settings_claude(ambiente):
    impostazioni = json.loads((ambiente["cartella"] / ".claude" / "settings.json").read_text())
    assert impostazioni["permissions"]["blockReadsOutsideWorkingDirectories"] is True
    assert impostazioni["sandbox"]["enabled"] is True
    assert "mcp__*" in impostazioni["permissions"]["deny"]


@pytest.mark.skipif(package.python_base() is None, reason="manca un Python di Homebrew")
def test_ambiente_del_pacchetto(ambiente, tmp_path):
    """Il .venv del pacchetto usa un Python fuori dalla home e fa girare la dashboard."""
    import shutil

    copia = tmp_path / "pkg"
    shutil.copytree(ambiente["cartella"], copia)
    python = package.crea_ambiente(copia)
    reale = python.resolve()
    assert not reale.is_relative_to(Path.home()) or reale.is_relative_to(copia)
    sintetico = next((copia / "data").glob("sintetico.*"))
    r = subprocess.run([str(python), str(copia / "dashboard.py"), str(sintetico)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (copia / "anteprima.html").exists()


def test_runner_esegue_sul_vero_senza_lasciare_tracce(ambiente, tmp_path):
    from anonym import runner

    pacchetti = runner.elenca_pacchetti(ambiente["cartella"].parent)
    assert [p.cartella for p in pacchetti] == [ambiente["cartella"]]
    pacchetto = pacchetti[0]
    assert pacchetto.completato is False  # scheletro non ancora toccato da Claude
    prima = {f.relative_to(pacchetto.cartella) for f in pacchetto.cartella.rglob("*")}
    html, _ = runner.esegui(pacchetto, ambiente["vero_csv"].read_bytes(), "vero.csv", uscita=tmp_path / "d.html")
    testo = html.read_text(encoding="utf-8")
    assert "Content-Security-Policy" in testo
    assert "<strong>DATI VERI</strong> · file: <code>vero.csv</code>" in testo  # nome originale, non quello temporaneo
    assert "<title>[VERI]" in testo
    dopo = {f.relative_to(pacchetto.cartella) for f in pacchetto.cartella.rglob("*")}
    assert dopo == prima  # niente file vero ne' HTML dentro il pacchetto


def test_runner_errore_leggibile(ambiente, tmp_path):
    from anonym import runner

    pacchetto = runner.leggi_pacchetto(ambiente["cartella"])
    with pytest.raises(RuntimeError, match="mancano"):
        runner.esegui(pacchetto, b"a;b\n1;2\n", "altro.csv", uscita=tmp_path / "x.html")

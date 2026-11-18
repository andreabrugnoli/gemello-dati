"""Genera un dataset bancario inventato da usare come "dati veri" per test e demo in aula.

Tutti i valori sono fittizi (Faker it_IT), ma il file va trattato come se fosse reale.
Uso: python demo/crea_demo.py [percorso_output]
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

SEED = 7
N_CLIENTI = 1300

COMUNI = [
    ("Verona", "37121", "VR", 30), ("San Bonifacio", "37047", "VR", 6), ("Legnago", "37045", "VR", 6),
    ("Villafranca di Verona", "37069", "VR", 7), ("Bussolengo", "37012", "VR", 5),
    ("Vicenza", "36100", "VI", 10), ("Padova", "35121", "PD", 9), ("Mantova", "46100", "MN", 5),
    ("Peschiera del Garda", "37019", "VR", 3), ("Soave", "37038", "VR", 2), ("Badia Calavena", "37030", "VR", 1),
]
FILIALI = ["Verona Centro", "Verona Borgo Trento", "San Bonifacio", "Legnago", "Villafranca", "Bussolengo",
           "Vicenza", "Padova"]
SEGMENTI = {"Privato": 0.62, "Affluent": 0.18, "Small business": 0.13, "PMI": 0.07}
RAPPORTI = {"Conto corrente": 0.45, "Deposito titoli": 0.18, "Carta di credito": 0.17, "Mutuo": 0.12,
            "Prestito personale": 0.08}
NOTE = ["Cliente chiede rinegoziazione del mutuo", "Segnalato ritardo pagamento rata",
        "Interessato a fondo pensione", "Richiesta aumento fido", "Contattare per rinnovo carta",
        "Cliente in contenzioso con la filiale", "Preferisce contatto telefonico"]


def _scegli(rng: random.Random, pesi: dict[str, float]) -> str:
    """Estrae una chiave secondo i pesi."""
    return rng.choices(list(pesi), weights=list(pesi.values()))[0]


def crea_demo(n_clienti: int = N_CLIENTI, seed: int = SEED) -> pd.DataFrame:
    """Costruisce il DataFrame dei rapporti bancari fittizi."""
    fake = Faker("it_IT")
    Faker.seed(seed)
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    consulenti = [f"{fake.first_name()} {fake.last_name()}" for _ in range(25)]

    righe = []
    n_rapporto = 0
    for i in range(n_clienti):
        nome, cognome = fake.first_name(), fake.last_name()
        comune, cap, prov, _ = rng.choices(COMUNI, weights=[c[3] for c in COMUNI])[0]
        segmento = _scegli(rng, SEGMENTI)
        nascita = date(1940, 1, 1) + timedelta(days=rng.randint(0, 365 * 63))
        cliente = {
            "ndg": f"{4100000 + i * 7:08d}",
            "nome": nome,
            "cognome": cognome,
            "codice_fiscale": fake.ssn(),
            "email": f"{nome}.{cognome}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'libero.it', 'yahoo.it', 'outlook.it', 'hotmail.it'])}".lower().replace(" ", ""),
            "telefono": fake.phone_number(),
            "indirizzo": fake.street_address(),
            "cap": cap,
            "comune": comune,
            "provincia": prov,
            "data_nascita": nascita.strftime("%d/%m/%Y"),
            "sesso": rng.choice(["M", "F"]),
            "segmento": segmento,
            "filiale": rng.choice(FILIALI),
            "consulente": rng.choice(consulenti),
        }
        # numero di rapporti per cliente: per lo piu' uno, alcuni ne hanno molti
        n_rapp = min(1 + int(nrng.geometric(0.62)) - 1, 8)
        for _ in range(n_rapp):
            n_rapporto += 1
            tipo = _scegli(rng, RAPPORTI)
            apertura = date(2008, 1, 1) + timedelta(days=rng.randint(0, 365 * 17))
            chiusura = ""
            if rng.random() < 0.22:
                chiusura = (apertura + timedelta(days=rng.randint(30, 3000))).strftime("%d/%m/%Y")
            base = {"Privato": 9, "Affluent": 11, "Small business": 10.5, "PMI": 12}[segmento]
            saldo = float(nrng.lognormal(base, 0.9))
            if tipo in ("Mutuo", "Prestito personale"):
                saldo = -abs(saldo) * 3
            righe.append({
                "id_rapporto": f"R{n_rapporto:06d}",
                **cliente,
                "iban": fake.iban() if tipo == "Conto corrente" else "",
                "tipo_rapporto": tipo,
                "data_apertura": apertura.strftime("%d/%m/%Y"),
                "data_chiusura": chiusura,
                "saldo_medio": round(saldo, 2),
                "operazioni_mese": int(nrng.poisson(14 if tipo == "Conto corrente" else 2)),
                "rating_rischio": int(np.clip(nrng.normal(4, 2), 1, 10)),
                "canale_digitale": "Sì" if rng.random() < (0.75 if nascita.year > 1970 else 0.35) else "No",
                "note": rng.choice(NOTE) if rng.random() < 0.15 else "",
            })
    return pd.DataFrame(righe)


def main() -> None:
    """Scrive il CSV in formato italiano (separatore ';', decimali con la virgola)."""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "rapporti_banca_demo.csv"
    df = crea_demo()
    df.to_csv(out, sep=";", decimal=",", index=False, encoding="utf-8")
    print(f"{len(df)} rapporti di {df['ndg'].nunique()} clienti scritti in {out}")


if __name__ == "__main__":
    main()

"""
Supervisor — Profilo Contribuente & Coordinamento

Fonte di verita unica per tutti i dati del contribuente.
Mantiene profilo, storico pluriennale, stato ciclo fiscale.
Tutti gli agenti leggono/scrivono tramite questo modulo.

File di stato: data/contribuente/profilo.json
              data/contribuente/storico_YYYY.json
"""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings

logger = logging.getLogger("supervisor")

PROFILO_FILE = settings.DATA_CONTRIBUENTE / "profilo.json"


# ---------------------------------------------------------------------------
# Profilo contribuente
# ---------------------------------------------------------------------------
def profilo_vuoto() -> dict:
    return {
        "anagrafica": {
            "nome": "", "cognome": "", "codice_fiscale": "",
            "data_nascita": "", "comune_nascita": "", "provincia_nascita": "",
            "residenza": "", "email": "", "telefono": "",
        },
        "piva": {
            "numero": "", "data_apertura": "", "data_cessazione": None,
            "stato": "attiva",  # attiva | in_chiusura | cessata_adempimenti_pendenti | cessata_completata
            "ateco_primario": "", "ateco_secondario": "",
            "coefficiente_redditivita": 0,
        },
        "regime": {
            "tipo": "forfettario",
            "aliquota": 0.05,
            "anno_inizio": None,
            "riduzione_contributiva_35": False,
        },
        "inps": {
            "gestione": "separata",  # separata | artigiani | commercianti
        },
        "firma_digitale": {
            "provider": "", "scadenza": "",
        },
        "banca": {
            "iban": "", "provider_psd2": "",
        },
        "canali_notifica": {
            "email": "", "telefono": "", "telegram_chat_id": "",
        },
        "configurazione": {
            "soglia_auto_approvazione_f24": 500,
            "auto_approvazione_fatture": False,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def carica_profilo() -> dict:
    if PROFILO_FILE.exists():
        with open(PROFILO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return profilo_vuoto()


def salva_profilo(profilo: dict):
    profilo["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROFILO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILO_FILE, "w", encoding="utf-8") as f:
        json.dump(profilo, f, indent=2, ensure_ascii=False)
    logger.info("Profilo salvato: %s", PROFILO_FILE)


def aggiorna_profilo(aggiornamenti: dict) -> dict:
    profilo = carica_profilo()
    for key, value in aggiornamenti.items():
        if isinstance(value, dict) and key in profilo:
            profilo[key].update(value)
        else:
            profilo[key] = value
    salva_profilo(profilo)
    return profilo


# ---------------------------------------------------------------------------
# Storico annuale
# ---------------------------------------------------------------------------
def storico_file(anno: int) -> Path:
    return settings.DATA_CONTRIBUENTE / f"storico_{anno}.json"


def storico_vuoto(anno: int) -> dict:
    return {
        "anno": anno,
        "ricavi_totali": 0,
        "reddito_imponibile": 0,
        "imposta_sostitutiva": {"importo": 0, "aliquota": 0, "pagato": False},
        "contributi_inps": {"fissi": 0, "percentuali": 0, "totale": 0, "pagato": False},
        "acconti_versati": [],
        "saldo": {"importo": 0, "data_versamento": None},
        "dichiarazione": {"file": None, "data_invio": None, "ricevuta": None},
        "f24_generati": [],
        "f24_pagati": [],
        "fatture_emesse": [],
        "bollo_virtuale": {
            "totale_annuo": 0,
            "versamenti_trimestrali": [],
        },
        "crediti_imposta": {
            "residuo_anno_precedente": 0,
            "utilizzato_in_compensazione": 0,
            "residuo_fine_anno": 0,
        },
        "eventi": [],
    }


def carica_storico(anno: int) -> dict:
    f = storico_file(anno)
    if f.exists():
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return storico_vuoto(anno)


def salva_storico(storico: dict):
    f = storico_file(storico["anno"])
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(storico, fh, indent=2, ensure_ascii=False)
    logger.info("Storico %d salvato", storico["anno"])


# ---------------------------------------------------------------------------
# Fatture
# ---------------------------------------------------------------------------
def registra_fattura(anno: int, fattura: dict):
    storico = carica_storico(anno)
    storico["fatture_emesse"].append(fattura)
    storico["ricavi_totali"] = sum(f["importo"] for f in storico["fatture_emesse"])
    profilo = carica_profilo()
    coeff = profilo["piva"]["coefficiente_redditivita"] / 100
    storico["reddito_imponibile"] = round(storico["ricavi_totali"] * coeff, 2)
    salva_storico(storico)
    return storico


def registra_f24(anno: int, f24: dict):
    storico = carica_storico(anno)
    storico["f24_generati"].append(f24)
    salva_storico(storico)


def registra_pagamento_f24(anno: int, pagamento: dict):
    storico = carica_storico(anno)
    storico["f24_pagati"].append(pagamento)
    salva_storico(storico)


# ---------------------------------------------------------------------------
# Eventi / Audit trail
# ---------------------------------------------------------------------------
def registra_evento(anno: int, tipo: str, descrizione: str):
    storico = carica_storico(anno)
    storico["eventi"].append({
        "data": datetime.now(timezone.utc).isoformat(),
        "tipo": tipo,
        "descrizione": descrizione,
    })
    salva_storico(storico)


# ---------------------------------------------------------------------------
# Stato complessivo
# ---------------------------------------------------------------------------
def stato_corrente() -> dict:
    profilo = carica_profilo()
    anno = date.today().year
    storico = carica_storico(anno)
    return {
        "profilo": profilo,
        "storico_corrente": storico,
        "anno": anno,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        p = profilo_vuoto()
        salva_profilo(p)
        s = storico_vuoto(date.today().year)
        salva_storico(s)
        print(f"Profilo e storico {date.today().year} inizializzati.")
    else:
        stato = stato_corrente()
        print(json.dumps(stato, indent=2, ensure_ascii=False))

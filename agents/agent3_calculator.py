"""
Agent3 — Calculator (deterministico)

Calcola imposta sostitutiva, contributi INPS, acconti e saldo.
Genera importi F24 con codici tributo corretti.

Questo agente e' DETERMINISTICO (zero LLM) — fa solo aritmetica.
Nella versione originale Agent3 usa LLM e Agent3b valida.
Qui li uniamo: il calcolo e' gia' deterministico, la validazione e' intrinseca.

Input:  data/contribuente/profilo.json + storico_YYYY.json
Output: context/calcolo_YYYY.json
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from agents.supervisor import carica_profilo, carica_storico, salva_storico, registra_evento

LOGS_DIR = settings.LOGS_DIR
CONTEXT_DIR = settings.CONTEXT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent3.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent3")


def calcola_imposta(ricavi: float, coefficiente: float, aliquota: float,
                    inps_pagati_anno: float = 0) -> dict:
    """Calcola imposta sostitutiva forfettaria."""
    reddito = round(ricavi * coefficiente, 2)
    reddito_netto = max(0, reddito - inps_pagati_anno)
    imposta = round(reddito_netto * aliquota, 2)
    return {
        "ricavi": ricavi,
        "coefficiente": coefficiente,
        "reddito_lordo": reddito,
        "inps_dedotti": inps_pagati_anno,
        "reddito_imponibile": reddito_netto,
        "aliquota": aliquota,
        "imposta": imposta,
    }


def calcola_inps_gestione_separata(reddito: float) -> dict:
    """Contributi INPS gestione separata."""
    gs = settings.INPS["gestione_separata"]
    base = min(reddito, gs["massimale"])
    contributi = round(base * gs["aliquota"], 2)
    return {
        "gestione": "separata",
        "base_imponibile": base,
        "aliquota": gs["aliquota"],
        "contributi_totali": contributi,
        "fissi": 0,
        "variabili": contributi,
    }


def calcola_inps_artigiani(reddito: float, riduzione_35: bool = False) -> dict:
    """Contributi INPS artigiani con eventuale riduzione 35%."""
    art = settings.INPS["artigiani"]
    rid = (1 - art["riduzione_forfettari"]) if riduzione_35 else 1

    fissi = round(art["contributo_fisso"] * rid, 2)

    eccedente = max(0, reddito - art["minimale"])
    if eccedente > 0:
        sotto_fascia = min(eccedente, art["soglia_prima_fascia"] - art["minimale"])
        sopra_fascia = max(0, eccedente - sotto_fascia)
        variabili = (sotto_fascia * art["aliquota"] + sopra_fascia * art["aliquota_oltre_fascia"])
        variabili = round(variabili * rid, 2)
    else:
        variabili = 0

    return {
        "gestione": "artigiani",
        "base_imponibile": reddito,
        "riduzione_35": riduzione_35,
        "fissi": fissi,
        "variabili": variabili,
        "contributi_totali": round(fissi + variabili, 2),
    }


def calcola_inps_commercianti(reddito: float, riduzione_35: bool = False) -> dict:
    """Contributi INPS commercianti con eventuale riduzione 35%."""
    com = settings.INPS["commercianti"]
    rid = (1 - com["riduzione_forfettari"]) if riduzione_35 else 1

    fissi = round(com["contributo_fisso"] * rid, 2)

    eccedente = max(0, reddito - com["minimale"])
    if eccedente > 0:
        sotto_fascia = min(eccedente, com["soglia_prima_fascia"] - com["minimale"])
        sopra_fascia = max(0, eccedente - sotto_fascia)
        variabili = (sotto_fascia * com["aliquota"] + sopra_fascia * com["aliquota_oltre_fascia"])
        variabili = round(variabili * rid, 2)
    else:
        variabili = 0

    return {
        "gestione": "commercianti",
        "base_imponibile": reddito,
        "riduzione_35": riduzione_35,
        "fissi": fissi,
        "variabili": variabili,
        "contributi_totali": round(fissi + variabili, 2),
    }


def calcola_acconti(imposta_anno_precedente: float) -> dict:
    """Calcola acconti dovuti basandosi sull'anno precedente."""
    if imposta_anno_precedente <= settings.REGIME["soglia_acconti_minima"]:
        return {"dovuti": False, "primo_acconto": 0, "secondo_acconto": 0, "totale": 0}

    totale = imposta_anno_precedente
    primo = round(totale * 0.40, 2)
    secondo = round(totale * 0.60, 2)
    return {
        "dovuti": True,
        "primo_acconto": primo,
        "secondo_acconto": secondo,
        "totale": round(primo + secondo, 2),
    }


def calcola_bollo_virtuale(fatture: list) -> dict:
    """Calcola bollo virtuale sulle fatture emesse."""
    soglia = settings.REGIME["bollo_virtuale_soglia"]
    importo_bollo = settings.REGIME["bollo_virtuale_importo"]

    trimestri = {1: 0, 2: 0, 3: 0, 4: 0}
    for f in fatture:
        if f.get("importo", 0) > soglia:
            mese = int(f.get("data", "2026-01-01").split("-")[1])
            q = (mese - 1) // 3 + 1
            trimestri[q] += importo_bollo

    return {
        "totale": sum(trimestri.values()),
        "per_trimestre": trimestri,
    }


def calcola_tutto(anno: int = None) -> dict:
    """Esegue il calcolo fiscale completo per l'anno."""
    if anno is None:
        anno = date.today().year

    profilo = carica_profilo()
    storico = carica_storico(anno)
    storico_prec = carica_storico(anno - 1)

    ricavi = storico["ricavi_totali"]
    coeff = profilo["piva"]["coefficiente_redditivita"] / 100
    aliquota = profilo["regime"]["aliquota"]
    gestione = profilo["inps"]["gestione"]
    riduzione = profilo["regime"].get("riduzione_contributiva_35", False)

    reddito = round(ricavi * coeff, 2)

    # INPS
    if gestione == "separata":
        inps = calcola_inps_gestione_separata(reddito)
    elif gestione == "artigiani":
        inps = calcola_inps_artigiani(reddito, riduzione)
    else:
        inps = calcola_inps_commercianti(reddito, riduzione)

    # INPS pagati nell'anno (per deduzione)
    inps_pagati = sum(p.get("importo", 0) for p in storico.get("f24_pagati", [])
                      if "inps" in p.get("tipo", "").lower())

    # Imposta
    imposta = calcola_imposta(ricavi, coeff, aliquota, inps_pagati)

    # Acconti
    imposta_prec = storico_prec.get("imposta_sostitutiva", {}).get("importo", 0)
    acconti = calcola_acconti(imposta_prec)

    # Bollo virtuale
    bollo = calcola_bollo_virtuale(storico.get("fatture_emesse", []))

    # Totale
    totale_tasse = round(inps["contributi_totali"] + imposta["imposta"], 2)

    risultato = {
        "anno": anno,
        "ricavi": ricavi,
        "imposta": imposta,
        "inps": inps,
        "acconti": acconti,
        "bollo_virtuale": bollo,
        "totale_tasse": totale_tasse,
        "netto": round(ricavi - totale_tasse, 2),
        "aliquota_effettiva": round((totale_tasse / ricavi * 100), 1) if ricavi > 0 else 0,
        "accantonamento_mensile": round(totale_tasse / 12, 2) if ricavi > 0 else 0,
        "calcolato_il": date.today().isoformat(),
    }

    # Salva
    output = CONTEXT_DIR / f"calcolo_{anno}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(risultato, f, indent=2, ensure_ascii=False)
    logger.info("Calcolo %d completato: tasse=%s netto=%s", anno, totale_tasse, risultato["netto"])

    registra_evento(anno, "calcolo", f"Calcolo fiscale completato: tasse {totale_tasse}, netto {risultato['netto']}")

    return risultato


if __name__ == "__main__":
    anno = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    r = calcola_tutto(anno)
    print(json.dumps(r, indent=2, ensure_ascii=False))

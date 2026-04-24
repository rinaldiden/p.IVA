"""
Agent6 — Payment Scheduler

Genera F24 precompilati e costruisce lo scadenzario annuale.
Legge i calcoli da Agent3 e genera i modelli F24.

Input:  context/calcolo_YYYY.json + profilo contribuente
Output: data/f24/ANNO/f24_*.json + context/scadenzario_YYYY.json
"""

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from agents.supervisor import (
    carica_profilo, carica_storico, registra_f24, registra_evento
)

LOGS_DIR = settings.LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent6.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent6")


def genera_f24(anno: int, codice_tributo: str, importo: float,
               descrizione: str, scadenza: str, sezione: str = "erario",
               periodo_da: str = "", periodo_a: str = "") -> dict:
    """Genera un singolo F24 e lo salva."""
    profilo = carica_profilo()
    ana = profilo["anagrafica"]

    f24 = {
        "contribuente": {
            "codice_fiscale": ana.get("codice_fiscale", ""),
            "cognome": ana.get("cognome", ""),
            "nome": ana.get("nome", ""),
        },
        "sezione": sezione,
        "codice_tributo": codice_tributo,
        "anno_riferimento": str(anno),
        "importo": round(importo, 2),
        "descrizione": descrizione,
        "scadenza": scadenza,
        "stato": "da_pagare",
        "generato_il": datetime.now(timezone.utc).isoformat(),
    }

    if sezione == "inps":
        f24["periodo_da"] = periodo_da
        f24["periodo_a"] = periodo_a

    # Salva file
    f24_dir = settings.DATA_F24 / str(anno)
    f24_dir.mkdir(parents=True, exist_ok=True)

    existing = list(f24_dir.glob("f24_*.json"))
    num = len(existing) + 1
    f24_file = f24_dir / f"f24_{num:03d}_{codice_tributo}.json"

    with open(f24_file, "w", encoding="utf-8") as fh:
        json.dump(f24, fh, indent=2, ensure_ascii=False)

    registra_f24(anno, f24)
    logger.info("F24 generato: %s €%.2f scadenza %s", codice_tributo, importo, scadenza)

    return f24


def genera_scadenzario(anno: int) -> dict:
    """Genera lo scadenzario completo per l'anno."""
    # Carica calcolo
    calcolo_file = settings.CONTEXT_DIR / f"calcolo_{anno}.json"
    if not calcolo_file.exists():
        logger.error("Calcolo %d non trovato, esegui prima agent3_calculator", anno)
        return {"errore": "calcolo non trovato"}

    with open(calcolo_file, "r", encoding="utf-8") as f:
        calcolo = json.load(f)

    profilo = carica_profilo()
    gestione = profilo["inps"]["gestione"]
    anno_apertura = profilo["regime"].get("anno_inizio", anno)
    primo_anno = (anno == anno_apertura)

    imposta = calcolo["imposta"]["imposta"]
    inps = calcolo["inps"]
    acconti = calcolo["acconti"]
    bollo = calcolo["bollo_virtuale"]

    scadenze = []
    f24_generati = []

    # --- IMPOSTA SOSTITUTIVA ---
    if not primo_anno:
        # Saldo anno precedente
        f = genera_f24(anno, "1792", imposta, "Saldo imposta sostitutiva", f"{anno}-06-30")
        f24_generati.append(f)
        scadenze.append({"data": f"{anno}-06-30", "tipo": "saldo_imposta", "importo": imposta})

        # Acconti
        if acconti["dovuti"]:
            f = genera_f24(anno, "1790", acconti["primo_acconto"],
                          "Primo acconto imposta sostitutiva (40%)", f"{anno}-06-30")
            f24_generati.append(f)
            scadenze.append({"data": f"{anno}-06-30", "tipo": "primo_acconto", "importo": acconti["primo_acconto"]})

            f = genera_f24(anno, "1791", acconti["secondo_acconto"],
                          "Secondo acconto imposta sostitutiva (60%)", f"{anno}-11-30")
            f24_generati.append(f)
            scadenze.append({"data": f"{anno}-11-30", "tipo": "secondo_acconto", "importo": acconti["secondo_acconto"]})
    else:
        scadenze.append({"data": f"{anno}-06-30", "tipo": "info",
                        "nota": "Primo anno: nessun acconto dovuto. Il saldo si paga l'anno prossimo."})

    # --- INPS ---
    if gestione == "separata":
        if not primo_anno:
            f = genera_f24(anno, "PXX", inps["contributi_totali"],
                          "Saldo INPS gestione separata", f"{anno}-06-30", sezione="inps")
            f24_generati.append(f)
            scadenze.append({"data": f"{anno}-06-30", "tipo": "saldo_inps_gs", "importo": inps["contributi_totali"]})
        else:
            scadenze.append({"data": f"{anno}-06-30", "tipo": "info",
                            "nota": "Primo anno GS: nessun acconto INPS. Il saldo si paga l'anno prossimo."})

    elif gestione in ("artigiani", "commercianti"):
        # Rate fisse trimestrali
        rata = round(inps["fissi"] / 4, 2)
        causale = "AF" if gestione == "artigiani" else "CF"
        date_rate = [
            (f"{anno}-05-16", "gen-mar", "01", "03"),
            (f"{anno}-08-20", "apr-giu", "04", "06"),
            (f"{anno}-11-16", "lug-set", "07", "09"),
            (f"{anno + 1}-02-16", "ott-dic", "10", "12"),
        ]
        for data_scad, periodo, da, a in date_rate:
            f = genera_f24(anno, causale, rata,
                          f"INPS fisso {gestione} — {periodo}", data_scad,
                          sezione="inps", periodo_da=f"{anno}{da}", periodo_a=f"{anno}{a}")
            f24_generati.append(f)
            scadenze.append({"data": data_scad, "tipo": f"inps_fisso_{periodo}", "importo": rata})

        # Eccedente minimale (saldo anno successivo se primo anno)
        if inps["variabili"] > 0:
            if not primo_anno:
                causale_ecc = "AP" if gestione == "artigiani" else "CP"
                f = genera_f24(anno, causale_ecc, inps["variabili"],
                              f"Saldo INPS eccedente {gestione}", f"{anno}-06-30", sezione="inps")
                f24_generati.append(f)
                scadenze.append({"data": f"{anno}-06-30", "tipo": "inps_eccedente", "importo": inps["variabili"]})
            else:
                scadenze.append({"data": f"{anno + 1}-06-30", "tipo": "inps_eccedente_prossimo_anno",
                                "importo": inps["variabili"],
                                "nota": "Primo anno: eccedente INPS da pagare l'anno prossimo."})

    # --- BOLLO VIRTUALE ---
    codici_bollo = {1: "2501", 2: "2502", 3: "2503", 4: "2504"}
    date_bollo = {1: f"{anno}-05-31", 2: f"{anno}-09-30", 3: f"{anno}-11-30", 4: f"{anno + 1}-02-28"}

    for q, importo_q in bollo["per_trimestre"].items():
        q = int(q)
        if importo_q > 0:
            f = genera_f24(anno, codici_bollo[q], importo_q,
                          f"Bollo virtuale fatture Q{q}", date_bollo[q])
            f24_generati.append(f)
            scadenze.append({"data": date_bollo[q], "tipo": f"bollo_q{q}", "importo": importo_q})

    # --- DIRITTO CAMERALE ---
    if gestione in ("artigiani", "commercianti"):
        f = genera_f24(anno, "3850", 120.00, "Diritto annuale CCIAA", f"{anno}-06-30",
                      sezione="regioni_enti_locali")
        f24_generati.append(f)
        scadenze.append({"data": f"{anno}-06-30", "tipo": "cciaa", "importo": 120.00})

    # --- DICHIARAZIONE ---
    scadenze.append({"data": f"{anno}-11-30", "tipo": "dichiarazione",
                    "nota": "Invio telematico Modello Redditi PF"})

    # Ordina per data
    scadenze.sort(key=lambda x: x["data"])

    risultato = {
        "anno": anno,
        "primo_anno": primo_anno,
        "gestione_inps": gestione,
        "totale_f24": sum(f["importo"] for f in f24_generati),
        "num_f24": len(f24_generati),
        "scadenze": scadenze,
        "generato_il": date.today().isoformat(),
    }

    output = settings.CONTEXT_DIR / f"scadenzario_{anno}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(risultato, f, indent=2, ensure_ascii=False)

    registra_evento(anno, "scadenzario", f"Scadenzario generato: {len(scadenze)} scadenze, {len(f24_generati)} F24")
    logger.info("Scadenzario %d: %d scadenze, %d F24, totale €%.2f",
                anno, len(scadenze), len(f24_generati), risultato["totale_f24"])

    return risultato


if __name__ == "__main__":
    anno = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    r = genera_scadenzario(anno)
    print(json.dumps(r, indent=2, ensure_ascii=False))

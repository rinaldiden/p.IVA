"""
Agent4 — Compliance Checker

Monitora soglie ricavi, verifica marca da bollo, cause ostative.
Legge lo storico dal Supervisor e genera alert.

Output: context/compliance_YYYY.json
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from agents.supervisor import carica_profilo, carica_storico, registra_evento

LOGS_DIR = settings.LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent4.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent4")


def controlla_soglie(ricavi: float) -> list[dict]:
    alerts = []
    for s in settings.SOGLIE_ALERT:
        if ricavi >= s["soglia"]:
            alerts.append({
                "soglia": s["soglia"],
                "livello": s["livello"],
                "messaggio": s["messaggio"],
                "ricavi_attuali": ricavi,
            })
    return alerts


def controlla_bollo(fatture: list) -> list[dict]:
    alerts = []
    soglia = settings.REGIME["bollo_virtuale_soglia"]
    for f in fatture:
        if f.get("importo", 0) > soglia and not f.get("bollo_virtuale", False):
            alerts.append({
                "tipo": "bollo_mancante",
                "livello": "warning",
                "fattura": f.get("numero"),
                "importo": f.get("importo"),
                "messaggio": f"Fattura {f.get('numero')}: importo €{f.get('importo')} > €{soglia} senza bollo virtuale",
            })
    return alerts


def proiezione_annuale(ricavi: float, mese_corrente: int) -> dict:
    if mese_corrente == 0:
        return {"proiezione": 0, "mese": 0}
    proiezione = round(ricavi / mese_corrente * 12, 2)
    return {
        "ricavi_attuali": ricavi,
        "mese_corrente": mese_corrente,
        "proiezione_annuale": proiezione,
        "supera_85k": proiezione > 85000,
        "supera_100k": proiezione > 100000,
    }


def controlla_compliance(anno: int = None) -> dict:
    if anno is None:
        anno = date.today().year

    storico = carica_storico(anno)
    ricavi = storico.get("ricavi_totali", 0)
    fatture = storico.get("fatture_emesse", [])
    mese = date.today().month

    alert_soglie = controlla_soglie(ricavi)
    alert_bollo = controlla_bollo(fatture)
    proiezione = proiezione_annuale(ricavi, mese)

    risultato = {
        "anno": anno,
        "ricavi_totali": ricavi,
        "num_fatture": len(fatture),
        "proiezione": proiezione,
        "alert_soglie": alert_soglie,
        "alert_bollo": alert_bollo,
        "totale_alert": len(alert_soglie) + len(alert_bollo),
        "controllato_il": date.today().isoformat(),
    }

    output = settings.CONTEXT_DIR / f"compliance_{anno}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(risultato, f, indent=2, ensure_ascii=False)

    if alert_soglie:
        top = alert_soglie[-1]
        registra_evento(anno, "compliance_alert", f"Soglia {top['livello']}: {top['messaggio']}")
        logger.warning("ALERT %s: %s (ricavi: €%.2f)", top["livello"], top["messaggio"], ricavi)
    else:
        logger.info("Compliance OK: ricavi €%.2f, proiezione €%.2f", ricavi, proiezione.get("proiezione_annuale", 0))

    return risultato


if __name__ == "__main__":
    r = controlla_compliance()
    print(json.dumps(r, indent=2, ensure_ascii=False))

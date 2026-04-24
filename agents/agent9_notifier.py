"""
Agent9 — Notifier

Invia notifiche via Telegram (per ora), SMS e email (futuro).
Legge alert da context/ e li recapita all'utente.

Output: data/notifiche/YYYY-MM-DD.json
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings

LOGS_DIR = settings.LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent9.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent9")


def invia_telegram(messaggio: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.warning("Telegram non configurato, messaggio stampato a console")
        print(f"\n📢 NOTIFICA: {messaggio}\n")
        return False

    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": messaggio, "parse_mode": "Markdown"})
        if r.status_code == 200:
            logger.info("Telegram inviato: %s", messaggio[:80])
            return True
        logger.error("Telegram errore %d: %s", r.status_code, r.text)
    except Exception as e:
        logger.error("Telegram fallito: %s", e)
    return False


def notifica(tipo: str, messaggio: str, livello: str = "info"):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tipo": tipo,
        "livello": livello,
        "messaggio": messaggio,
        "canale": "telegram",
        "inviato": False,
    }

    emoji = {"info": "ℹ️", "warning": "⚠️", "alert": "🔔", "critical": "🚨",
             "danger": "❗", "emergency": "🆘"}.get(livello, "📌")

    testo = f"{emoji} *FiscalAI — {tipo}*\n\n{messaggio}"
    record["inviato"] = invia_telegram(testo)

    # Log
    log_file = settings.DATA_NOTIFICHE / f"{date.today().isoformat()}.json"
    existing = []
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing.append(record)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return record


def notifica_compliance(compliance: dict):
    for alert in compliance.get("alert_soglie", []):
        notifica("Soglia Ricavi", alert["messaggio"], alert["livello"])
    for alert in compliance.get("alert_bollo", []):
        notifica("Bollo Virtuale", alert["messaggio"], alert["livello"])


def notifica_fattura(fattura: dict):
    msg = (f"Fattura n. {fattura['numero']} emessa\n"
           f"Cliente: {fattura['cliente']}\n"
           f"Importo: €{fattura['importo']:.2f}\n"
           f"Bollo: {'SI' if fattura.get('bollo_virtuale') else 'NO'}")
    notifica("Fattura Emessa", msg, "info")


def notifica_scadenza(scadenza: dict):
    msg = (f"Scadenza: {scadenza['description']}\n"
           f"Data: {scadenza['date']}\n"
           f"Importo: €{scadenza.get('importo', 'da calcolare')}")
    notifica("Scadenza Fiscale", msg, "warning")


if __name__ == "__main__":
    notifica("Test", "FiscalAI e' operativo. Notifiche attive.", "info")

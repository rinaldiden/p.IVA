"""
FiscalAI — Configurazione centralizzata

Tutti gli agenti importano da qui.
I dati fiscali vengono caricati dai JSON in shared/.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
SHARED_DIR = BASE_DIR / "shared"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CONTEXT_DIR = BASE_DIR / "context"

# Sottodirectory dati
DATA_CONTRIBUENTE = DATA_DIR / "contribuente"
DATA_FATTURE = DATA_DIR / "fatture"
DATA_F24 = DATA_DIR / "f24"
DATA_DICHIARAZIONI = DATA_DIR / "dichiarazioni"
DATA_TRANSAZIONI = DATA_DIR / "transazioni"
DATA_NOTIFICHE = DATA_DIR / "notifiche"

for d in [DATA_CONTRIBUENTE, DATA_FATTURE, DATA_F24, DATA_DICHIARAZIONI,
          DATA_TRANSAZIONI, DATA_NOTIFICHE, LOGS_DIR, CONTEXT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Dati fiscali da shared/
# ---------------------------------------------------------------------------
def _load_json(name: str) -> dict:
    with open(SHARED_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)

ATECO_COEFFICIENTS = _load_json("ateco_coefficients.json")
TAX_CALENDAR = _load_json("tax_calendar.json")
F24_TAX_CODES = _load_json("f24_tax_codes.json")
F24_TEMPLATE = _load_json("f24_template.json")

# ---------------------------------------------------------------------------
# INPS 2026 — dati ufficiali Circolare 14/2026
# ---------------------------------------------------------------------------
INPS = {
    "gestione_separata": {
        "aliquota": 0.2607,
        "minimale": 18808,
        "massimale": 122295,
    },
    "artigiani": {
        "aliquota": 0.24,
        "aliquota_oltre_fascia": 0.25,
        "contributo_fisso": 4521.36,
        "contributo_fisso_ridotto_35": 2938.88,
        "minimale": 18808,
        "soglia_prima_fascia": 56224,
        "riduzione_forfettari": 0.35,
    },
    "commercianti": {
        "aliquota": 0.2448,
        "aliquota_oltre_fascia": 0.2548,
        "contributo_fisso": 4611.64,
        "contributo_fisso_ridotto_35": 2997.57,
        "minimale": 18808,
        "soglia_prima_fascia": 56224,
        "riduzione_forfettari": 0.35,
    },
}

# ---------------------------------------------------------------------------
# Regime forfettario
# ---------------------------------------------------------------------------
REGIME = {
    "soglia_ricavi": 85000,
    "soglia_uscita_immediata": 100000,
    "aliquota_ordinaria": 0.15,
    "aliquota_agevolata": 0.05,
    "anni_agevolazione": 5,
    "soglia_acconti_minima": 51.65,
    "maggiorazione_differimento": 0.004,  # 0,40%
    "bollo_virtuale_soglia": 77.47,
    "bollo_virtuale_importo": 2.00,
}

# ---------------------------------------------------------------------------
# Fattura elettronica forfettario
# ---------------------------------------------------------------------------
FATTURA = {
    "regime_fiscale": "RF19",
    "natura_operazione": "N2.2",
    "formato": "FPA12",  # FatturaPA v1.2.2
    "dicitura_obbligatoria": (
        "Operazione effettuata ai sensi dell'art. 1, commi 54-89, "
        "Legge n. 190/2014 - Regime forfettario"
    ),
}

# ---------------------------------------------------------------------------
# Soglie alert compliance (Agent4)
# ---------------------------------------------------------------------------
SOGLIE_ALERT = [
    {"soglia": 70000, "livello": "info", "messaggio": "Stai andando bene, tieni d'occhio la soglia"},
    {"soglia": 80000, "livello": "warning", "messaggio": "Ti avvicini — se superi 85k l'anno prossimo passi al regime ordinario"},
    {"soglia": 84000, "livello": "alert", "messaggio": "ATTENZIONE — valuta se rinviare fatture al prossimo anno"},
    {"soglia": 85000, "livello": "critical", "messaggio": "Hai superato la soglia — dal 1 gennaio prossimo sei in regime ordinario"},
    {"soglia": 95000, "livello": "danger", "messaggio": "PERICOLO — se arrivi a 100k esci SUBITO dal forfettario con IVA retroattiva"},
    {"soglia": 100000, "livello": "emergency", "messaggio": "SUPERAMENTO CRITICO — uscita immediata, IVA retroattiva da oggi"},
]

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

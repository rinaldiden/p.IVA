"""Explainer — natural language explanations via Claude API."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import ATECOSuggestion, ProfiloContribuente, SimulationResult

SYSTEM_PROMPT = (
    "Sei il consulente fiscale di FiscalAI. Spieghi il regime forfettario "
    "italiano in modo semplice, diretto e concreto. Usi numeri reali, "
    "eviti il burocratese, parli in italiano, tratti l'utente come un adulto "
    "intelligente che vuole capire cosa paga e perché. Sei preciso sui numeri "
    "(sempre con 2 decimali e simbolo €) e sulle scadenze."
)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1000

_ATECO_FILE = Path(__file__).resolve().parent.parent.parent / "shared" / "ateco_coefficients.json"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def _get_client():
    """Lazy import to avoid hard dependency when testing."""
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _call_claude(prompt: str) -> str:
    try:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Claude API call failed: %s", e)
        return (
            "[Spiegazione non disponibile — API Claude non raggiungibile. "
            "I calcoli fiscali sono comunque validi e corretti.]"
        )


def _load_ateco_catalog() -> dict[str, Any]:
    with open(_ATECO_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["coefficients"]


def explain_simulation(sim: SimulationResult) -> str:
    """Generate a personalized explanation of the simulation results."""
    sim_data = {
        "anno": sim.anno_fiscale,
        "primo_anno": sim.profilo.primo_anno,
        "ricavi_totali": str(sim.ricavi_totali),
        "reddito_imponibile": str(sim.reddito_imponibile),
        "aliquota": str(sim.aliquota),
        "imposta_sostitutiva": str(sim.imposta_sostitutiva),
        "contributo_inps": str(sim.contributo_inps),
        "totale_da_pagare": str(sim.imposta_sostitutiva + sim.contributo_inps),
        "rata_mensile": str(sim.rata_mensile_da_accantonare),
        "risparmio_vs_ordinario": str(sim.risparmio_vs_ordinario),
        "gestione_inps": sim.profilo.gestione_inps,
        "scadenze": [
            {"data": s.data, "descrizione": s.descrizione, "importo": str(s.importo)}
            for s in sim.scadenze_anno_corrente
        ],
    }

    prompt = (
        f"Ecco i risultati della simulazione fiscale:\n"
        f"{json.dumps(sim_data, indent=2, cls=_DecimalEncoder)}\n\n"
        f"Spiega in modo personalizzato:\n"
        f"1. Importo annuale totale e rata mensile da accantonare\n"
        f"2. Scadenze principali con date e importi\n"
        f"3. Tre cose da fare nel regime forfettario\n"
        f"4. Tre cose da NON fare nel regime forfettario"
    )

    return _call_claude(prompt)


def suggest_ateco(descrizione: str) -> list[ATECOSuggestion]:
    """Suggest top 3 ATECO codes for the given activity description."""
    catalogo = _load_ateco_catalog()
    catalogo_str = json.dumps(catalogo, indent=2, ensure_ascii=False)

    prompt = (
        f"L'utente descrive la sua attività così: \"{descrizione}\"\n\n"
        f"Ecco il catalogo ATECO disponibile:\n{catalogo_str}\n\n"
        f"Rispondi SOLO con un JSON array di 3 suggerimenti, ordinati per rilevanza:\n"
        f'[{{"codice": "XX.XX.XX", "descrizione": "...", "coefficiente": "0.XX", '
        f'"motivazione": "..."}}]\n'
        f"Nessun altro testo, solo il JSON."
    )

    response = _call_claude(prompt)

    # Parse JSON from response
    try:
        # Handle possible markdown code blocks
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        suggestions = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []

    return [
        ATECOSuggestion(
            codice=s["codice"],
            descrizione=s["descrizione"],
            coefficiente=Decimal(s["coefficiente"]),
            motivazione=s["motivazione"],
        )
        for s in suggestions[:3]
    ]


def explain_inps_options(attivita: str) -> str:
    """Explain the 3 INPS management types for the given activity."""
    prompt = (
        f"L'utente svolge questa attività: \"{attivita}\"\n\n"
        f"Spiega le 3 gestioni INPS possibili per un forfettario:\n"
        f"1. Gestione separata\n"
        f"2. Artigiani\n"
        f"3. Commercianti\n\n"
        f"Per ciascuna indica:\n"
        f"- Chi deve iscriversi\n"
        f"- Importi approssimativi per 30.000€ di reddito imponibile (anno 2024)\n"
        f"- Pro e contro\n"
        f"- Se è disponibile la riduzione 35%\n\n"
        f"Raccomanda quella più adatta all'attività descritta."
    )

    return _call_claude(prompt)


def answer_question(
    domanda: str,
    profilo: ProfiloContribuente | None = None,
) -> str:
    """Answer a free-form question with optional profile context."""
    context = ""
    if profilo:
        context = (
            f"\nContesto contribuente:\n"
            f"- ATECO: {profilo.ateco_principale}\n"
            f"- Gestione INPS: {profilo.gestione_inps}\n"
            f"- Aliquota: {'5%' if profilo.regime_agevolato else '15%'}\n"
            f"- Primo anno: {'Sì' if profilo.primo_anno else 'No'}\n"
        )

    prompt = f"{domanda}{context}"
    return _call_claude(prompt)

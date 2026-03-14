"""LLM-based normative text parser — extracts parameters via Claude API."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

from .models import ParameterChange, RelevanceCheck

SYSTEM_PROMPT = (
    "Sei un esperto di normativa fiscale italiana, specializzato nel regime "
    "forfettario (L. 190/2014). Analizzi testi normativi ed estrai parametri "
    "numerici precisi. Rispondi SEMPRE in JSON valido. Non aggiungere testo "
    "fuori dal JSON."
)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000

# Parameters we monitor
MONITORED_PARAMETERS = [
    "coefficienti di redditività ATECO",
    "aliquota INPS gestione separata",
    "contributo fisso INPS artigiani",
    "contributo fisso INPS commercianti",
    "minimale/massimale INPS",
    "aliquota eccedenza INPS",
    "soglia ricavi forfettario (attualmente 85.000€)",
    "aliquota imposta sostitutiva (5% agevolata, 15% ordinaria)",
    "durata regime agevolato (5 anni)",
    "soglia reddito lavoro dipendente causa ostativa (30.000€)",
    "soglia marca da bollo fatture (77,47€)",
    "codici tributo F24",
    "scadenze fiscali",
]


def _get_client():
    """Lazy import to avoid hard dependency when testing."""
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _call_claude(prompt: str) -> str:
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def check_relevance(testo: str) -> RelevanceCheck:
    """Check if a normative document is relevant to our monitored parameters."""
    params_list = "\n".join(f"- {p}" for p in MONITORED_PARAMETERS)

    prompt = (
        f"Questo documento normativo contiene modifiche ai seguenti "
        f"parametri del regime forfettario italiano?\n\n"
        f"{params_list}\n\n"
        f"Documento:\n{testo[:3000]}\n\n"
        f"Se sì, rispondi con:\n"
        f'{{"rilevante": true, "parametri_coinvolti": ["nome1", "nome2"], '
        f'"motivazione": "..."}}\n'
        f"Se nessun parametro cambia:\n"
        f'{{"rilevante": false, "motivazione": "..."}}'
    )

    response = _call_claude(prompt)
    try:
        data = _parse_json_response(response)
    except (json.JSONDecodeError, IndexError):
        return RelevanceCheck(rilevante=False, motivazione="Parse error")

    return RelevanceCheck(
        rilevante=data.get("rilevante", False),
        parametri_coinvolti=data.get("parametri_coinvolti", []),
        motivazione=data.get("motivazione", ""),
    )


def extract_parameters(
    testo: str,
    valori_attuali: dict[str, str],
) -> list[ParameterChange]:
    """Extract updated parameter values from a normative text."""
    attuali_str = json.dumps(valori_attuali, indent=2, ensure_ascii=False)

    prompt = (
        f"Dal seguente testo normativo, estrai i valori aggiornati per i "
        f"parametri del regime forfettario.\n\n"
        f"Valori attuali nel nostro sistema:\n{attuali_str}\n\n"
        f"Testo normativo:\n{testo[:4000]}\n\n"
        f"Per ogni parametro che cambia, fornisci un JSON array:\n"
        f"[{{\n"
        f'  "nome_parametro": "es. inps_rates.2025.gestione_separata.aliquota",\n'
        f'  "file_destinazione": "es. shared/inps_rates.json",\n'
        f'  "valore_precedente": "0.2607",\n'
        f'  "valore_nuovo": "0.2650",\n'
        f'  "data_efficacia": "2025-01-01",\n'
        f'  "norma_riferimento": "es. L. di Bilancio 2025 art. X c. Y",\n'
        f'  "certezza": "alta|media|bassa",\n'
        f'  "url_fonte": ""\n'
        f"}}]\n"
        f"Se nessun parametro cambia, rispondi con un array vuoto: []"
    )

    response = _call_claude(prompt)
    try:
        data = _parse_json_response(response)
    except (json.JSONDecodeError, IndexError):
        return []

    if not isinstance(data, list):
        return []

    changes: list[ParameterChange] = []
    for item in data:
        try:
            efficacia = date.fromisoformat(item["data_efficacia"])
        except (KeyError, ValueError):
            efficacia = date.today()

        changes.append(ParameterChange(
            nome_parametro=item.get("nome_parametro", ""),
            file_destinazione=item.get("file_destinazione", ""),
            valore_precedente=item.get("valore_precedente", ""),
            valore_nuovo=item.get("valore_nuovo", ""),
            data_efficacia=efficacia,
            norma_riferimento=item.get("norma_riferimento", ""),
            certezza=item.get("certezza", "bassa"),
            url_fonte=item.get("url_fonte", ""),
        ))

    return changes


def check_relevance_mock(testo: str, result: RelevanceCheck) -> RelevanceCheck:
    """For testing: return a predetermined result."""
    return result


def extract_parameters_mock(
    testo: str,
    valori_attuali: dict[str, str],
    result: list[ParameterChange],
) -> list[ParameterChange]:
    """For testing: return predetermined parameter changes."""
    return result

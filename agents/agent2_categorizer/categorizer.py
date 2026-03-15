"""Agent2 — Categorizer (stub — not yet implemented)

Classifica transazioni per tipo e per codice ATECO (supporto multi-ATECO).
Archivia spese per documentazione gestionale.
Tiene il contatore ricavi aggiornato in tempo reale, separato per ATECO.
Monitora andamento fatturazione e alimenta Agent4 con trend e proiezione annuale.
"""

from typing import Any, Dict, Optional


def categorize(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """Classifica una transazione associandola al codice ATECO corretto.

    Args:
        transaction: Transazione normalizzata da Agent1.

    Returns:
        Transazione arricchita con categoria e codice ATECO.
    """
    # stub — not yet implemented
    return {
        "status": "stub",
        "transaction": transaction,
        "category": None,
        "ateco_code": None,
        "message": "Agent2 Categorizer not yet implemented",
    }


def get_revenue_counter() -> Dict[str, Any]:
    """Restituisce il contatore ricavi corrente, separato per ATECO e totale.

    Returns:
        Contatori ricavi per ATECO e aggregato con proiezione annuale.
    """
    # stub — not yet implemented
    return {
        "status": "stub",
        "by_ateco": {},
        "total": 0.0,
        "projection": None,
        "message": "Revenue counter not yet implemented",
    }

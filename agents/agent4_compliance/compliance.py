"""Agent4 — Compliance Checker (stub — not yet implemented)

Monitora andamento fatturazione con proiezione annuale (aggregato multi-ATECO).
Gestisce soglie ricavi (70k, 80k, 84k, 85k) per il regime forfettario.
Controlla cause ostative e verifica esclusioni.
Segnala necessita visto di conformita per crediti > 5.000 EUR.

Nota: la soglia 85.000 EUR e l'unica rilevante per uscita dal forfettario.
Il superamento comporta uscita dall'anno fiscale SUCCESSIVO, mai in corso d'anno.
"""

from typing import Any, Dict, Optional


def check_compliance(revenue_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Verifica compliance del contribuente rispetto al regime forfettario.

    Args:
        revenue_data: Dati ricavi e trend da Agent2 (per ATECO e aggregati).

    Returns:
        Stato compliance con eventuali alert e proiezione annuale.
    """
    # stub — not yet implemented
    return {
        "status": "stub",
        "alerts": [],
        "threshold_breached": None,
        "projection": None,
        "cause_ostative": [],
        "message": "Agent4 Compliance Checker not yet implemented",
    }


def check_tax_credit_visa(credit_amount: float) -> Dict[str, Any]:
    """Verifica se serve visto di conformita per compensazione crediti in F24.

    Args:
        credit_amount: Importo del credito d'imposta.

    Returns:
        Esito verifica con indicazione se serve visto di conformita.
    """
    # stub — not yet implemented
    return {
        "status": "stub",
        "requires_visa": credit_amount > 5000.0 if credit_amount else None,
        "message": "Tax credit visa check not yet implemented",
    }

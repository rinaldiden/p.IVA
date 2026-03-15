"""Agent9 — Notifier (stub — not yet implemented)

Gestisce tutte le notifiche del sistema verso l'utente:
- SMS + email 7 giorni prima di ogni scadenza fiscale
- Alert da tutti gli agenti (SDI, compliance, consent PSD2, ecc.)
- Priorita: Informativa, Normale, Alta, Critica
- Canali: SMS (Twilio), Email (SendGrid), Push (app mobile)
- Retry automatico per notifiche critiche (ogni 4h fino a conferma lettura)
"""

from typing import Any, Dict, List, Optional


def notify(
    message: str,
    priority: str = "normal",
    channels: Optional[List[str]] = None,
    source_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Invia una notifica all'utente sui canali configurati.

    Args:
        message: Testo della notifica.
        priority: Livello di priorita ("info", "normal", "high", "critical").
        channels: Canali specifici da usare. Se None, dedotti dalla priorita.
        source_agent: Agente che ha generato la notifica.

    Returns:
        Esito dell'invio con stato per ciascun canale.
    """
    # stub — not yet implemented
    return {
        "status": "stub",
        "message": message,
        "priority": priority,
        "channels": channels or [],
        "source_agent": source_agent,
        "delivered": False,
        "detail": "Agent9 Notifier not yet implemented",
    }

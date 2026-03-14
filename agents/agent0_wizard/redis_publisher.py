"""Redis Streams publisher for Agent0 onboarding events."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import redis

from .models import ProfiloContribuente, SimulationResult

STREAM = "fiscalai:agent0:events"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


class Agent0RedisPublisher:
    def __init__(self, redis_url: str | None = None) -> None:
        url = redis_url or os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        self._redis = redis.Redis.from_url(url, decode_responses=True)

    def publish_onboarding_complete(
        self,
        profilo: ProfiloContribuente,
        simulation: SimulationResult | None = None,
        correlation_id: str | None = None,
    ) -> str:
        payload = {
            "contribuente_id": profilo.contribuente_id,
            "nome": profilo.nome,
            "cognome": profilo.cognome,
            "codice_fiscale": profilo.codice_fiscale,
            "ateco_principale": profilo.ateco_principale,
            "ateco_secondari": profilo.ateco_secondari,
            "gestione_inps": profilo.gestione_inps,
            "regime_agevolato": profilo.regime_agevolato,
            "primo_anno": profilo.primo_anno,
            "rivalsa_inps_4": profilo.rivalsa_inps_4,
            "stato": profilo.stato,
        }

        if simulation:
            payload["simulation"] = {
                "imposta_sostitutiva": str(simulation.imposta_sostitutiva),
                "contributo_inps": str(simulation.contributo_inps),
                "rata_mensile": str(simulation.rata_mensile_da_accantonare),
            }

        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": "agent0_wizard",
            "contribuente_id": profilo.contribuente_id,
            "event_type": "onboarding_complete",
            "payload": json.dumps(payload, cls=_DecimalEncoder),
            "correlation_id": correlation_id or str(uuid.uuid4()),
        }
        return self._redis.xadd(STREAM, event)

    def close(self) -> None:
        self._redis.close()

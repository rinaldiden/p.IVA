"""Redis Streams publisher for Agent8 invoicing events."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import redis

STREAM = "fiscalai:agent8:events"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


class Agent8RedisPublisher:
    """Publishes invoicing events to Redis Streams."""

    def __init__(self, redis_url: str | None = None) -> None:
        url = redis_url or os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        self._redis = redis.Redis.from_url(url, decode_responses=True)

    def publish_invoice_sent(
        self,
        contribuente_id: str,
        fattura_numero: str,
        importo: str,
        ricavo_netto: str,
        correlation_id: str | None = None,
    ) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": "agent8_invoicing",
            "contribuente_id": contribuente_id,
            "event_type": "invoice_sent",
            "payload": json.dumps({
                "fattura_numero": fattura_numero,
                "importo": importo,
                "ricavo_netto": ricavo_netto,
            }),
            "correlation_id": correlation_id or str(uuid.uuid4()),
        }
        return self._redis.xadd(STREAM, event)

    def publish_sdi_error(
        self,
        contribuente_id: str,
        fattura_numero: str,
        codice_errore: str,
        correlation_id: str | None = None,
    ) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": "agent8_invoicing",
            "contribuente_id": contribuente_id,
            "event_type": "invoice_sdi_error",
            "payload": json.dumps({
                "fattura_numero": fattura_numero,
                "codice_errore": codice_errore,
            }),
            "correlation_id": correlation_id or str(uuid.uuid4()),
        }
        return self._redis.xadd(STREAM, event)

    def close(self) -> None:
        self._redis.close()

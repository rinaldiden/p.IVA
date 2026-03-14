"""Redis Streams publisher for Agent10 NormativeWatcher events."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis

from .models import NormativeUpdate, ParameterChange

STREAM = "fiscalai:agent10:events"


class Agent10RedisPublisher:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        self._redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def publish_normative_update(
        self,
        update: NormativeUpdate,
        correlation_id: str | None = None,
    ) -> str:
        for change in update.parametri_modificati:
            event = {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_id": "agent10_normative",
                "contribuente_id": "_system",
                "event_type": "normative_update_applied",
                "payload": json.dumps({
                    "parametro": change.nome_parametro,
                    "valore_precedente": change.valore_precedente,
                    "valore_nuovo": change.valore_nuovo,
                    "data_efficacia": change.data_efficacia.isoformat(),
                    "norma": change.norma_riferimento,
                    "fonte_url": change.url_fonte or update.documento_url,
                }),
                "correlation_id": correlation_id or str(uuid.uuid4()),
            }
            self._redis.xadd(STREAM, event)
        return update.update_id

    def publish_review_needed(
        self,
        change: ParameterChange,
        update: NormativeUpdate,
    ) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "agent10_normative",
            "contribuente_id": "_system",
            "event_type": "review_needed",
            "payload": json.dumps({
                "parametro": change.nome_parametro,
                "valore_precedente": change.valore_precedente,
                "valore_nuovo": change.valore_nuovo,
                "certezza": change.certezza,
                "norma": change.norma_riferimento,
            }),
            "correlation_id": str(uuid.uuid4()),
        }
        return self._redis.xadd(STREAM, event)

    def close(self) -> None:
        self._redis.close()

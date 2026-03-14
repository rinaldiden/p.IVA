"""Redis Streams publisher for Agent3b validation events."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import redis

STREAM = "fiscalai:agent3b:events"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


class Agent3bRedisPublisher:
    """Publishes validation results to Redis Streams."""

    def __init__(self, redis_url: str | None = None) -> None:
        url = redis_url or os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        self._redis = redis.Redis.from_url(url, decode_responses=True)

    def publish_validation_result(
        self,
        contribuente_id: str,
        blocco: bool,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": "agent3b_validator",
            "contribuente_id": contribuente_id,
            "event_type": "validation_result",
            "blocco": str(blocco).lower(),
            "payload": json.dumps(payload, cls=_DecimalEncoder),
            "correlation_id": correlation_id or str(uuid.uuid4()),
        }
        return self._redis.xadd(STREAM, event)

    def close(self) -> None:
        self._redis.close()

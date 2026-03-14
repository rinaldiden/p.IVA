"""Redis Streams client for Vault events."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import redis


VAULT_STREAM = "fiscalai:vault:events"


class VaultRedisClient:
    """Publishes vault events to Redis Streams."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        self._redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def publish_event(
        self,
        event_type: str,
        agent_id: str,
        credential_type: str,
        credential_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Publish an event to the vault Redis stream.

        Returns:
            The Redis stream message ID.
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": agent_id,
            "event_type": event_type,
            "credential_type": credential_type,
            "credential_id": credential_id or "",
            "details": json.dumps(details or {}),
        }

        return self._redis.xadd(VAULT_STREAM, event)

    def close(self) -> None:
        self._redis.close()

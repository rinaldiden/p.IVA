"""AgentPublisher — publishes events to Redis Streams."""

from __future__ import annotations

import os
from typing import Any

import redis

from .models import AgentEvent, stream_for_agent

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class AgentPublisher:
    """Publishes events to the agent's dedicated Redis Stream."""

    def __init__(
        self,
        agent_id: str,
        redis_url: str | None = None,
    ) -> None:
        redis_url = redis_url or os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        self._agent_id = agent_id
        self._stream = stream_for_agent(agent_id)
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def stream(self) -> str:
        return self._stream

    def publish(
        self,
        event_type: str,
        contribuente_id: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> str:
        """Publish an event and return its event_id."""
        event = AgentEvent.create(
            agent_id=self._agent_id,
            event_type=event_type,
            contribuente_id=contribuente_id,
            payload=payload,
            correlation_id=correlation_id,
        )
        self._redis.xadd(self._stream, event.to_redis())
        return event.event_id

    def publish_event(self, event: AgentEvent) -> str:
        """Publish a pre-built AgentEvent."""
        self._redis.xadd(self._stream, event.to_redis())
        return event.event_id

    def close(self) -> None:
        self._redis.close()

    def __enter__(self) -> AgentPublisher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

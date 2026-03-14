"""AgentConsumer — consumes events from Redis Streams with consumer groups."""

from __future__ import annotations

import logging
from typing import Any, Callable

import redis

from .models import AgentEvent

logger = logging.getLogger(__name__)


class AgentConsumer:
    """Consumes events from one or more Redis Streams using consumer groups.

    Each agent_id forms a consumer group. Within a group, messages are
    delivered to exactly one consumer (exactly-once within the group).
    ACK happens only after the handler completes successfully.
    """

    def __init__(
        self,
        agent_id: str,
        redis_url: str = "redis://localhost:6379/0",
        streams_to_listen: list[str] | None = None,
        consumer_name: str | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._consumer_name = consumer_name or f"{agent_id}-1"
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._streams = streams_to_listen or []
        self._running = False

        # Ensure consumer groups exist
        for stream in self._streams:
            self._ensure_group(stream)

    def _ensure_group(self, stream: str) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            self._redis.xgroup_create(
                stream, self._agent_id, id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def consume(
        self,
        handler: Callable[[AgentEvent], None],
        block_ms: int = 1000,
        max_iterations: int | None = None,
    ) -> None:
        """Start consuming events.

        Calls handler(AgentEvent) for each message.
        ACK only after handler completes without exception.
        If handler raises, message stays in pending (will be redelivered).

        Args:
            handler: Callback for each event.
            block_ms: How long to block waiting for new messages.
            max_iterations: Stop after N iterations (None = run forever).
        """
        self._running = True
        iterations = 0

        # Build stream dict: {stream_name: ">"} means "new messages for this group"
        streams_dict = {s: ">" for s in self._streams}

        while self._running:
            if max_iterations is not None:
                if iterations >= max_iterations:
                    break
                iterations += 1

            try:
                results = self._redis.xreadgroup(
                    self._agent_id,
                    self._consumer_name,
                    streams_dict,
                    count=10,
                    block=block_ms,
                )
            except redis.ConnectionError:
                logger.error("Redis connection lost, stopping consumer")
                break

            if not results:
                continue

            for stream_name, messages in results:
                for stream_id, data in messages:
                    event = AgentEvent.from_redis(stream_id, data)
                    try:
                        handler(event)
                        # ACK only on success
                        self._redis.xack(stream_name, self._agent_id, stream_id)
                    except Exception:
                        logger.exception(
                            "Handler failed for event %s on stream %s, "
                            "message will remain pending",
                            event.event_id,
                            stream_name,
                        )

    def consume_once(
        self,
        handler: Callable[[AgentEvent], None],
        block_ms: int = 100,
    ) -> int:
        """Consume available messages once (non-blocking). Returns count processed."""
        streams_dict = {s: ">" for s in self._streams}
        processed = 0

        try:
            results = self._redis.xreadgroup(
                self._agent_id,
                self._consumer_name,
                streams_dict,
                count=100,
                block=block_ms,
            )
        except redis.ConnectionError:
            return 0

        if not results:
            return 0

        for stream_name, messages in results:
            for stream_id, data in messages:
                event = AgentEvent.from_redis(stream_id, data)
                try:
                    handler(event)
                    self._redis.xack(stream_name, self._agent_id, stream_id)
                    processed += 1
                except Exception:
                    logger.exception(
                        "Handler failed for event %s", event.event_id
                    )

        return processed

    def get_pending(self) -> list[AgentEvent]:
        """Return pending (unacknowledged) messages for this consumer."""
        pending: list[AgentEvent] = []

        for stream in self._streams:
            try:
                result = self._redis.xpending_range(
                    stream, self._agent_id, "-", "+", count=100,
                    consumername=self._consumer_name,
                )
            except redis.ResponseError:
                continue

            if not result:
                continue

            # Fetch the actual messages
            msg_ids = [entry["message_id"] for entry in result]
            if msg_ids:
                # XCLAIM to read them
                claimed = self._redis.xclaim(
                    stream,
                    self._agent_id,
                    self._consumer_name,
                    min_idle_time=0,
                    message_ids=msg_ids,
                )
                for stream_id, data in claimed:
                    pending.append(AgentEvent.from_redis(stream_id, data))

        return pending

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self.stop()
        self._redis.close()

    def __enter__(self) -> AgentConsumer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

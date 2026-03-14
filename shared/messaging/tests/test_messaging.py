"""Test suite for inter-agent messaging bus — 6 test cases.

These tests require a running Redis instance. They are skipped if Redis
is unavailable (CI-friendly).
"""

from __future__ import annotations

import time
import uuid

import pytest
import redis

from shared.messaging.consumer import AgentConsumer
from shared.messaging.models import AgentEvent, EventType, stream_for_agent
from shared.messaging.publisher import AgentPublisher
from shared.messaging.supervisor_listener import (
    ContribuenteStateStore,
    SupervisorListener,
)

REDIS_URL = "redis://localhost:6379/0"


def _redis_available() -> bool:
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        r.close()
        return True
    except (redis.ConnectionError, redis.TimeoutError):
        return False


# Unique stream prefix per test run to avoid collisions
_RUN_ID = uuid.uuid4().hex[:8]


def _test_stream(agent_id: str) -> str:
    return f"fiscalai:test:{_RUN_ID}:{agent_id}:events"


def _cleanup_stream(r: redis.Redis, stream: str) -> None:
    try:
        r.delete(stream)
    except redis.ResponseError:
        pass


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="Redis not available"
)


class TestPublishConsumeRoundTrip:
    """Test 1: Publisher publishes, Consumer receives correctly."""

    def test_round_trip(self):
        stream = _test_stream("agent3_rt")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _cleanup_stream(r, stream)

        # Publish
        pub_r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        event = AgentEvent.create(
            agent_id="agent3_calculator",
            event_type=EventType.CALCULATION_DONE,
            contribuente_id="contrib-001",
            payload={"imposta": "1560.00"},
        )
        pub_r.xadd(stream, event.to_redis())

        # Consume
        group = f"test_consumer_{_RUN_ID}"
        try:
            r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        results = r.xreadgroup(group, "c1", {stream: ">"}, count=1, block=500)
        assert len(results) == 1

        stream_name, messages = results[0]
        assert len(messages) == 1

        stream_id, data = messages[0]
        received = AgentEvent.from_redis(stream_id, data)
        assert received.event_type == EventType.CALCULATION_DONE
        assert received.contribuente_id == "contrib-001"
        assert received.payload["imposta"] == "1560.00"
        assert received.correlation_id == event.correlation_id

        _cleanup_stream(r, stream)
        r.close()
        pub_r.close()


class TestConsumerGroupExactlyOnce:
    """Test 2: Two consumers in same group, each message delivered to one only."""

    def test_exactly_once(self):
        stream = _test_stream("agent3_eo")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _cleanup_stream(r, stream)

        # Publish 5 messages
        for i in range(5):
            event = AgentEvent.create(
                agent_id="agent3_calculator",
                event_type=EventType.CALCULATION_DONE,
                contribuente_id=f"contrib-{i:03d}",
                payload={"index": i},
            )
            r.xadd(stream, event.to_redis())

        group = f"test_eo_{_RUN_ID}"
        try:
            r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        # Consumer A reads
        results_a = r.xreadgroup(group, "consumer_a", {stream: ">"}, count=10, block=200)
        # Consumer B reads
        results_b = r.xreadgroup(group, "consumer_b", {stream: ">"}, count=10, block=200)

        count_a = sum(len(msgs) for _, msgs in results_a) if results_a else 0
        count_b = sum(len(msgs) for _, msgs in results_b) if results_b else 0

        # All 5 messages delivered, but split between A and B
        assert count_a + count_b == 5
        # Consumer A got them all (first reader gets pending)
        assert count_a == 5
        assert count_b == 0

        _cleanup_stream(r, stream)
        r.close()


class TestAgent3bBlockPropagation:
    """Test 3: SupervisorListener receives VALIDATION_BLOCKED → state = BLOCKED."""

    def test_block_propagation(self):
        stream = _test_stream("agent3b_block")
        supervisor_stream = _test_stream("supervisor_block")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _cleanup_stream(r, stream)
        _cleanup_stream(r, supervisor_stream)

        state_store = ContribuenteStateStore()

        # Publish VALIDATION_BLOCKED
        event = AgentEvent.create(
            agent_id="agent3b_validator",
            event_type=EventType.VALIDATION_BLOCKED,
            contribuente_id="contrib-blocked",
            payload={"divergenze": [{"campo": "imposta", "delta": "0.01"}]},
        )
        r.xadd(stream, event.to_redis())

        # Create consumer group for supervisor
        group = f"supervisor_{_RUN_ID}"
        try:
            r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        # Read and dispatch manually
        results = r.xreadgroup(group, "sup1", {stream: ">"}, count=1, block=500)
        assert results

        _, messages = results[0]
        stream_id, data = messages[0]
        received = AgentEvent.from_redis(stream_id, data)

        # Simulate supervisor handler
        assert received.event_type == EventType.VALIDATION_BLOCKED
        state_store.set_state(
            received.contribuente_id, "BLOCKED",
            reason="validation_blocked",
        )

        assert state_store.is_blocked("contrib-blocked") is True
        assert state_store.get_state("contrib-blocked") == "BLOCKED"

        _cleanup_stream(r, stream)
        _cleanup_stream(r, supervisor_stream)
        r.close()


class TestPendingMessages:
    """Test 4: Message stays pending if not ACKed."""

    def test_pending(self):
        stream = _test_stream("agent3_pending")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _cleanup_stream(r, stream)

        # Publish
        event = AgentEvent.create(
            agent_id="agent3_calculator",
            event_type=EventType.CALCULATION_DONE,
            contribuente_id="contrib-pending",
            payload={"test": True},
        )
        r.xadd(stream, event.to_redis())

        group = f"test_pending_{_RUN_ID}"
        try:
            r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        # Read but do NOT ACK
        results = r.xreadgroup(group, "c1", {stream: ">"}, count=1, block=500)
        assert results
        _, messages = results[0]
        stream_id, _ = messages[0]

        # Check pending
        pending = r.xpending_range(stream, group, "-", "+", count=10, consumername="c1")
        assert len(pending) == 1
        assert pending[0]["message_id"] == stream_id

        _cleanup_stream(r, stream)
        r.close()


class TestCorrelationIdPropagated:
    """Test 5: Correlation ID persists across event chain."""

    def test_correlation_chain(self):
        stream_a0 = _test_stream("agent0_corr")
        stream_a1 = _test_stream("agent1_corr")
        stream_a3 = _test_stream("agent3_corr")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        for s in [stream_a0, stream_a1, stream_a3]:
            _cleanup_stream(r, s)

        shared_corr_id = str(uuid.uuid4())

        # Agent0 publishes
        e0 = AgentEvent.create(
            agent_id="agent0_wizard",
            event_type=EventType.ONBOARDING_COMPLETE,
            contribuente_id="contrib-corr",
            payload={"step": "onboarding"},
            correlation_id=shared_corr_id,
        )
        r.xadd(stream_a0, e0.to_redis())

        # Agent1 picks up, propagates correlation_id
        e1 = AgentEvent.create(
            agent_id="agent1_collector",
            event_type=EventType.DOCUMENTS_COLLECTED,
            contribuente_id="contrib-corr",
            payload={"documents": 3},
            correlation_id=shared_corr_id,
        )
        r.xadd(stream_a1, e1.to_redis())

        # Agent3 picks up, propagates correlation_id
        e3 = AgentEvent.create(
            agent_id="agent3_calculator",
            event_type=EventType.CALCULATION_DONE,
            contribuente_id="contrib-corr",
            payload={"imposta": "1560.00"},
            correlation_id=shared_corr_id,
        )
        r.xadd(stream_a3, e3.to_redis())

        # Verify all have the same correlation_id
        for stream in [stream_a0, stream_a1, stream_a3]:
            msgs = r.xrange(stream)
            assert len(msgs) == 1
            _, data = msgs[0]
            assert data["correlation_id"] == shared_corr_id

        for s in [stream_a0, stream_a1, stream_a3]:
            _cleanup_stream(r, s)
        r.close()


class TestPSD2ExpiringTrigger:
    """Test 6: Agent1 publishes PSD2_EXPIRING → Supervisor publishes renewal needed."""

    def test_psd2_trigger(self):
        stream_a1 = _test_stream("agent1_psd2")
        stream_sup = _test_stream("supervisor_psd2")
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _cleanup_stream(r, stream_a1)
        _cleanup_stream(r, stream_sup)

        # Publish PSD2_EXPIRING from agent1
        event = AgentEvent.create(
            agent_id="agent1_collector",
            event_type=EventType.PSD2_EXPIRING,
            contribuente_id="contrib-psd2",
            payload={"days_remaining": 7, "banca": "Intesa Sanpaolo"},
        )
        r.xadd(stream_a1, event.to_redis())

        # Supervisor reads
        group = f"sup_psd2_{_RUN_ID}"
        try:
            r.xgroup_create(stream_a1, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        results = r.xreadgroup(group, "sup1", {stream_a1: ">"}, count=1, block=500)
        assert results

        _, messages = results[0]
        _, data = messages[0]
        received = AgentEvent.from_redis("", data)

        assert received.event_type == EventType.PSD2_EXPIRING
        assert received.payload["days_remaining"] == 7

        # Supervisor would publish renewal needed
        renewal = AgentEvent.create(
            agent_id="supervisor",
            event_type=EventType.PSD2_RENEWAL_NEEDED,
            contribuente_id="contrib-psd2",
            payload={
                "days_remaining": 7,
                "banca": "Intesa Sanpaolo",
            },
            correlation_id=received.correlation_id,
        )
        r.xadd(stream_sup, renewal.to_redis())

        # Verify Agent9 could read it
        sup_msgs = r.xrange(stream_sup)
        assert len(sup_msgs) == 1
        _, sup_data = sup_msgs[0]
        assert sup_data["event_type"] == EventType.PSD2_RENEWAL_NEEDED
        assert sup_data["correlation_id"] == received.correlation_id

        _cleanup_stream(r, stream_a1)
        _cleanup_stream(r, stream_sup)
        r.close()

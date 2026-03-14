# Inter-Agent Messaging Bus

Redis Streams-based communication layer for FiscalAI agents.

## Quick start

```python
from shared.messaging import AgentPublisher, AgentConsumer, EventType, AgentEvent

# Publish
with AgentPublisher("agent3_calculator") as pub:
    pub.publish(
        event_type=EventType.CALCULATION_DONE,
        contribuente_id="uuid-here",
        payload={"imposta": "1560.00"},
    )

# Consume
def handler(event: AgentEvent):
    print(f"Received {event.event_type} for {event.contribuente_id}")

with AgentConsumer(
    "agent6_scheduler",
    streams_to_listen=["fiscalai:agent3b:events"],
) as consumer:
    consumer.consume(handler)
```

## Architecture

Each agent publishes to its own stream (`fiscalai:{agent_id}:events`).
Downstream agents subscribe via consumer groups (exactly-once delivery).

The Supervisor listens to **all** streams and handles critical events:
- `VALIDATION_BLOCKED` → block contribuente, notify Agent9
- `PSD2_EXPIRING` → trigger renewal flow
- `THRESHOLD_WARNING` → log + notify
- `COMPLIANCE_FAIL` → set WARNING state

## Blocking protocol

When Agent3b publishes `VALIDATION_BLOCKED`, the Supervisor sets the
contribuente state to `BLOCKED`. All downstream agents (Agent5, Agent6)
must check `supervisor.is_blocked(contribuente_id)` before processing.

## Running tests

```bash
# Requires Redis running on localhost:6379
python -m pytest shared/messaging/tests/ -v
```

## Environment

```
REDIS_URL=redis://localhost:6379/0
```

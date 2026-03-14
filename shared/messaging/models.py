"""Data models for the inter-agent messaging bus."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


class EventType:
    """All event types in the system."""

    # Agent0
    ONBOARDING_COMPLETE = "onboarding_complete"
    SIMULATION_DONE = "simulation_done"

    # Agent1
    DOCUMENTS_COLLECTED = "documents_collected"
    PSD2_EXPIRING = "psd2_expiring"
    PSD2_EXPIRED = "psd2_expired"

    # Agent2
    CATEGORIZATION_DONE = "categorization_done"
    ANOMALY_DETECTED = "anomaly_detected"

    # Agent3
    CALCULATION_DONE = "calculation_done"

    # Agent3b — CRITICAL
    VALIDATION_OK = "validation_ok"
    VALIDATION_BLOCKED = "validation_blocked"

    # Agent4
    THRESHOLD_WARNING = "threshold_warning"
    COMPLIANCE_FAIL = "compliance_fail"

    # Agent5
    DECLARATION_READY = "declaration_ready"
    DECLARATION_SENT = "declaration_sent"
    DECLARATION_ERROR = "declaration_error"

    # Agent6
    PAYMENT_SCHEDULED = "payment_scheduled"

    # Agent8
    INVOICE_SENT = "invoice_sent"
    INVOICE_SDI_ERROR = "invoice_sdi_error"

    # Agent9
    NOTIFICATION_SENT = "notification_sent"

    # Agent10
    NORMATIVE_APPLIED = "normative_applied"
    NORMATIVE_SCHEDULED = "normative_scheduled"
    NORMATIVE_REVIEW_NEEDED = "normative_review_needed"

    # Vault
    CREDENTIAL_EXPIRING = "credential_expiring"
    CREDENTIAL_ROTATED = "credential_rotated"

    # Supervisor
    CONTRIBUENTE_BLOCKED = "contribuente_blocked"
    CONTRIBUENTE_UNBLOCKED = "contribuente_unblocked"
    PSD2_RENEWAL_NEEDED = "psd2_renewal_needed"
    PROFILE_UPDATED = "profile_updated"


# Stream name per agent
AGENT_STREAMS = {
    "agent0_wizard": "fiscalai:agent0:events",
    "agent1_collector": "fiscalai:agent1:events",
    "agent2_categorizer": "fiscalai:agent2:events",
    "agent3_calculator": "fiscalai:agent3:events",
    "agent3b_validator": "fiscalai:agent3b:events",
    "agent4_compliance": "fiscalai:agent4:events",
    "agent5_declaration": "fiscalai:agent5:events",
    "agent6_scheduler": "fiscalai:agent6:events",
    "agent8_invoicing": "fiscalai:agent8:events",
    "agent9_notifier": "fiscalai:agent9:events",
    "agent10_normative": "fiscalai:agent10:events",
    "vault": "fiscalai:vault:events",
    "supervisor": "fiscalai:supervisor:events",
}

ALL_AGENT_STREAMS = list(AGENT_STREAMS.values())


def stream_for_agent(agent_id: str) -> str:
    """Get the stream name for a given agent ID."""
    if agent_id in AGENT_STREAMS:
        return AGENT_STREAMS[agent_id]
    return f"fiscalai:{agent_id}:events"


@dataclass
class AgentEvent:
    """A single event on the bus."""

    event_id: str
    timestamp: str
    agent_id: str
    contribuente_id: str
    event_type: str
    payload: dict
    correlation_id: str

    # Redis stream metadata (set after read)
    stream_id: str = ""

    @classmethod
    def create(
        cls,
        agent_id: str,
        event_type: str,
        contribuente_id: str,
        payload: dict,
        correlation_id: str | None = None,
    ) -> AgentEvent:
        return cls(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=agent_id,
            contribuente_id=contribuente_id,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )

    def to_redis(self) -> dict[str, str]:
        """Serialize for Redis XADD."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "contribuente_id": self.contribuente_id,
            "event_type": self.event_type,
            "payload": json.dumps(self.payload, cls=_DecimalEncoder),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_redis(cls, stream_id: str, data: dict[str, str]) -> AgentEvent:
        """Deserialize from Redis XREAD."""
        payload_raw = data.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except (json.JSONDecodeError, TypeError):
            payload = {"_raw": payload_raw}

        return cls(
            event_id=data.get("event_id", ""),
            timestamp=data.get("timestamp", ""),
            agent_id=data.get("agent_id", ""),
            contribuente_id=data.get("contribuente_id", ""),
            event_type=data.get("event_type", ""),
            payload=payload,
            correlation_id=data.get("correlation_id", ""),
            stream_id=stream_id,
        )

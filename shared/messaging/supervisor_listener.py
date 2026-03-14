"""SupervisorListener — listens to all agent streams and reacts."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .consumer import AgentConsumer
from .models import ALL_AGENT_STREAMS, AgentEvent, EventType, stream_for_agent
from .publisher import AgentPublisher

logger = logging.getLogger(__name__)


class ContribuenteStateStore:
    """In-memory store for contribuente states. Replace with DB in production."""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}  # contribuente_id → state
        self._log: list[dict[str, Any]] = []

    def set_state(self, contribuente_id: str, state: str, reason: str = "") -> None:
        self._states[contribuente_id] = state
        self._log.append({
            "contribuente_id": contribuente_id,
            "state": state,
            "reason": reason,
        })

    def get_state(self, contribuente_id: str) -> str:
        return self._states.get(contribuente_id, "active")

    def is_blocked(self, contribuente_id: str) -> bool:
        return self.get_state(contribuente_id) == "BLOCKED"


class SupervisorListener:
    """Listens to all agent streams and handles critical events.

    Routes:
    - VALIDATION_BLOCKED → block contribuente, notify Agent9
    - PSD2_EXPIRING → publish renewal needed
    - THRESHOLD_WARNING → log + notify
    - COMPLIANCE_FAIL → set WARNING state + notify
    - INVOICE_SDI_ERROR → notify immediately
    - CREDENTIAL_EXPIRING → initiate renewal flow
    """

    def __init__(
        self,
        redis_url: str | None = None,
        state_store: ContribuenteStateStore | None = None,
    ) -> None:
        import os
        redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis_url = redis_url
        self._state = state_store or ContribuenteStateStore()

        # Consumer listens to all agent streams
        self._consumer = AgentConsumer(
            agent_id="supervisor",
            redis_url=redis_url,
            streams_to_listen=ALL_AGENT_STREAMS,
        )

        # Publisher for supervisor decisions
        self._publisher = AgentPublisher(
            agent_id="supervisor",
            redis_url=redis_url,
        )

        # Event handlers
        self._handlers: dict[str, Callable[[AgentEvent], None]] = {
            EventType.VALIDATION_BLOCKED: self._handle_validation_blocked,
            EventType.VALIDATION_OK: self._handle_validation_ok,
            EventType.PSD2_EXPIRING: self._handle_psd2_expiring,
            EventType.PSD2_EXPIRED: self._handle_psd2_expired,
            EventType.THRESHOLD_WARNING: self._handle_threshold_warning,
            EventType.COMPLIANCE_FAIL: self._handle_compliance_fail,
            EventType.INVOICE_SDI_ERROR: self._handle_sdi_error,
            EventType.CREDENTIAL_EXPIRING: self._handle_credential_expiring,
        }

    @property
    def state_store(self) -> ContribuenteStateStore:
        return self._state

    def _dispatch(self, event: AgentEvent) -> None:
        """Route event to the appropriate handler."""
        handler = self._handlers.get(event.event_type)
        if handler:
            logger.info(
                "Supervisor handling %s from %s for %s",
                event.event_type, event.agent_id, event.contribuente_id,
            )
            handler(event)

    # --- Critical: Agent3b validation blocked ---
    def _handle_validation_blocked(self, event: AgentEvent) -> None:
        cid = event.contribuente_id
        self._state.set_state(
            cid, "BLOCKED",
            reason=f"Agent3b validation blocked: {event.payload}",
        )
        self._publisher.publish(
            event_type=EventType.CONTRIBUENTE_BLOCKED,
            contribuente_id=cid,
            payload={
                "reason": "validation_blocked",
                "divergenze": event.payload.get("divergenze", []),
                "source_event_id": event.event_id,
            },
            correlation_id=event.correlation_id,
        )
        logger.warning("Contribuente %s BLOCKED by Agent3b", cid)

    def _handle_validation_ok(self, event: AgentEvent) -> None:
        cid = event.contribuente_id
        if self._state.is_blocked(cid):
            self._state.set_state(cid, "active", reason="Validation passed")
            self._publisher.publish(
                event_type=EventType.CONTRIBUENTE_UNBLOCKED,
                contribuente_id=cid,
                payload={"source_event_id": event.event_id},
                correlation_id=event.correlation_id,
            )

    # --- PSD2 ---
    def _handle_psd2_expiring(self, event: AgentEvent) -> None:
        self._publisher.publish(
            event_type=EventType.PSD2_RENEWAL_NEEDED,
            contribuente_id=event.contribuente_id,
            payload={
                "days_remaining": event.payload.get("days_remaining"),
                "banca": event.payload.get("banca"),
                "source_event_id": event.event_id,
            },
            correlation_id=event.correlation_id,
        )

    def _handle_psd2_expired(self, event: AgentEvent) -> None:
        self._state.set_state(
            event.contribuente_id, "WARNING",
            reason="PSD2 consent expired",
        )
        self._publisher.publish(
            event_type=EventType.PSD2_RENEWAL_NEEDED,
            contribuente_id=event.contribuente_id,
            payload={
                "days_remaining": 0,
                "expired": True,
                "banca": event.payload.get("banca"),
            },
            correlation_id=event.correlation_id,
        )

    # --- Compliance ---
    def _handle_threshold_warning(self, event: AgentEvent) -> None:
        self._publisher.publish(
            event_type=EventType.THRESHOLD_WARNING,
            contribuente_id=event.contribuente_id,
            payload={
                "soglia": event.payload.get("soglia"),
                "ricavi_correnti": event.payload.get("ricavi_correnti"),
                "source_event_id": event.event_id,
            },
            correlation_id=event.correlation_id,
        )

    def _handle_compliance_fail(self, event: AgentEvent) -> None:
        cid = event.contribuente_id
        self._state.set_state(cid, "WARNING", reason="Compliance fail")
        self._publisher.publish(
            event_type=EventType.COMPLIANCE_FAIL,
            contribuente_id=cid,
            payload={
                "reason": event.payload.get("reason"),
                "source_event_id": event.event_id,
            },
            correlation_id=event.correlation_id,
        )

    # --- SDI errors ---
    def _handle_sdi_error(self, event: AgentEvent) -> None:
        self._publisher.publish(
            event_type=EventType.INVOICE_SDI_ERROR,
            contribuente_id=event.contribuente_id,
            payload={
                "codice_errore": event.payload.get("codice_errore"),
                "azione_suggerita": event.payload.get("azione_suggerita"),
                "fattura_id": event.payload.get("fattura_id"),
                "source_event_id": event.event_id,
            },
            correlation_id=event.correlation_id,
        )

    # --- Credential management ---
    def _handle_credential_expiring(self, event: AgentEvent) -> None:
        cred_type = event.payload.get("credential_type", "")
        if cred_type == "PSD2_CONSENT":
            self._publisher.publish(
                event_type=EventType.PSD2_RENEWAL_NEEDED,
                contribuente_id=event.contribuente_id,
                payload={
                    "trigger": "credential_expiring",
                    "credential_type": cred_type,
                },
                correlation_id=event.correlation_id,
            )
        else:
            self._publisher.publish(
                event_type=EventType.CREDENTIAL_EXPIRING,
                contribuente_id=event.contribuente_id,
                payload={
                    "credential_type": cred_type,
                    "source_event_id": event.event_id,
                },
                correlation_id=event.correlation_id,
            )

    def listen(self, max_iterations: int | None = None) -> None:
        """Start listening to all streams."""
        self._consumer.consume(
            handler=self._dispatch,
            block_ms=1000,
            max_iterations=max_iterations,
        )

    def listen_once(self, block_ms: int = 100) -> int:
        """Process available messages once. Returns count processed."""
        return self._consumer.consume_once(
            handler=self._dispatch,
            block_ms=block_ms,
        )

    def close(self) -> None:
        self._consumer.close()
        self._publisher.close()

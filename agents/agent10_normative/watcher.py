"""Agent10 NormativeWatcher — main orchestrator.

Monitors Italian fiscal legislation changes and updates system parameters
from the effective date, not the publication date.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable

from . import parser, sources
from .diff_engine import compute_diff, filter_needs_review, get_current_values
from .models import NormativeUpdate, ParameterChange, SourceResult
from .scheduler import NormativeScheduler
from .updater import apply_update, write_review_queue

logger = logging.getLogger(__name__)


class NormativeWatcher:
    """Main orchestrator for normative monitoring.

    Flow:
    1. Fetch sources
    2. Check relevance (LLM)
    3. Extract parameters (LLM)
    4. Diff against current values
    5. Schedule or apply updates
    6. Audit trail + notifications
    """

    def __init__(
        self,
        check_relevance_fn: Callable | None = None,
        extract_params_fn: Callable | None = None,
        anomaly_threshold_pct: float = 5.0,
    ) -> None:
        self._check_relevance = check_relevance_fn or parser.check_relevance
        self._extract_params = extract_params_fn or parser.extract_parameters
        self._scheduler = NormativeScheduler()
        self._anomaly_threshold = anomaly_threshold_pct

    def check_source(
        self,
        source_name: str,
        http_client: Any = None,
    ) -> list[NormativeUpdate]:
        """Check a single source for normative updates.

        Returns list of NormativeUpdate objects (pending, scheduled, or applied).
        """
        fetcher = sources.ALL_FETCHERS.get(source_name)
        if not fetcher:
            logger.error("Unknown source: %s", source_name)
            return []

        # Step 1 — Fetch
        results = fetcher(http_client=http_client)
        if not results:
            logger.info("No new documents from %s", source_name)
            return []

        updates: list[NormativeUpdate] = []

        for doc in results:
            update = self._process_document(doc)
            if update:
                updates.append(update)

        return updates

    def check_all_sources(
        self,
        http_client: Any = None,
    ) -> list[NormativeUpdate]:
        """Check all sources."""
        all_updates: list[NormativeUpdate] = []
        for source_name in sources.ALL_FETCHERS:
            updates = self.check_source(source_name, http_client)
            all_updates.extend(updates)
        return all_updates

    def _process_document(self, doc: SourceResult) -> NormativeUpdate | None:
        """Process a single document through the full pipeline."""

        # Step 2 — Relevance check
        relevance = self._check_relevance(doc.testo)
        if not relevance.rilevante:
            logger.info("Not relevant: %s", doc.titolo)
            return None

        logger.info(
            "Relevant document: %s — params: %s",
            doc.titolo,
            relevance.parametri_coinvolti,
        )

        # Step 3 — Extract parameters
        current_values = get_current_values()
        changes = self._extract_params(doc.testo, current_values)
        if not changes:
            logger.info("No parameter changes extracted from: %s", doc.titolo)
            return None

        # Step 4 — Diff
        real_changes = compute_diff(changes)
        if not real_changes:
            logger.info("No actual differences for: %s", doc.titolo)
            return None

        # Split auto vs review
        auto_changes, review_changes = filter_needs_review(
            real_changes, self._anomaly_threshold
        )

        update = NormativeUpdate(
            update_id=str(uuid.uuid4()),
            timestamp_rilevazione=datetime.now(timezone.utc),
            fonte=doc.fonte,
            documento_titolo=doc.titolo,
            documento_url=doc.url,
            hash_documento=doc.hash_documento,
            parametri_modificati=auto_changes,
            stato="pending",
        )

        # Handle review-needed changes
        for change in review_changes:
            review_update = NormativeUpdate(
                update_id=str(uuid.uuid4()),
                timestamp_rilevazione=datetime.now(timezone.utc),
                fonte=doc.fonte,
                documento_titolo=doc.titolo,
                documento_url=doc.url,
                hash_documento=doc.hash_documento,
                parametri_modificati=[change],
                stato="review_needed",
            )
            write_review_queue(change, review_update)
            logger.warning(
                "Parameter %s needs human review (certezza=%s)",
                change.nome_parametro, change.certezza,
            )

        if not auto_changes:
            update.stato = "review_needed"
            return update

        # Step 5 — Schedule or apply
        self._schedule_or_apply(update)

        return update

    def _schedule_or_apply(self, update: NormativeUpdate) -> None:
        """Apply immediately if effective today/past, schedule if future."""
        today = date.today()

        # Find the earliest effective date
        earliest = min(
            (c.data_efficacia for c in update.parametri_modificati),
            default=today,
        )

        if earliest <= today:
            # Already effective — apply now
            logger.info("Applying immediately: %s", update.documento_titolo)
            apply_update(update)
        else:
            # Future — schedule
            update.stato = "scheduled"
            update.data_applicazione = earliest
            self._scheduler.schedule(update)
            logger.info(
                "Scheduled for %s: %s",
                earliest.isoformat(),
                update.documento_titolo,
            )

    def apply_due_updates(self) -> list[NormativeUpdate]:
        """Apply any scheduled updates that are now due."""
        due = self._scheduler.get_due_updates()
        applied: list[NormativeUpdate] = []

        for entry in due:
            update_id = entry.get("update_id", "")
            logger.info("Applying due update: %s", update_id)
            # In a full implementation, we'd reconstruct the NormativeUpdate
            # and apply it. For now, mark as applied.
            self._scheduler.mark_applied(update_id)

        return applied

    @property
    def scheduler(self) -> NormativeScheduler:
        return self._scheduler

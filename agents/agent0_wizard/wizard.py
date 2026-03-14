"""Agent0 Wizard — main orchestrator."""

from __future__ import annotations

import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from .models import ProfiloContribuente, SimulationResult
from .onboarding import OnboardingWizard
from .redis_publisher import Agent0RedisPublisher
from .simulator import simulate

logger = logging.getLogger(__name__)


def run_onboarding(
    use_claude: bool = True,
    publish_redis: bool = True,
) -> ProfiloContribuente:
    """Run the full onboarding wizard, persist profile, and publish to Redis."""
    wizard = OnboardingWizard(use_claude=use_claude)
    profilo = wizard.run()

    # Persist to Supervisor store (survives restarts)
    try:
        from agents.supervisor.persistence import SupervisorStore
        store = SupervisorStore()
        store.save_from_agent0(asdict(profilo))
        logger.info("Profile persisted to Supervisor store: %s", profilo.contribuente_id)
    except Exception as e:
        logger.warning("Failed to persist profile to Supervisor: %s", e)

    if publish_redis:
        publisher = Agent0RedisPublisher()
        try:
            publisher.publish_onboarding_complete(
                profilo=profilo,
                simulation=wizard.simulation,
            )
        finally:
            publisher.close()

    return profilo


def run_simulation(
    profilo: ProfiloContribuente,
    ricavi_per_ateco: dict[str, Decimal],
    imposta_anno_prec: Decimal = Decimal("0"),
    anno_fiscale: int | None = None,
) -> SimulationResult:
    """Run a standalone simulation without onboarding."""
    return simulate(
        profilo=profilo,
        ricavi_per_ateco=ricavi_per_ateco,
        imposta_anno_prec=imposta_anno_prec,
        anno_fiscale=anno_fiscale,
    )

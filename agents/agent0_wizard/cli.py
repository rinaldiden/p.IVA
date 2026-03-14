"""CLI interattiva per test immediato di Agent0 Wizard.

Usage:
    python -m agents.agent0_wizard.cli
    python -m agents.agent0_wizard.cli --no-claude   # skip Claude API calls
"""

from __future__ import annotations

import argparse
import sys

from .onboarding import OnboardingWizard


def main() -> None:
    parser = argparse.ArgumentParser(description="FiscalAI Onboarding Wizard")
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Run without Claude API (no ATECO suggestions or explanations)",
    )
    parser.add_argument(
        "--no-redis",
        action="store_true",
        help="Skip Redis publishing",
    )
    args = parser.parse_args()

    use_claude = not args.no_claude

    wizard = OnboardingWizard(use_claude=use_claude)

    try:
        profilo = wizard.run()
    except KeyboardInterrupt:
        print("\n\nOnboarding interrotto.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        sys.exit(1)

    # Publish to Redis
    if not args.no_redis:
        try:
            from .redis_publisher import Agent0RedisPublisher

            publisher = Agent0RedisPublisher()
            publisher.publish_onboarding_complete(
                profilo=profilo,
                simulation=wizard.simulation,
            )
            publisher.close()
            print("\n📡 Evento pubblicato su Redis: fiscalai:agent0:onboarding_complete")
        except Exception as e:
            print(f"\n⚠ Redis non disponibile: {e}")
            print("  Il profilo è stato creato ma l'evento non è stato pubblicato.")

    print("\n🎉 Onboarding completato!")


if __name__ == "__main__":
    main()

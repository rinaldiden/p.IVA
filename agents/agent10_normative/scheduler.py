"""Scheduler — manages periodic checks and future update scheduling."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import NormativeUpdate

logger = logging.getLogger(__name__)

_SCHEDULED_FILE = Path(__file__).resolve().parent / "audit" / "scheduled.jsonl"


class NormativeScheduler:
    """Manages scheduled normative updates.

    For production, this would use APScheduler for cron-like jobs.
    This implementation provides the scheduling logic and persistence,
    with the actual cron handled externally (e.g., systemd timer, cron, APScheduler).
    """

    def __init__(self) -> None:
        self._pending: list[dict[str, Any]] = []
        self._load_scheduled()

    def _load_scheduled(self) -> None:
        """Load scheduled updates from disk."""
        if not _SCHEDULED_FILE.exists():
            return
        with open(_SCHEDULED_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._pending.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    def _save_scheduled(self) -> None:
        """Persist scheduled updates to disk."""
        _SCHEDULED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SCHEDULED_FILE, "w", encoding="utf-8") as f:
            for entry in self._pending:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def schedule(self, update: NormativeUpdate) -> None:
        """Schedule an update for future application."""
        entry = {
            "update_id": update.update_id,
            "data_applicazione": (
                update.data_applicazione.isoformat()
                if update.data_applicazione else ""
            ),
            "documento_titolo": update.documento_titolo,
            "fonte": update.fonte,
            "stato": "scheduled",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "parametri": [
                {
                    "nome": c.nome_parametro,
                    "valore_nuovo": c.valore_nuovo,
                    "data_efficacia": c.data_efficacia.isoformat(),
                }
                for c in update.parametri_modificati
            ],
        }
        self._pending.append(entry)
        self._save_scheduled()
        logger.info(
            "Scheduled update %s for %s",
            update.update_id,
            update.data_applicazione,
        )

    def get_due_updates(self, as_of: date | None = None) -> list[dict[str, Any]]:
        """Return updates that should be applied today or earlier."""
        today = as_of or date.today()
        due: list[dict[str, Any]] = []

        for entry in self._pending:
            if entry.get("stato") != "scheduled":
                continue
            data_str = entry.get("data_applicazione", "")
            if not data_str:
                continue
            try:
                data_app = date.fromisoformat(data_str)
            except ValueError:
                continue
            if data_app <= today:
                due.append(entry)

        return due

    def get_upcoming(self, within_days: int = 30) -> list[dict[str, Any]]:
        """Return updates scheduled within the next N days."""
        from datetime import timedelta
        today = date.today()
        cutoff = today + timedelta(days=within_days)
        upcoming: list[dict[str, Any]] = []

        for entry in self._pending:
            if entry.get("stato") != "scheduled":
                continue
            data_str = entry.get("data_applicazione", "")
            if not data_str:
                continue
            try:
                data_app = date.fromisoformat(data_str)
            except ValueError:
                continue
            if today < data_app <= cutoff:
                upcoming.append(entry)

        return upcoming

    def mark_applied(self, update_id: str) -> None:
        """Mark a scheduled update as applied."""
        for entry in self._pending:
            if entry.get("update_id") == update_id:
                entry["stato"] = "applied"
                entry["applied_at"] = datetime.now(timezone.utc).isoformat()
        self._save_scheduled()

    @property
    def pending_count(self) -> int:
        return sum(
            1 for e in self._pending if e.get("stato") == "scheduled"
        )


# Cron schedule documentation (for APScheduler or external cron)
CRON_SCHEDULE = {
    "check_gazzetta_ufficiale": {"trigger": "cron", "hour": 6, "minute": 0},
    "check_agenzia_entrate": {"trigger": "cron", "hour": 6, "minute": 30},
    "check_inps": {"trigger": "cron", "hour": 7, "minute": 0},
    "check_normattiva": {"trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0},
    "check_pending_updates": {"trigger": "cron", "hour": 0, "minute": 1},
    "check_future_updates_reminder": {"trigger": "cron", "day_of_week": "mon", "hour": 9, "minute": 0},
}

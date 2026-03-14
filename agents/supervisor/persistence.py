"""Supervisor persistence — stores and retrieves contribuente profiles.

Uses JSON file storage as MVP, designed for PostgreSQL migration.
Profiles survive restarts — Agent0 onboarding data is not lost.
"""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path(__file__).resolve().parent / "data"
_PROFILES_FILE = _STORAGE_DIR / "profiles.json"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


class SupervisorStore:
    """File-backed store for contribuente profiles.

    Thread-safe via file locking. Designed as drop-in replacement
    for future PostgreSQL backend.
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._dir = storage_dir or _STORAGE_DIR
        self._file = self._dir / "profiles.json"
        self._dir.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            self._file.write_text("{}\n")

    def _load(self) -> dict[str, Any]:
        with open(self._file, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, Any]) -> None:
        lock_path = self._file.with_suffix(".json.lock")
        with open(lock_path, "w") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, cls=_DecimalEncoder)
                f.write("\n")

    def save_profile(self, contribuente_id: str, profile: dict[str, Any]) -> None:
        """Save or update a contribuente profile."""
        data = self._load()
        profile["_updated_at"] = datetime.now(timezone.utc).isoformat()
        data[contribuente_id] = profile
        self._save(data)
        logger.info("Profile saved: %s", contribuente_id)

    def get_profile(self, contribuente_id: str) -> dict[str, Any] | None:
        """Retrieve a profile by ID. Returns None if not found."""
        data = self._load()
        return data.get(contribuente_id)

    def list_profiles(self) -> list[str]:
        """List all contribuente IDs."""
        data = self._load()
        return [k for k in data.keys() if not k.startswith("_")]

    def delete_profile(self, contribuente_id: str) -> bool:
        """Remove a profile. Returns True if it existed."""
        data = self._load()
        if contribuente_id in data:
            del data[contribuente_id]
            self._save(data)
            return True
        return False

    def save_from_agent0(self, profilo: dict[str, Any]) -> None:
        """Persist an Agent0 onboarding profile.

        Extracts contribuente_id and saves the full profile
        so it survives system restarts.
        """
        cid = profilo.get("contribuente_id", "")
        if not cid:
            raise ValueError("Profile missing contribuente_id")

        self.save_profile(cid, {
            "anagrafica": {
                "nome": profilo.get("nome", ""),
                "cognome": profilo.get("cognome", ""),
                "codice_fiscale": profilo.get("codice_fiscale", ""),
                "comune_residenza": profilo.get("comune_residenza", ""),
            },
            "piva": {
                "data_apertura": profilo.get("data_apertura_piva", ""),
                "ateco_principale": profilo.get("ateco_principale", ""),
                "ateco_secondari": profilo.get("ateco_secondari", []),
            },
            "regime": {
                "tipo": "forfettario",
                "agevolato": profilo.get("regime_agevolato", True),
                "primo_anno": profilo.get("primo_anno", True),
            },
            "inps": {
                "gestione": profilo.get("gestione_inps", "separata"),
                "riduzione_35": profilo.get("riduzione_inps_35", False),
                "rivalsa_4": profilo.get("rivalsa_inps_4", False),
            },
            "stato": profilo.get("stato", "onboarding"),
            "_source": "agent0_wizard",
        })

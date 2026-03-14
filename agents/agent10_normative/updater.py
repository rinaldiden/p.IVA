"""Updater — applies parameter changes to shared/ files and audit trail."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .models import NormativeUpdate, ParameterChange

logger = logging.getLogger(__name__)

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"
_AUDIT_DIR = Path(__file__).resolve().parent / "audit"
_CHANGES_FILE = _AUDIT_DIR / "changes.jsonl"
_REVIEW_QUEUE = _SHARED_DIR / "normative_review_queue.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _set_nested(data: dict, dotted_key: str, value: str) -> None:
    """Set a value in a nested dict using dotted path.
    First segment is file prefix (skipped)."""
    parts = dotted_key.split(".")
    if len(parts) > 1:
        parts = parts[1:]

    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def apply_change(change: ParameterChange) -> bool:
    """Apply a single parameter change to the target shared/ file.
    Returns True if applied successfully."""
    file_path = _SHARED_DIR / Path(change.file_destinazione).name

    if not file_path.exists():
        logger.error("Target file does not exist: %s", file_path)
        return False

    try:
        data = _load_json(file_path)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error("Failed to load %s: %s", file_path, e)
        return False

    _set_nested(data, change.nome_parametro, change.valore_nuovo)
    _save_json(file_path, data)

    logger.info(
        "Applied: %s = %s → %s (effective %s)",
        change.nome_parametro,
        change.valore_precedente,
        change.valore_nuovo,
        change.data_efficacia,
    )
    return True


def apply_update(update: NormativeUpdate) -> bool:
    """Apply all parameter changes in a NormativeUpdate."""
    all_ok = True
    for change in update.parametri_modificati:
        if not apply_change(change):
            all_ok = False

    if all_ok:
        update.stato = "applied"
        update.data_applicazione = date.today()
        _write_audit(update)
        _git_commit(update)
    else:
        logger.error("Some changes failed for update %s", update.update_id)

    return all_ok


def _write_audit(update: NormativeUpdate) -> None:
    """Append to audit/changes.jsonl (append-only)."""
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "update_id": update.update_id,
        "fonte": update.fonte,
        "documento": update.documento_titolo,
        "url": update.documento_url,
        "hash_documento": update.hash_documento,
        "parametri_modificati": [
            {
                "nome": c.nome_parametro,
                "file": c.file_destinazione,
                "vecchio": c.valore_precedente,
                "nuovo": c.valore_nuovo,
                "data_efficacia": c.data_efficacia.isoformat(),
                "norma": c.norma_riferimento,
                "certezza": c.certezza,
            }
            for c in update.parametri_modificati
        ],
        "data_efficacia": (
            update.parametri_modificati[0].data_efficacia.isoformat()
            if update.parametri_modificati else ""
        ),
        "applicato_il": date.today().isoformat(),
    }

    with open(_CHANGES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_review_queue(change: ParameterChange, update: NormativeUpdate) -> None:
    """Add a change to the human review queue."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "update_id": update.update_id,
        "stato": "needs_review",
        "fonte": update.fonte,
        "documento": update.documento_titolo,
        "parametro": change.nome_parametro,
        "valore_precedente": change.valore_precedente,
        "valore_nuovo": change.valore_nuovo,
        "data_efficacia": change.data_efficacia.isoformat(),
        "norma": change.norma_riferimento,
        "certezza": change.certezza,
    }

    with open(_REVIEW_QUEUE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _git_commit(update: NormativeUpdate) -> None:
    """Auto-commit changes if GIT_AUTO_COMMIT=true."""
    if os.environ.get("GIT_AUTO_COMMIT", "").lower() != "true":
        return

    repo_root = _SHARED_DIR.parent

    for change in update.parametri_modificati:
        file_path = _SHARED_DIR / Path(change.file_destinazione).name
        try:
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=repo_root, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            pass

    # Also add audit file
    try:
        subprocess.run(
            ["git", "add", str(_CHANGES_FILE)],
            cwd=repo_root, capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        pass

    change_summaries = []
    for c in update.parametri_modificati:
        change_summaries.append(
            f"{c.nome_parametro} da {c.valore_precedente} a {c.valore_nuovo}"
        )

    msg = (
        f"normative-update: {'; '.join(change_summaries)} "
        f"— efficace dal {update.parametri_modificati[0].data_efficacia.isoformat() if update.parametri_modificati else '?'} "
        f"— fonte: {update.documento_titolo}"
    )

    try:
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_root, capture_output=True, check=True,
        )
        logger.info("Git commit: %s", msg)
    except subprocess.CalledProcessError as e:
        logger.warning("Git commit failed: %s", e.stderr)

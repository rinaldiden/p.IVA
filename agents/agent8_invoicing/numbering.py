"""Progressive invoice numbering — annual, no gaps."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_COUNTER_FILE = _DATA_DIR / "invoice_counter.json"


def _load_counters() -> dict[str, int]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _COUNTER_FILE.exists():
        _COUNTER_FILE.write_text("{}\n")
    with open(_COUNTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_counters(data: dict[str, int]) -> None:
    lock_path = _COUNTER_FILE.with_suffix(".json.lock")
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        with open(_COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def prossimo_numero(anno: int) -> str:
    """Get next invoice number for the year. Format: YYYY/NNN."""
    counters = _load_counters()
    key = str(anno)
    current = counters.get(key, 0) + 1
    counters[key] = current
    _save_counters(counters)
    return f"{anno}/{current:03d}"


def ultimo_numero(anno: int) -> int:
    """Get the last used number for the year (0 if none)."""
    counters = _load_counters()
    return counters.get(str(anno), 0)


def reset_anno(anno: int) -> None:
    """Reset counter for a year (use only in tests)."""
    counters = _load_counters()
    counters[str(anno)] = 0
    _save_counters(counters)

"""Diff engine — compares extracted parameters with current values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import NormativeUpdate, ParameterChange

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_value(data: dict[str, Any], dotted_path: str) -> str | None:
    """Resolve a dotted path like 'inps_rates.2024.gestione_separata.aliquota'
    into the actual value from the JSON data.
    The first segment is the file name (skipped)."""
    parts = dotted_path.split(".")
    # Skip file prefix (e.g. "inps_rates")
    if len(parts) > 1:
        parts = parts[1:]

    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return str(current) if current is not None else None


def get_current_values() -> dict[str, str]:
    """Load all current parameter values from shared/ files.
    Returns a flat dict: {"inps_rates.2024.gestione_separata.aliquota": "0.2607", ...}
    """
    values: dict[str, str] = {}

    # INPS rates
    inps_path = _SHARED_DIR / "inps_rates.json"
    if inps_path.exists():
        data = _load_json(inps_path)
        for anno, year_data in data.items():
            if anno.startswith("_") or not isinstance(year_data, dict):
                continue
            for gestione, params in year_data.items():
                if gestione.startswith("_") or not isinstance(params, dict):
                    continue
                for key, val in params.items():
                    if key.startswith("_"):
                        continue
                    values[f"inps_rates.{anno}.{gestione}.{key}"] = str(val)

    # Forfettario limits
    limits_path = _SHARED_DIR / "forfettario_limits.json"
    if limits_path.exists():
        data = _load_json(limits_path)
        for key, val in data.items():
            if key.startswith("_"):
                continue
            values[f"forfettario_limits.{key}"] = str(val)

    # ATECO coefficients (count only)
    ateco_path = _SHARED_DIR / "ateco_coefficients.json"
    if ateco_path.exists():
        data = _load_json(ateco_path)
        coeffs = data.get("coefficients", {})
        for code, info in coeffs.items():
            if isinstance(info, dict) and "coefficient" in info:
                values[f"ateco_coefficients.{code}.coefficient"] = str(info["coefficient"])

    return values


def compute_diff(
    changes: list[ParameterChange],
) -> list[ParameterChange]:
    """Filter changes to only those that actually differ from current values."""
    current = get_current_values()
    real_changes: list[ParameterChange] = []

    for change in changes:
        current_val = current.get(change.nome_parametro)
        if current_val is None:
            # New parameter — always a real change
            real_changes.append(change)
        elif str(current_val) != str(change.valore_nuovo):
            # Value actually changed
            if not change.valore_precedente:
                change.valore_precedente = current_val
            real_changes.append(change)

    return real_changes


def filter_needs_review(
    changes: list[ParameterChange],
    anomaly_threshold_pct: float = 5.0,
) -> tuple[list[ParameterChange], list[ParameterChange]]:
    """Split changes into auto-applicable and needs-review.

    Returns (auto, review).
    Review criteria:
    - certezza == "bassa"
    - Percentage change exceeds anomaly threshold
    """
    auto: list[ParameterChange] = []
    review: list[ParameterChange] = []

    for change in changes:
        if change.certezza == "bassa":
            review.append(change)
            continue

        # Check percentage change for numeric values
        try:
            old = float(change.valore_precedente)
            new = float(change.valore_nuovo)
            if old != 0:
                pct_change = abs((new - old) / old) * 100
                if pct_change > anomaly_threshold_pct:
                    review.append(change)
                    continue
        except (ValueError, ZeroDivisionError):
            pass

        auto.append(change)

    return auto, review

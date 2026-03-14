"""Agent3 — Deterministic fiscal calculator for Italian forfettario regime.

Pure Python, zero LLM, zero external API calls.
All arithmetic uses Decimal for exact fiscal calculations.
"""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .models import AtecoDetail, CalcoloResult, ContribuenteInput, F24Entry

# Paths to shared data files
_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"
_ATECO_FILE = _SHARED_DIR / "ateco_coefficients.json"
_INPS_FILE = _SHARED_DIR / "inps_rates.json"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_ateco_coefficient(codice_ateco: str) -> Decimal:
    """Look up the coefficient for an ATECO code.

    First tries exact match, then prefix match, then range fallback.
    """
    data = _load_json(_ATECO_FILE)
    coefficients = data["coefficients"]

    # Exact match
    if codice_ateco in coefficients:
        return Decimal(coefficients[codice_ateco]["coefficient"])

    # Prefix match (e.g., "62.01" matches "62.01.00")
    for code, info in coefficients.items():
        if code.startswith(codice_ateco) or codice_ateco.startswith(code):
            return Decimal(info["coefficient"])

    # Range fallback by division (first 2 digits)
    division = codice_ateco.split(".")[0]
    div_num = int(division)
    range_fallback = data.get("range_fallback", {})
    for range_key, info in range_fallback.items():
        if range_key.startswith("_"):
            continue
        parts = range_key.split("-")
        if len(parts) == 2:
            low, high = int(parts[0]), int(parts[1])
            if low <= div_num <= high:
                return Decimal(info["coefficient"])
        elif int(parts[0]) == div_num:
            return Decimal(info["coefficient"])

    raise ValueError(f"No coefficient found for ATECO code: {codice_ateco}")


def _get_inps_rates(anno: int, gestione: str) -> dict[str, Any]:
    """Load INPS rates for the given year and management type."""
    data = _load_json(_INPS_FILE)
    anno_str = str(anno)

    if anno_str not in data:
        raise ValueError(f"INPS rates not available for year {anno}")

    year_data = data[anno_str]
    # Map short name to JSON key (e.g. "separata" → "gestione_separata")
    gestione_key = f"gestione_{gestione}" if gestione == "separata" else gestione
    if gestione_key not in year_data:
        raise ValueError(f"Unknown gestione INPS: {gestione}")
    gestione = gestione_key

    rates = year_data[gestione]

    # Check for null values (year not yet updated)
    for key, val in rates.items():
        if key.startswith("_"):
            continue
        if val is None:
            raise ValueError(
                f"INPS rate '{key}' for {gestione}/{anno} is null. "
                f"Update shared/inps_rates.json with the current year's circular."
            )

    return rates


def _round_euro(amount: Decimal) -> Decimal:
    """Round to 2 decimal places using standard rounding."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _compute_checksum(
    contribuente_id: str,
    anno_fiscale: int,
    reddito_imponibile: Decimal,
    imposta_sostitutiva: Decimal,
    da_versare: Decimal,
    credito_anno_prossimo: Decimal,
) -> str:
    """SHA-256 checksum of key calculation fields."""
    payload = (
        f"{contribuente_id}|{anno_fiscale}|{reddito_imponibile}|"
        f"{imposta_sostitutiva}|{da_versare}|{credito_anno_prossimo}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calcola(input_data: ContribuenteInput) -> CalcoloResult:
    """Execute the complete fiscal calculation.

    This is the main entry point for Agent3.
    Pure deterministic logic — no LLM, no randomness.
    """
    result = CalcoloResult(
        contribuente_id=input_data.contribuente_id,
        anno_fiscale=input_data.anno_fiscale,
        primo_anno=input_data.primo_anno,
        rivalsa_inps_applicata=input_data.rivalsa_inps_applicata,
        acconti_versati=input_data.acconti_versati,
        crediti_precedenti=input_data.crediti_precedenti,
    )

    # --- Per-ATECO breakdown ---
    reddito_lordo = Decimal("0")
    for codice_ateco, ricavi in input_data.ateco_ricavi.items():
        coeff = _get_ateco_coefficient(codice_ateco)
        reddito_ateco = _round_euro(ricavi * coeff)
        result.dettaglio_ateco.append(
            AtecoDetail(
                codice_ateco=codice_ateco,
                ricavi=ricavi,
                coefficiente=coeff,
                reddito=reddito_ateco,
            )
        )
        reddito_lordo += reddito_ateco

    result.reddito_lordo = _round_euro(reddito_lordo)

    # --- Deduct INPS contributions (only deduction in forfettario) ---
    result.contributi_inps_dedotti = input_data.contributi_inps_versati
    result.reddito_imponibile = _round_euro(
        max(Decimal("0"), result.reddito_lordo - input_data.contributi_inps_versati)
    )

    # --- Substitute tax ---
    result.aliquota = Decimal("0.05") if input_data.regime_agevolato else Decimal("0.15")
    result.imposta_sostitutiva = _round_euro(
        result.reddito_imponibile * result.aliquota
    )

    # --- Advances (CRITICAL: first year = zero) ---
    if input_data.primo_anno:
        result.acconto_prima_rata = Decimal("0")
        result.acconto_seconda_rata = Decimal("0")
        result.acconti_dovuti = Decimal("0")
    else:
        result.acconti_dovuti = _round_euro(
            input_data.imposta_anno_precedente * Decimal("1.00")
        )
        result.acconto_prima_rata = _round_euro(
            input_data.imposta_anno_precedente * Decimal("0.40")
        )
        result.acconto_seconda_rata = _round_euro(
            input_data.imposta_anno_precedente * Decimal("0.60")
        )

    # --- Balance ---
    saldo = (
        result.imposta_sostitutiva
        - input_data.acconti_versati
        - input_data.crediti_precedenti
    )
    result.saldo = _round_euro(saldo)

    if result.saldo < Decimal("0"):
        result.credito_anno_prossimo = _round_euro(abs(result.saldo))
        result.da_versare = Decimal("0")
    else:
        result.credito_anno_prossimo = Decimal("0")
        result.da_versare = result.saldo

    # --- INPS calculation ---
    _calcola_inps(input_data, result)

    # --- F24 entries ---
    _genera_f24(result)

    # --- Checksum ---
    result.checksum = _compute_checksum(
        result.contribuente_id,
        result.anno_fiscale,
        result.reddito_imponibile,
        result.imposta_sostitutiva,
        result.da_versare,
        result.credito_anno_prossimo,
    )

    return result


def _calcola_inps(input_data: ContribuenteInput, result: CalcoloResult) -> None:
    """Calculate INPS contributions based on management type."""
    rates = _get_inps_rates(input_data.anno_fiscale, input_data.gestione_inps)

    if input_data.gestione_inps == "separata":
        aliquota = Decimal(rates["aliquota"])
        contributo = _round_euro(result.reddito_imponibile * aliquota)
        result.contributo_inps_calcolato = contributo
        result.dettaglio_inps = {
            "tipo": "gestione_separata",
            "aliquota": str(aliquota),
            "base_imponibile": str(result.reddito_imponibile),
            "contributo": str(contributo),
        }

    elif input_data.gestione_inps in ("artigiani", "commercianti"):
        contributo_fisso = Decimal(rates["contributo_fisso_annuo"])
        minimale = Decimal(rates["minimale_annuo"])
        aliquota_ecc = Decimal(rates["aliquota_eccedenza"])

        eccedenza = max(Decimal("0"), result.reddito_imponibile - minimale)
        contributo_variabile = _round_euro(eccedenza * aliquota_ecc)
        totale = _round_euro(contributo_fisso + contributo_variabile)

        if input_data.riduzione_inps_35:
            totale = _round_euro(totale * Decimal("0.65"))

        result.contributo_inps_calcolato = totale
        result.dettaglio_inps = {
            "tipo": input_data.gestione_inps,
            "contributo_fisso": str(contributo_fisso),
            "minimale": str(minimale),
            "eccedenza": str(eccedenza),
            "aliquota_eccedenza": str(aliquota_ecc),
            "contributo_variabile": str(contributo_variabile),
            "riduzione_35": input_data.riduzione_inps_35,
            "totale": str(totale),
        }
    else:
        raise ValueError(f"Unknown gestione INPS: {input_data.gestione_inps}")


def _genera_f24(result: CalcoloResult) -> None:
    """Generate F24 payment entries."""
    if result.da_versare > Decimal("0"):
        result.f24_entries.append(
            F24Entry(
                codice_tributo="1792",
                descrizione="Imposta sostitutiva forfettario — SALDO",
                importo=result.da_versare,
                scadenza="06-30",
            )
        )

    if result.acconto_prima_rata > Decimal("0"):
        result.f24_entries.append(
            F24Entry(
                codice_tributo="1790",
                descrizione="Imposta sostitutiva forfettario — ACCONTO 1ª RATA (40%)",
                importo=result.acconto_prima_rata,
                scadenza="06-30",
            )
        )

    if result.acconto_seconda_rata > Decimal("0"):
        result.f24_entries.append(
            F24Entry(
                codice_tributo="1791",
                descrizione="Imposta sostitutiva forfettario — ACCONTO 2ª RATA (60%)",
                importo=result.acconto_seconda_rata,
                scadenza="11-30",
            )
        )

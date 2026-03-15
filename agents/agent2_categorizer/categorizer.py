"""Agent2 — Categorizer (ATECO-based transaction categorization)

Classifies transactions by ATECO code and expense category.
Tracks revenue progressively per ATECO per year.
Handles multi-ATECO profiles with keyword-based assignment.
Reconciles SDI invoices with bank movements.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import (
    AtecoRevenueDetail,
    CategorizedTransaction,
    ExpenseCategory,
    ReconciliationMatch,
    RevenueCounter,
)

logger = logging.getLogger(__name__)

# Load ATECO coefficients
_ATECO_FILE = Path(__file__).resolve().parent.parent.parent / "shared" / "ateco_coefficients.json"
_ATECO_DATA: dict[str, Any] = {}
_ATECO_COEFFICIENTS: dict[str, dict] = {}
_RANGE_FALLBACK: dict[str, dict] = {}


def _load_ateco() -> None:
    """Load ATECO data from shared JSON file."""
    global _ATECO_DATA, _ATECO_COEFFICIENTS, _RANGE_FALLBACK
    if _ATECO_COEFFICIENTS:
        return  # already loaded
    try:
        with open(_ATECO_FILE, encoding="utf-8") as f:
            _ATECO_DATA = json.load(f)
        _ATECO_COEFFICIENTS = _ATECO_DATA.get("coefficients", {})
        _RANGE_FALLBACK = _ATECO_DATA.get("range_fallback", {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load ATECO data: %s", e)


def _get_ateco_info(code: str) -> dict:
    """Get ATECO info by exact code, or fallback to range."""
    _load_ateco()

    # Exact match
    if code in _ATECO_COEFFICIENTS:
        return _ATECO_COEFFICIENTS[code]

    # Range fallback: extract 2-digit division
    division = code.split(".")[0] if "." in code else code[:2]
    try:
        div_num = int(division)
    except ValueError:
        return {}

    for range_key, info in _RANGE_FALLBACK.items():
        if range_key.startswith("_"):
            continue
        if "-" in range_key:
            lo, hi = range_key.split("-")
            try:
                if int(lo) <= div_num <= int(hi):
                    return info
            except ValueError:
                continue
        else:
            try:
                if int(range_key) == div_num:
                    return info
            except ValueError:
                continue

    return {}


def _get_profile_ateco_codes(profile: dict) -> list[str]:
    """Extract all ATECO codes from a profile."""
    anagrafica = profile.get("anagrafica", profile)
    codes = []
    principale = anagrafica.get("ateco_principale", "")
    if principale:
        codes.append(principale)
    secondari = anagrafica.get("ateco_secondari", [])
    if isinstance(secondari, list):
        codes.extend(secondari)
    return codes


def _match_ateco_by_keywords(description: str, ateco_codes: list[str]) -> tuple[str, float, str]:
    """Match a description to an ATECO code using keywords.

    Returns (ateco_code, confidence, rule_applied).
    """
    _load_ateco()
    desc_lower = description.lower()

    best_code = ""
    best_score = 0
    best_rule = ""

    for code in ateco_codes:
        info = _ATECO_COEFFICIENTS.get(code, {})
        keywords = info.get("keywords", [])

        score = 0
        matched_keywords = []
        for kw in keywords:
            if kw.lower() in desc_lower:
                # Longer keyword matches are worth more
                score += len(kw)
                matched_keywords.append(kw)

        if score > best_score:
            best_score = score
            best_code = code
            best_rule = f"keyword_match: {', '.join(matched_keywords)}"

    if best_code:
        # Normalize confidence: more matched chars = higher confidence
        confidence = min(1.0, best_score / max(len(desc_lower), 1) * 2)
        confidence = max(0.3, confidence)  # floor at 0.3 if we matched anything
        return best_code, confidence, best_rule

    return "", 0.0, ""


def _categorize_expense(description: str, importo: float = 0.0) -> tuple[str, float, str]:
    """Categorize an expense transaction by description keywords.

    Returns (category, confidence, rule_applied).
    """
    desc_lower = description.lower()

    best_cat = ExpenseCategory.ALTRO
    best_score = 0
    best_rule = ""

    for cat, keywords in ExpenseCategory.KEYWORDS.items():
        score = 0
        matched = []
        for kw in keywords:
            if kw.lower() in desc_lower:
                score += len(kw)
                matched.append(kw)

        if score > best_score:
            best_score = score
            best_cat = cat
            best_rule = f"expense_keyword: {', '.join(matched)}"

    confidence = min(1.0, best_score / max(len(desc_lower), 1) * 3) if best_score > 0 else 0.1
    confidence = max(0.2, confidence) if best_score > 0 else 0.1

    if not best_rule:
        best_rule = "default_altro"

    return best_cat, confidence, best_rule


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(transazione: dict, profile: dict) -> CategorizedTransaction:
    """Categorize a single transaction based on profile's ATECO codes.

    Args:
        transazione: Transaction dict with keys like tipo, importo, descrizione,
                     causale, fonte, cedente, numero_fattura, etc.
        profile: Contribuente profile dict (from persistence).

    Returns:
        CategorizedTransaction with ateco_code, category, confidence, rule.
    """
    _load_ateco()
    ateco_codes = _get_profile_ateco_codes(profile)

    tipo = transazione.get("tipo", "")
    descrizione = (
        transazione.get("descrizione", "")
        or transazione.get("causale", "")
        or ""
    )
    importo_raw = transazione.get("importo", 0)
    try:
        importo = float(importo_raw)
    except (ValueError, TypeError):
        importo = 0.0

    is_ricavo = tipo in ("ricavo", "RICAVO", "income")
    is_spesa = tipo in ("spesa", "SPESA", "expense", "f24", "F24")

    # If not explicitly typed, try to infer from context
    if not is_ricavo and not is_spesa:
        fonte = transazione.get("fonte", "")
        if fonte == "sdi":
            # Check if cedente matches profile
            cedente_piva = transazione.get("cedente_piva", "")
            profile_piva = profile.get("anagrafica", {}).get("partita_iva", "")
            if cedente_piva and profile_piva and cedente_piva == profile_piva:
                is_ricavo = True
            else:
                is_spesa = True
        elif fonte == "ocr":
            is_spesa = True
        elif importo >= 0:
            is_ricavo = True
        else:
            is_spesa = True

    result = CategorizedTransaction(
        original=transazione,
        is_ricavo=is_ricavo,
        is_spesa=is_spesa,
    )

    if is_ricavo:
        # Revenue: assign to ATECO code
        result.category = "ricavo"

        if len(ateco_codes) == 1:
            # Single ATECO — assign directly
            code = ateco_codes[0]
            info = _get_ateco_info(code)
            result.ateco_code = code
            result.ateco_description = info.get("description", "")
            result.confidence = 0.95
            result.rule_applied = "single_ateco_direct"
        elif len(ateco_codes) > 1:
            # Multi-ATECO — use keywords to match
            code, conf, rule = _match_ateco_by_keywords(descrizione, ateco_codes)
            if code:
                info = _get_ateco_info(code)
                result.ateco_code = code
                result.ateco_description = info.get("description", "")
                result.confidence = conf
                result.rule_applied = rule
            else:
                # Fallback to primary ATECO
                code = ateco_codes[0]
                info = _get_ateco_info(code)
                result.ateco_code = code
                result.ateco_description = info.get("description", "")
                result.confidence = 0.5
                result.rule_applied = "multi_ateco_fallback_primary"
        else:
            result.confidence = 0.1
            result.rule_applied = "no_ateco_in_profile"

    else:
        # Expense: categorize by description
        cat, conf, rule = _categorize_expense(descrizione, importo)
        result.category = cat
        result.confidence = conf
        result.rule_applied = rule

        # If expense has ATECO relevance (e.g., for tracking per-ATECO spend)
        if ateco_codes:
            code, ateco_conf, ateco_rule = _match_ateco_by_keywords(descrizione, ateco_codes)
            if code and ateco_conf > 0.3:
                result.ateco_code = code
                info = _get_ateco_info(code)
                result.ateco_description = info.get("description", "")

    return result


def categorize_batch(
    transazioni: list[dict], profile: dict
) -> list[CategorizedTransaction]:
    """Categorize a batch of transactions.

    Args:
        transazioni: List of transaction dicts.
        profile: Contribuente profile dict.

    Returns:
        List of CategorizedTransaction, one per input.
    """
    return [categorize(tx, profile) for tx in transazioni]


def get_revenue_counter(profile: dict, anno: int) -> RevenueCounter:
    """Build a revenue counter from profile's fatture for a given year.

    Reads the `fatture` list from the profile, filters by year,
    and aggregates revenue per ATECO code.

    Args:
        profile: Contribuente profile dict (with 'fatture' list).
        anno: Fiscal year to count.

    Returns:
        RevenueCounter with per-ATECO breakdown and threshold percentage.
    """
    _load_ateco()
    ateco_codes = _get_profile_ateco_codes(profile)
    fatture = profile.get("fatture", [])

    counter = RevenueCounter(anno=anno)

    for fattura in fatture:
        # Filter by year
        fattura_data = fattura.get("data", "")
        fattura_anno = fattura.get("anno", 0)

        if fattura_anno and fattura_anno != anno:
            continue
        if fattura_data and not fattura_anno:
            try:
                d = date.fromisoformat(fattura_data)
                if d.year != anno:
                    continue
            except (ValueError, TypeError):
                continue

        importo_raw = fattura.get("imponibile") or fattura.get("importo") or fattura.get("totale_documento") or "0"
        try:
            importo = Decimal(str(importo_raw))
        except (InvalidOperation, ValueError):
            continue

        # Determine ATECO code for this fattura
        fattura_ateco = fattura.get("ateco_code", "")

        if not fattura_ateco:
            descrizione = fattura.get("descrizione") or fattura.get("causale") or ""
            if len(ateco_codes) == 1:
                fattura_ateco = ateco_codes[0]
            elif len(ateco_codes) > 1:
                matched, _, _ = _match_ateco_by_keywords(descrizione, ateco_codes)
                fattura_ateco = matched or (ateco_codes[0] if ateco_codes else "")
            else:
                fattura_ateco = ""

        if fattura_ateco:
            info = _get_ateco_info(fattura_ateco)
            coeff_str = info.get("coefficient", "0")
            try:
                coeff = Decimal(coeff_str)
            except (InvalidOperation, ValueError):
                coeff = Decimal("0")
            counter.add_revenue(
                fattura_ateco, importo,
                description=info.get("description", ""),
                coefficient=coeff,
            )
        else:
            counter.grand_total += importo

    # Annualized projection based on current date
    today = date.today()
    if today.year == anno and today.month > 0:
        days_elapsed = (today - date(anno, 1, 1)).days + 1
        if days_elapsed > 0 and counter.grand_total > 0:
            daily_avg = counter.grand_total / days_elapsed
            counter.proiezione_annuale = (daily_avg * 365).quantize(Decimal("0.01"))

    return counter


def match_invoice_payment(
    fattura: dict,
    movimenti: list[dict],
    tolerance_days: int = 15,
) -> dict | None:
    """Reconcile an SDI invoice with bank movements.

    Matches by amount (exact) and date proximity (within tolerance_days).
    Also checks client name similarity.

    Args:
        fattura: Invoice dict with importo/totale_documento, data, numero, cliente/cessionario.
        movimenti: List of bank movement dicts.
        tolerance_days: Max days between invoice date and payment date.

    Returns:
        Best matching movement dict with match metadata, or None.
    """
    # Extract invoice data
    fattura_importo_raw = (
        fattura.get("totale_documento")
        or fattura.get("importo")
        or fattura.get("imponibile")
        or "0"
    )
    try:
        fattura_importo = Decimal(str(fattura_importo_raw))
    except (InvalidOperation, ValueError):
        return None

    fattura_data_str = fattura.get("data", "")
    try:
        fattura_date = date.fromisoformat(str(fattura_data_str))
    except (ValueError, TypeError):
        fattura_date = date.today()

    fattura_numero = fattura.get("numero", "")
    fattura_cliente = (
        fattura.get("cessionario", {}).get("denominazione", "")
        if isinstance(fattura.get("cessionario"), dict)
        else fattura.get("cessionario", "")
    )

    best_match: dict | None = None
    best_score = 0.0

    for mov in movimenti:
        # Parse movement amount
        mov_importo_raw = mov.get("importo") or mov.get("amount") or mov.get("value") or "0"
        try:
            mov_importo = Decimal(str(mov_importo_raw))
        except (InvalidOperation, ValueError):
            continue

        # Parse movement date
        mov_data_str = mov.get("data") or mov.get("booking_date") or mov.get("date") or ""
        try:
            mov_date = date.fromisoformat(str(mov_data_str))
        except (ValueError, TypeError):
            continue

        # Amount match (exact or with abs for sign differences)
        amount_match = (mov_importo == fattura_importo) or (abs(mov_importo) == abs(fattura_importo))
        if not amount_match:
            continue

        # Date proximity
        days_diff = abs((mov_date - fattura_date).days)
        if days_diff > tolerance_days:
            continue

        # Score: closer date = higher score
        date_score = 1.0 - (days_diff / tolerance_days)

        # Bonus for client name match in causale
        causale = (mov.get("causale") or mov.get("description") or mov.get("remittance_information") or "").lower()
        controparte = (mov.get("denominazione_controparte") or mov.get("counterpart_name") or "").lower()

        name_score = 0.0
        if fattura_cliente:
            cliente_lower = fattura_cliente.lower()
            if cliente_lower in causale or cliente_lower in controparte:
                name_score = 0.3
            elif any(part in causale or part in controparte for part in cliente_lower.split() if len(part) > 2):
                name_score = 0.15

        # Bonus for invoice number in causale
        num_score = 0.0
        if fattura_numero and fattura_numero.replace("/", "") in causale.replace("/", ""):
            num_score = 0.2

        total_score = date_score * 0.5 + name_score + num_score + (0.3 if amount_match else 0.0)

        if total_score > best_score:
            best_score = total_score
            best_match = {
                "movimento": mov,
                "fattura_numero": fattura_numero,
                "fattura_importo": str(fattura_importo),
                "movimento_importo": str(mov_importo),
                "movimento_data": mov_date.isoformat(),
                "days_difference": days_diff,
                "amount_match": True,
                "confidence": round(min(1.0, total_score), 2),
                "match_score": round(total_score, 3),
            }

    return best_match


def suggest_category(description: str, importo: float = 0.0) -> list[str]:
    """Suggest expense categories based on description.

    Returns a ranked list of up to 3 category suggestions.

    Args:
        description: Free-text description of the expense.
        importo: Amount (optional, for context).

    Returns:
        List of category strings, best match first.
    """
    desc_lower = description.lower()
    scored: list[tuple[str, int]] = []

    for cat, keywords in ExpenseCategory.KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in desc_lower:
                score += len(kw)
        if score > 0:
            scored.append((cat, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    result = [cat for cat, _ in scored[:3]]

    # Always include ALTRO as last if we have fewer than 3
    if ExpenseCategory.ALTRO not in result:
        result.append(ExpenseCategory.ALTRO)

    return result[:3]

"""Tests for Agent2 Categorizer — 12 test cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agents.agent2_categorizer.categorizer import (
    categorize,
    categorize_batch,
    get_revenue_counter,
    match_invoice_payment,
    suggest_category,
)
from agents.agent2_categorizer.models import (
    CategorizedTransaction,
    ExpenseCategory,
    RevenueCounter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile_single_ateco() -> dict:
    return {
        "anagrafica": {
            "ateco_principale": "62.01.00",
            "ateco_secondari": [],
        },
        "fatture": [
            {
                "data": "2024-03-15",
                "imponibile": "3000",
                "descrizione": "Sviluppo app web",
            },
            {
                "data": "2024-06-20",
                "imponibile": "5000",
                "descrizione": "Sviluppo backend API",
            },
            {
                "data": "2023-12-01",
                "imponibile": "2000",
                "descrizione": "Vecchia fattura",
            },
        ],
    }


@pytest.fixture
def profile_multi_ateco() -> dict:
    return {
        "anagrafica": {
            "ateco_principale": "62.01.00",
            "ateco_secondari": ["73.11.02"],
        },
        "fatture": [],
    }


# ---------------------------------------------------------------------------
# Single Transaction Categorization
# ---------------------------------------------------------------------------

class TestCategorizeSingle:
    def test_ricavo_single_ateco(self, profile_single_ateco):
        tx = {"tipo": "ricavo", "importo": "3000", "descrizione": "Sviluppo app web"}
        result = categorize(tx, profile_single_ateco)
        assert isinstance(result, CategorizedTransaction)
        assert result.is_ricavo is True
        assert result.ateco_code == "62.01.00"
        assert result.confidence >= 0.9
        assert result.rule_applied == "single_ateco_direct"

    def test_ricavo_multi_ateco_software(self, profile_multi_ateco):
        tx = {"tipo": "ricavo", "importo": "2000", "descrizione": "Sviluppo software gestionale"}
        result = categorize(tx, profile_multi_ateco)
        assert result.ateco_code == "62.01.00"
        assert "keyword_match" in result.rule_applied

    def test_ricavo_multi_ateco_marketing(self, profile_multi_ateco):
        tx = {"tipo": "ricavo", "importo": "1500", "descrizione": "Campagne pubblicitarie Google Ads"}
        result = categorize(tx, profile_multi_ateco)
        assert result.ateco_code == "73.11.02"
        assert "keyword_match" in result.rule_applied

    def test_spesa_categorization(self, profile_single_ateco):
        tx = {"tipo": "spesa", "importo": "120", "descrizione": "Abbonamento hosting AWS cloud"}
        result = categorize(tx, profile_single_ateco)
        assert result.is_spesa is True
        assert result.category == ExpenseCategory.SOFTWARE

    def test_spesa_trasporto(self, profile_single_ateco):
        tx = {"tipo": "spesa", "importo": "45", "descrizione": "Biglietto treno Italo Milano-Roma"}
        result = categorize(tx, profile_single_ateco)
        assert result.category == ExpenseCategory.TRASPORTO

    def test_spesa_default_altro(self, profile_single_ateco):
        tx = {"tipo": "spesa", "importo": "10", "descrizione": "xyzzy"}
        result = categorize(tx, profile_single_ateco)
        assert result.category == ExpenseCategory.ALTRO

    def test_infer_tipo_from_fonte_ocr(self, profile_single_ateco):
        tx = {"fonte": "ocr", "importo": "30", "descrizione": "Scontrino bar caffè"}
        result = categorize(tx, profile_single_ateco)
        assert result.is_spesa is True
        assert result.category == ExpenseCategory.RAPPRESENTANZA


# ---------------------------------------------------------------------------
# Batch Categorization
# ---------------------------------------------------------------------------

class TestCategorizeBatch:
    def test_batch_multiple(self, profile_single_ateco):
        txs = [
            {"tipo": "ricavo", "importo": "1000", "descrizione": "Consulenza"},
            {"tipo": "spesa", "importo": "50", "descrizione": "Cancelleria penne"},
        ]
        results = categorize_batch(txs, profile_single_ateco)
        assert len(results) == 2
        assert results[0].is_ricavo is True
        assert results[1].is_spesa is True


# ---------------------------------------------------------------------------
# Revenue Counter
# ---------------------------------------------------------------------------

class TestRevenueCounter:
    def test_counter_single_year(self, profile_single_ateco):
        counter = get_revenue_counter(profile_single_ateco, 2024)
        assert counter.anno == 2024
        assert counter.grand_total == Decimal("8000")
        assert len(counter.per_ateco) == 1
        assert counter.per_ateco[0].ateco_code == "62.01.00"
        assert counter.per_ateco[0].transaction_count == 2

    def test_counter_excludes_other_years(self, profile_single_ateco):
        counter = get_revenue_counter(profile_single_ateco, 2023)
        assert counter.grand_total == Decimal("2000")

    def test_counter_threshold_percentage(self, profile_single_ateco):
        counter = get_revenue_counter(profile_single_ateco, 2024)
        expected_pct = (Decimal("8000") / Decimal("85000") * 100).quantize(Decimal("0.01"))
        assert counter.soglia_85k_percentage == expected_pct
        assert counter.over_threshold is False

    def test_counter_empty_year(self, profile_single_ateco):
        counter = get_revenue_counter(profile_single_ateco, 2025)
        assert counter.grand_total == Decimal("0")


# ---------------------------------------------------------------------------
# Invoice-Payment Reconciliation
# ---------------------------------------------------------------------------

class TestMatchInvoicePayment:
    def test_exact_match(self):
        fattura = {
            "numero": "2024/001",
            "totale_documento": "3002.00",
            "data": "2024-03-15",
            "cessionario": "Acme S.r.l.",
        }
        movimenti = [
            {
                "id": "m1",
                "importo": "3002.00",
                "data": "2024-03-20",
                "causale": "Bonifico Acme S.r.l. fattura 2024/001",
            },
        ]
        match = match_invoice_payment(fattura, movimenti)
        assert match is not None
        assert match["amount_match"] is True
        assert match["days_difference"] == 5
        assert match["confidence"] > 0.5

    def test_no_match_amount_mismatch(self):
        fattura = {"numero": "001", "totale_documento": "1000", "data": "2024-01-01"}
        movimenti = [{"id": "m1", "importo": "999", "data": "2024-01-05", "causale": "Bonifico"}]
        match = match_invoice_payment(fattura, movimenti)
        assert match is None

    def test_no_match_date_too_far(self):
        fattura = {"numero": "001", "totale_documento": "1000", "data": "2024-01-01"}
        movimenti = [{"id": "m1", "importo": "1000", "data": "2024-06-01", "causale": "Bonifico"}]
        match = match_invoice_payment(fattura, movimenti)
        assert match is None


# ---------------------------------------------------------------------------
# Suggest Category
# ---------------------------------------------------------------------------

class TestSuggestCategory:
    def test_suggest_software(self):
        cats = suggest_category("Abbonamento annuale hosting cloud AWS")
        assert ExpenseCategory.SOFTWARE in cats

    def test_suggest_trasporto(self):
        cats = suggest_category("Biglietto treno Roma-Milano")
        assert ExpenseCategory.TRASPORTO in cats

    def test_suggest_always_includes_altro(self):
        cats = suggest_category("Qualcosa di generico senza keyword")
        assert ExpenseCategory.ALTRO in cats

    def test_suggest_max_three(self):
        cats = suggest_category("hosting software cloud formazione corso libro")
        assert len(cats) <= 3

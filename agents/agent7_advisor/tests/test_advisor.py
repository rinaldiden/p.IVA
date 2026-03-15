"""Test suite for Agent7 Fiscal Advisor — 10 test cases."""

from decimal import Decimal

import pytest

from agents.agent7_advisor.advisor import (
    advise,
    confronto_regimi,
    ottimizza_multi_ateco,
    simulate_what_if,
    soglia_convenienza,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**overrides):
    """Create a minimal profile dict."""
    profile = {
        "contribuente_id": "TEST001",
        "anagrafica": {
            "codice_fiscale": "RSSMRA80A01H501Z",
            "ateco_principale": "62.01.00",
            "ateco_secondari": [],
            "gestione_inps": "separata",
            "primo_anno": True,
            "regime_agevolato": True,
            "riduzione_inps_35": False,
        },
        "fatture": [],
        "pagamenti": [],
    }
    profile.update(overrides)
    return profile


# ---------------------------------------------------------------------------
# Test: Confronto regimi
# ---------------------------------------------------------------------------

class TestConfrontoRegimi:
    """Tests for regime comparison."""

    def test_forfettario_cheaper_at_low_revenue(self):
        result = confronto_regimi(
            fatturato=Decimal("30000"),
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
            regime_agevolato=True,
        )
        assert result.forfettario.totale_carico_fiscale < result.ordinario.totale_carico_fiscale
        assert result.regime_consigliato == "forfettario"
        assert result.risparmio_forfettario_vs_ordinario > Decimal("0")

    def test_forfettario_15_percent(self):
        result = confronto_regimi(
            fatturato=Decimal("40000"),
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
            regime_agevolato=False,
        )
        assert result.forfettario.dettaglio["aliquota"] == "0.15"
        assert result.forfettario.imposta_principale > Decimal("0")

    def test_all_three_regimes_populated(self):
        result = confronto_regimi(
            fatturato=Decimal("50000"),
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
        )
        assert result.forfettario.totale_carico_fiscale > Decimal("0")
        assert result.ordinario.totale_carico_fiscale > Decimal("0")
        assert result.srl.totale_carico_fiscale > Decimal("0")

    def test_artigiani_comparison(self):
        result = confronto_regimi(
            fatturato=Decimal("40000"),
            ateco="43.21.01",
            gestione="artigiani",
            anno=2025,
        )
        assert result.forfettario.inps > Decimal("0")
        assert result.gestione_inps == "artigiani"

    def test_aliquota_effettiva_calculated(self):
        result = confronto_regimi(
            fatturato=Decimal("50000"),
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
        )
        # Effective rate should be between 0% and 100%
        assert Decimal("0") < result.forfettario.aliquota_effettiva < Decimal("100")
        assert Decimal("0") < result.ordinario.aliquota_effettiva < Decimal("100")

    def test_netto_disponibile_positive(self):
        result = confronto_regimi(
            fatturato=Decimal("60000"),
            ateco="74.90.99",
            gestione="separata",
            anno=2025,
        )
        assert result.forfettario.netto_disponibile > Decimal("0")
        assert result.ordinario.netto_disponibile > Decimal("0")
        assert result.srl.netto_disponibile > Decimal("0")

    def test_over_85k_note(self):
        result = confronto_regimi(
            fatturato=Decimal("100000"),
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
        )
        assert any("85.000" in n for n in result.note)


# ---------------------------------------------------------------------------
# Test: Soglia convenienza
# ---------------------------------------------------------------------------

class TestSogliaConvenienza:
    """Tests for break-even point calculation."""

    def test_returns_reasonable_value(self):
        result = soglia_convenienza(
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
            regime_agevolato=True,
        )
        assert result > Decimal("0")
        assert result <= Decimal("85000")

    def test_agevolato_higher_threshold(self):
        soglia_5 = soglia_convenienza(
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
            regime_agevolato=True,
        )
        soglia_15 = soglia_convenienza(
            ateco="62.01.00",
            gestione="separata",
            anno=2025,
            regime_agevolato=False,
        )
        # 5% rate should be convenient at higher revenue than 15%
        assert soglia_5 >= soglia_15


# ---------------------------------------------------------------------------
# Test: What-if simulation
# ---------------------------------------------------------------------------

class TestWhatIf:
    """Tests for what-if scenario simulation."""

    def test_additional_revenue_increases_tax(self):
        profile = _make_profile(fatture=[
            {"numero": "1", "importo": "30000", "data": "2025-03-15", "cliente": "A"},
        ])
        result = simulate_what_if(
            profile,
            {"fatturato_aggiuntivo": Decimal("20000")},
            anno=2025,
        )
        assert result.delta_imposta > Decimal("0")
        assert result.delta_inps > Decimal("0")
        assert result.fatturato_scenario == Decimal("50000.00")
        assert not result.supera_soglia

    def test_exceeding_threshold_flagged(self):
        profile = _make_profile(fatture=[
            {"numero": "1", "importo": "70000", "data": "2025-06-15", "cliente": "A"},
        ])
        result = simulate_what_if(
            profile,
            {"fatturato_aggiuntivo": Decimal("20000")},
            anno=2025,
        )
        assert result.supera_soglia
        assert any("85.000" in n for n in result.note)

    def test_marginal_rate_in_notes(self):
        profile = _make_profile(fatture=[
            {"numero": "1", "importo": "20000", "data": "2025-03-15", "cliente": "A"},
        ])
        result = simulate_what_if(
            profile,
            {"fatturato_aggiuntivo": Decimal("10000")},
            anno=2025,
        )
        assert any("marginale" in n.lower() for n in result.note)


# ---------------------------------------------------------------------------
# Test: Multi-ATECO optimization
# ---------------------------------------------------------------------------

class TestMultiAteco:
    """Tests for multi-ATECO optimization."""

    def test_single_ateco_no_optimization(self):
        result = ottimizza_multi_ateco(
            {"62.01.00": Decimal("50000")},
        )
        assert "Un solo codice ATECO" in result.note[0]

    def test_multiple_atecos_shows_coefficients(self):
        result = ottimizza_multi_ateco({
            "62.01.00": Decimal("30000"),  # coeff 0.78
            "47.91.10": Decimal("20000"),  # coeff 0.40
        })
        assert len(result.note) >= 2
        assert result.reddito_originale > Decimal("0")
        # Should mention which ATECO has lowest coefficient
        assert any("0.40" in n or "piu' basso" in n for n in result.note)

    def test_evasion_warning_present(self):
        result = ottimizza_multi_ateco({
            "62.01.00": Decimal("30000"),
            "47.91.10": Decimal("20000"),
        })
        assert any("evasione" in n.lower() for n in result.note)


# ---------------------------------------------------------------------------
# Test: Full advisory
# ---------------------------------------------------------------------------

class TestFullAdvisory:
    """Tests for the full advise() function."""

    def test_complete_report_generated(self):
        profile = _make_profile(fatture=[
            {"numero": "1", "importo": "25000", "data": "2025-03-15", "cliente": "A"},
        ])
        report = advise(profile, 2025)
        assert report.confronto is not None
        assert report.soglia_convenienza > Decimal("0")
        assert report.timing is not None
        assert len(report.raccomandazioni) > 0

    def test_multi_ateco_advisory_when_secondari_present(self):
        profile = _make_profile()
        profile["anagrafica"]["ateco_secondari"] = ["47.91.10"]
        profile["fatture"] = [
            {"numero": "1", "importo": "20000", "data": "2025-03-15", "cliente": "A", "ateco": "62.01.00"},
            {"numero": "2", "importo": "10000", "data": "2025-04-15", "cliente": "B", "ateco": "47.91.10"},
        ]
        report = advise(profile, 2025)
        assert report.multi_ateco is not None

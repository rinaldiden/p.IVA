"""Tests for Agent5 — Declaration Generator."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.agent5_declaration.declaration import (
    compile_quadro_lm,
    compile_quadro_rr,
    genera_riepilogo,
    generate_declaration,
    submit_declaration,
    validate_declaration,
)
from agents.agent5_declaration.models import Declaration, QuadroLM, QuadroRR


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_profile(
    ricavi: dict[str, str] | None = None,
    anno: int = 2024,
    regime_agevolato: bool = True,
    primo_anno: bool = True,
    gestione_inps: str = "separata",
    contributi_versati: str = "0",
    perdite_pregresse: str = "0",
) -> dict:
    """Build a minimal valid profile for testing."""
    if ricavi is None:
        ricavi = {"62.01": "50000"}

    fatture = []
    for ateco, importo in ricavi.items():
        fatture.append({
            "anno": anno,
            "imponibile": importo,
            "codice_ateco": ateco,
        })

    return {
        "contribuente_id": "RSSMRA80A01H501U",
        "anagrafica": {
            "nome": "Mario",
            "cognome": "Rossi",
            "codice_fiscale": "RSSMRA80A01H501U",
            "ateco_principale": list(ricavi.keys())[0],
            "regime_agevolato": regime_agevolato,
            "primo_anno": primo_anno,
            "gestione_inps": gestione_inps,
            "riduzione_inps_35": False,
        },
        "fatture": fatture,
        "spese": [],
        "contributi_inps_versati": contributi_versati,
        "perdite_pregresse": perdite_pregresse,
        "acconti_versati": "0",
        "crediti_precedenti": "0",
        "imposta_anno_precedente": "0",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompileQuadroLM:
    """Tests for compile_quadro_lm."""

    def test_basic_single_ateco(self):
        """Single ATECO 62.01 with 78% coefficient yields correct LM fields."""
        profile = _make_profile(ricavi={"62.01": "50000"})
        lm = compile_quadro_lm(profile, 2024)

        assert lm.lm21_ricavi_totali == Decimal("50000")
        assert lm.lm22_codice_ateco_principale == "62.01"
        assert len(lm.dettaglio_ateco) == 1
        assert lm.dettaglio_ateco[0].coefficiente_redditivita == Decimal("0.78")
        # 50000 * 0.78 = 39000
        assert lm.lm27_reddito_lordo == Decimal("39000.00")
        assert lm.lm33_aliquota == Decimal("0.05")  # primo anno agevolato
        # 39000 * 0.05 = 1950
        assert lm.lm34_imposta_dovuta == Decimal("1950.00")

    def test_multiple_ateco(self):
        """Multiple ATECO codes sum correctly."""
        profile = _make_profile(ricavi={"62.01": "30000", "47.91": "20000"})
        lm = compile_quadro_lm(profile, 2024)

        assert lm.lm21_ricavi_totali == Decimal("50000")
        assert len(lm.dettaglio_ateco) == 2
        # LM27 should be sum of individual redditi
        somma = sum(a.reddito_lordo for a in lm.dettaglio_ateco)
        assert lm.lm27_reddito_lordo == somma

    def test_aliquota_15_percent(self):
        """Non-primo-anno or non-agevolato uses 15% rate."""
        profile = _make_profile(regime_agevolato=False)
        lm = compile_quadro_lm(profile, 2024)

        assert lm.lm33_aliquota == Decimal("0.15")

    def test_inps_deduction(self):
        """INPS contributions are deducted in LM28 → LM29."""
        profile = _make_profile(contributi_versati="5000")
        lm = compile_quadro_lm(profile, 2024)

        assert lm.lm28_contributi_previdenziali == Decimal("5000")
        # reddito lordo 39000 - 5000 = 34000
        assert lm.lm29_reddito_netto == Decimal("34000.00")

    def test_perdite_pregresse(self):
        """Perdite pregresse reduce the taxable income."""
        profile = _make_profile(perdite_pregresse="10000")
        lm = compile_quadro_lm(profile, 2024)

        # reddito imponibile = reddito netto (39000) - perdite (10000) = 29000
        assert lm.lm30_perdite_pregresse == Decimal("10000")
        assert lm.lm32_reddito_imponibile == Decimal("29000.00")


class TestCompileQuadroRR:
    """Tests for compile_quadro_rr."""

    def test_gestione_separata(self):
        """Gestione separata uses percentage-based contribution."""
        profile = _make_profile(gestione_inps="separata")
        rr = compile_quadro_rr(profile, 2024)

        assert rr.sezione_ii is not None
        assert rr.sezione_ii.tipo_gestione == "gestione_separata"
        assert rr.sezione_ii.aliquota == Decimal("0.2607")
        assert rr.totale_contributi_dovuti > Decimal("0")

    def test_gestione_artigiani(self):
        """Artigiani uses fixed + variable contribution."""
        profile = _make_profile(gestione_inps="artigiani")
        rr = compile_quadro_rr(profile, 2024)

        assert rr.sezione_i is not None
        assert rr.sezione_i.tipo_gestione == "artigiani"
        assert rr.sezione_i.contributi_fissi > Decimal("0")
        assert rr.totale_contributi_dovuti > Decimal("0")


class TestGenerateDeclaration:
    """Tests for generate_declaration (full flow)."""

    def test_successful_generation(self):
        """Complete declaration is generated without errors."""
        profile = _make_profile()
        decl = generate_declaration(profile, 2024)

        assert decl.status == "compilata"
        assert decl.anno_fiscale == 2024
        assert decl.contribuente_id == "RSSMRA80A01H501U"
        assert not decl.errors
        assert decl.quadro_lm.lm21_ricavi_totali > Decimal("0")
        assert decl.riepilogo

    def test_missing_ricavi_fails(self):
        """Declaration with no revenue produces error status."""
        profile = _make_profile()
        profile["fatture"] = []  # remove all invoices
        decl = generate_declaration(profile, 2024)

        assert decl.status == "errore"
        assert len(decl.errors) > 0


class TestValidateDeclaration:
    """Tests for validate_declaration."""

    def test_valid_declaration_no_errors(self):
        """A well-formed declaration passes validation."""
        profile = _make_profile()
        decl = generate_declaration(profile, 2024)
        errors = validate_declaration(decl)
        assert errors == []

    def test_missing_contribuente_id(self):
        """Missing contribuente_id triggers validation error."""
        decl = Declaration(anno_fiscale=2024, contribuente_id="")
        errors = validate_declaration(decl)
        assert any("Contribuente ID" in e for e in errors)

    def test_invalid_anno_fiscale(self):
        """Year before 2015 triggers validation error."""
        decl = Declaration(anno_fiscale=2010, contribuente_id="TEST")
        errors = validate_declaration(decl)
        assert any("2010" in e for e in errors)


class TestSubmitDeclaration:
    """Tests for submit_declaration."""

    def test_submit_dry_run_success(self):
        """Successful dry-run submission returns protocol number."""
        profile = _make_profile()
        decl = generate_declaration(profile, 2024)
        result = submit_declaration(decl)

        assert result.success is True
        assert result.dry_run is True
        assert result.protocol_number.startswith("DRY-2024-")
        assert result.timestamp

    def test_submit_with_errors_fails(self):
        """Declaration in error state cannot be submitted."""
        decl = Declaration(anno_fiscale=2024, contribuente_id="TEST")
        decl.status = "errore"
        decl.errors = ["Some error"]
        result = submit_declaration(decl)

        assert result.success is False
        assert result.dry_run is True


class TestGeneraRiepilogo:
    """Tests for genera_riepilogo."""

    def test_riepilogo_keys(self):
        """Summary contains all expected keys."""
        profile = _make_profile()
        decl = generate_declaration(profile, 2024)
        riepilogo = genera_riepilogo(decl)

        expected_keys = [
            "anno_fiscale", "contribuente_id", "ricavi_totali",
            "reddito_lordo", "reddito_imponibile", "imposta_dovuta",
            "aliquota_imposta", "inps_contributi_dovuti",
            "totale_imposte_e_contributi",
        ]
        for key in expected_keys:
            assert key in riepilogo, f"Missing key: {key}"

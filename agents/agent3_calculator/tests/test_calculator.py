"""Test suite for Agent3 Calculator — 8 test cases as specified."""

from decimal import Decimal

import pytest

from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput


def _make_input(**overrides) -> ContribuenteInput:
    """Factory with sensible defaults."""
    defaults = {
        "contribuente_id": "TEST001",
        "anno_fiscale": 2024,
        "primo_anno": True,
        "ateco_ricavi": {"74.90.99": Decimal("40000")},
        "rivalsa_inps_applicata": Decimal("0"),
        "regime_agevolato": True,
        "gestione_inps": "separata",
        "riduzione_inps_35": False,
        "contributi_inps_versati": Decimal("0"),
        "imposta_anno_precedente": Decimal("0"),
        "acconti_versati": Decimal("0"),
        "crediti_precedenti": Decimal("0"),
    }
    defaults.update(overrides)
    return ContribuenteInput(**defaults)


class TestConsulentePrimoAnno:
    """Test 1: Consulente base primo anno.
    40k ricavi, ATECO 74.90.99 (coeff 0.78), aliquota 5%, primo_anno=True.
    """

    def test_reddito_lordo(self):
        result = calcola(_make_input())
        assert result.reddito_lordo == Decimal("31200.00")

    def test_imposta_sostitutiva(self):
        result = calcola(_make_input())
        # 31200 * 0.05 = 1560
        assert result.imposta_sostitutiva == Decimal("1560.00")

    def test_acconti_zero_primo_anno(self):
        result = calcola(_make_input())
        assert result.acconti_dovuti == Decimal("0")
        assert result.acconto_prima_rata == Decimal("0")
        assert result.acconto_seconda_rata == Decimal("0")

    def test_da_versare(self):
        result = calcola(_make_input())
        assert result.da_versare == Decimal("1560.00")

    def test_checksum_not_empty(self):
        result = calcola(_make_input())
        assert len(result.checksum) == 64  # SHA-256 hex


class TestConsulenteAnnoSuccessivo:
    """Test 2: Consulente anno successivo.
    50k ricavi, imposta_anno_precedente=3510 → acconto_1=1404, acconto_2=2106.
    """

    def test_acconti(self):
        inp = _make_input(
            primo_anno=False,
            ateco_ricavi={"74.90.99": Decimal("50000")},
            imposta_anno_precedente=Decimal("3510"),
        )
        result = calcola(inp)
        assert result.acconto_prima_rata == Decimal("1404.00")
        assert result.acconto_seconda_rata == Decimal("2106.00")
        assert result.acconti_dovuti == Decimal("3510.00")

    def test_reddito(self):
        inp = _make_input(
            primo_anno=False,
            ateco_ricavi={"74.90.99": Decimal("50000")},
            imposta_anno_precedente=Decimal("3510"),
        )
        result = calcola(inp)
        # 50000 * 0.78 = 39000
        assert result.reddito_lordo == Decimal("39000.00")


class TestMultiAteco:
    """Test 3: Multi-ATECO.
    30k@62.01.00 (coeff 0.78) + 20k@47.xx (coeff 0.40) → 23400+8000=31400.
    """

    def test_reddito_lordo_multi(self):
        inp = _make_input(
            ateco_ricavi={
                "62.01.00": Decimal("30000"),
                "47.11.40": Decimal("20000"),
            },
        )
        result = calcola(inp)
        assert result.reddito_lordo == Decimal("31400.00")

    def test_dettaglio_ateco(self):
        inp = _make_input(
            ateco_ricavi={
                "62.01.00": Decimal("30000"),
                "47.11.40": Decimal("20000"),
            },
        )
        result = calcola(inp)
        assert len(result.dettaglio_ateco) == 2


class TestRivalsaINPS:
    """Test 4: Rivalsa INPS 4% non altera il calcolo.
    La rivalsa è informativa, non entra nel reddito imponibile.
    """

    def test_rivalsa_non_altera(self):
        senza = calcola(_make_input(rivalsa_inps_applicata=Decimal("0")))
        con = calcola(_make_input(rivalsa_inps_applicata=Decimal("1248")))
        assert senza.reddito_imponibile == con.reddito_imponibile
        assert senza.imposta_sostitutiva == con.imposta_sostitutiva
        assert senza.da_versare == con.da_versare


class TestCreditoAnnoPrecedente:
    """Test 5: Credito anno precedente.
    Imposta=1560, crediti_precedenti=500 → da_versare=1060.
    """

    def test_credito_riduce_saldo(self):
        inp = _make_input(crediti_precedenti=Decimal("500"))
        result = calcola(inp)
        # imposta 1560 - crediti 500 = 1060
        assert result.da_versare == Decimal("1060.00")
        assert result.credito_anno_prossimo == Decimal("0")

    def test_credito_eccede_genera_riporto(self):
        inp = _make_input(crediti_precedenti=Decimal("2000"))
        result = calcola(inp)
        # imposta 1560 - crediti 2000 = -440
        assert result.da_versare == Decimal("0")
        assert result.credito_anno_prossimo == Decimal("440.00")


class TestINPSArtigianiRiduzione:
    """Test 6: INPS artigiani con riduzione 35%."""

    def test_riduzione_35(self):
        inp = _make_input(
            ateco_ricavi={"41.20.00": Decimal("60000")},
            gestione_inps="artigiani",
            riduzione_inps_35=True,
            regime_agevolato=False,
        )
        result = calcola(inp)
        # reddito_lordo = 60000 * 0.86 = 51600
        assert result.reddito_lordo == Decimal("51600.00")
        # contributo_inps has riduzione 35% applied
        assert result.contributo_inps_calcolato > Decimal("0")
        # Verify 35% reduction was applied
        assert result.dettaglio_inps["riduzione_35"] is True


class TestAliquota15:
    """Test: aliquota 15% (non agevolata)."""

    def test_aliquota_15(self):
        inp = _make_input(regime_agevolato=False)
        result = calcola(inp)
        assert result.aliquota == Decimal("0.15")
        # 31200 * 0.15 = 4680
        assert result.imposta_sostitutiva == Decimal("4680.00")


class TestF24Entries:
    """Test: F24 entries generation."""

    def test_primo_anno_no_acconti_f24(self):
        result = calcola(_make_input())
        # Primo anno: solo saldo, no acconti
        codici = [e.codice_tributo for e in result.f24_entries]
        assert "1792" in codici  # saldo
        assert "1790" not in codici  # no acconto 1
        assert "1791" not in codici  # no acconto 2

    def test_anno_successivo_f24(self):
        inp = _make_input(
            primo_anno=False,
            imposta_anno_precedente=Decimal("3510"),
        )
        result = calcola(inp)
        codici = [e.codice_tributo for e in result.f24_entries]
        assert "1792" in codici
        assert "1790" in codici
        assert "1791" in codici

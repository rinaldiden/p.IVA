"""Test suite for Agent3b Validator — validation OK + block on divergence."""

from decimal import Decimal

from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput
from agents.agent3b_validator.models import InputFiscale
from agents.agent3b_validator.validator import validate


def _make_agent3_input(**overrides) -> ContribuenteInput:
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


def _make_agent3b_input(**overrides) -> InputFiscale:
    defaults = {
        "id_contribuente": "TEST001",
        "anno": 2024,
        "is_primo_anno": True,
        "ricavi_per_ateco": {"74.90.99": Decimal("40000")},
        "rivalsa_4_percento": Decimal("0"),
        "aliquota_agevolata": True,
        "tipo_gestione_inps": "separata",
        "ha_riduzione_35": False,
        "inps_gia_versati": Decimal("0"),
        "imposta_anno_prima": Decimal("0"),
        "acconti_gia_versati": Decimal("0"),
        "crediti_da_prima": Decimal("0"),
    }
    defaults.update(overrides)
    return InputFiscale(**defaults)


def _result_to_dict(result) -> dict:
    """Convert CalcoloResult to dict as it would be serialized."""
    return {
        "reddito_lordo": str(result.reddito_lordo),
        "reddito_imponibile": str(result.reddito_imponibile),
        "imposta_sostitutiva": str(result.imposta_sostitutiva),
        "acconti_dovuti": str(result.acconti_dovuti),
        "acconto_prima_rata": str(result.acconto_prima_rata),
        "acconto_seconda_rata": str(result.acconto_seconda_rata),
        "da_versare": str(result.da_versare),
        "credito_anno_prossimo": str(result.credito_anno_prossimo),
        "contributo_inps_calcolato": str(result.contributo_inps_calcolato),
        "checksum": result.checksum,
    }


class TestValidazioneOK:
    """Test 7: Agent3b validates Agent3's correct results → no divergence."""

    def test_validation_passes(self):
        a3_result = calcola(_make_agent3_input())
        a3_dict = _result_to_dict(a3_result)
        a3b_input = _make_agent3b_input()

        esito = validate(a3b_input, a3_dict)

        assert esito.valid is True
        assert esito.blocco is False
        assert len(esito.divergenze) == 0
        assert esito.checksum_ok is True

    def test_validation_multi_ateco(self):
        a3_result = calcola(_make_agent3_input(
            ateco_ricavi={
                "62.01.00": Decimal("30000"),
                "47.11.40": Decimal("20000"),
            },
        ))
        a3_dict = _result_to_dict(a3_result)
        a3b_input = _make_agent3b_input(
            ricavi_per_ateco={
                "62.01.00": Decimal("30000"),
                "47.11.40": Decimal("20000"),
            },
        )

        esito = validate(a3b_input, a3_dict)
        assert esito.valid is True
        assert esito.blocco is False

    def test_validation_anno_successivo(self):
        a3_result = calcola(_make_agent3_input(
            primo_anno=False,
            ateco_ricavi={"74.90.99": Decimal("50000")},
            imposta_anno_precedente=Decimal("3510"),
        ))
        a3_dict = _result_to_dict(a3_result)
        a3b_input = _make_agent3b_input(
            is_primo_anno=False,
            ricavi_per_ateco={"74.90.99": Decimal("50000")},
            imposta_anno_prima=Decimal("3510"),
        )

        esito = validate(a3b_input, a3_dict)
        assert esito.valid is True
        assert esito.blocco is False


class TestBloccoSuDivergenza:
    """Test 8: Agent3b blocks on even 1 cent divergence."""

    def test_blocco_un_centesimo(self):
        a3_result = calcola(_make_agent3_input())
        a3_dict = _result_to_dict(a3_result)

        # Tamper: add 0.01 to reddito_lordo
        original = Decimal(a3_dict["reddito_lordo"])
        a3_dict["reddito_lordo"] = str(original + Decimal("0.01"))

        a3b_input = _make_agent3b_input()
        esito = validate(a3b_input, a3_dict)

        assert esito.valid is False
        assert esito.blocco is True
        assert len(esito.divergenze) >= 1
        campi = [d.campo for d in esito.divergenze]
        assert "reddito_lordo" in campi

    def test_blocco_checksum_mismatch(self):
        a3_result = calcola(_make_agent3_input())
        a3_dict = _result_to_dict(a3_result)

        # Tamper checksum only
        a3_dict["checksum"] = "0" * 64

        a3b_input = _make_agent3b_input()
        esito = validate(a3b_input, a3_dict)

        assert esito.valid is False
        assert esito.blocco is True
        assert esito.checksum_ok is False

    def test_blocco_imposta_errata(self):
        a3_result = calcola(_make_agent3_input())
        a3_dict = _result_to_dict(a3_result)

        # Tamper: wrong imposta
        a3_dict["imposta_sostitutiva"] = "9999.99"

        a3b_input = _make_agent3b_input()
        esito = validate(a3b_input, a3_dict)

        assert esito.valid is False
        assert esito.blocco is True

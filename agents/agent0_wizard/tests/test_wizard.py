"""Test suite for Agent0 Wizard — 7 test cases."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from agents.agent0_wizard.models import (
    ATECOSuggestion,
    ProfiloContribuente,
    SimulationResult,
)
from agents.agent0_wizard.simulator import simulate, SimulationError


def _make_profilo(**overrides) -> ProfiloContribuente:
    defaults = {
        "contribuente_id": "test-001",
        "nome": "Mario",
        "cognome": "Rossi",
        "codice_fiscale": "RSSMRA80A01H501Z",
        "comune_residenza": "Roma",
        "data_apertura_piva": date(2024, 3, 1),
        "primo_anno": True,
        "ateco_principale": "74.90.99",
        "ateco_secondari": [],
        "regime_agevolato": True,
        "gestione_inps": "separata",
        "riduzione_inps_35": False,
        "rivalsa_inps_4": False,
    }
    defaults.update(overrides)
    return ProfiloContribuente(**defaults)


class TestSimulazionePrimoAnno:
    """Test 1: Simulazione primo anno consulente.
    40.000€, ATECO 74.90.99, 5%, INPS separata, primo_anno=True.
    Atteso: acconti=0, rata mensile corretta, scadenze solo saldo.
    """

    def test_acconti_zero(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        assert sim.acconti_dovuti == Decimal("0")
        assert sim.acconto_prima_rata == Decimal("0")
        assert sim.acconto_seconda_rata == Decimal("0")

    def test_rata_mensile(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        totale = sim.imposta_sostitutiva + sim.contributo_inps
        atteso = (totale / Decimal("12")).quantize(Decimal("0.01"))
        assert sim.rata_mensile_da_accantonare == atteso

    def test_scadenze_solo_saldo(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        # Primo anno: no acconto entries
        descrizioni = [s.descrizione for s in sim.scadenze_anno_corrente]
        assert not any("Acconto" in d for d in descrizioni)

    def test_valori_base(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        # 40000 * 0.78 = 31200
        assert sim.reddito_lordo == Decimal("31200.00")
        assert sim.reddito_imponibile == Decimal("31200.00")
        # 31200 * 0.05 = 1560
        assert sim.imposta_sostitutiva == Decimal("1560.00")


class TestSimulazioneAnnoSuccessivo:
    """Test 2: Simulazione anno successivo.
    50.000€, imposta_anno_prec=3.510€.
    Atteso: scadenzario con acconti giugno e novembre.
    """

    def test_scadenze_con_acconti(self):
        profilo = _make_profilo(
            primo_anno=False,
            data_apertura_piva=date(2022, 1, 15),
        )
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("50000")},
            imposta_anno_prec=Decimal("3510"),
            anno_fiscale=2024,
        )
        descrizioni = [s.descrizione for s in sim.scadenze_anno_corrente]
        assert any("1ª rata" in d for d in descrizioni)
        assert any("2ª rata" in d for d in descrizioni)

    def test_acconti_importi(self):
        profilo = _make_profilo(
            primo_anno=False,
            data_apertura_piva=date(2022, 1, 15),
        )
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("50000")},
            imposta_anno_prec=Decimal("3510"),
            anno_fiscale=2024,
        )
        assert sim.acconto_prima_rata == Decimal("1404.00")
        assert sim.acconto_seconda_rata == Decimal("2106.00")


class TestRivalsaINPS:
    """Test 3: Rivalsa INPS flag attivo.
    Gestione separata, rivalsa_inps_4=True, ricavi=40.000€.
    Atteso: profilo.rivalsa_inps_4=True, calcolo non alterato.
    """

    def test_rivalsa_flag(self):
        profilo = _make_profilo(rivalsa_inps_4=True)
        assert profilo.rivalsa_inps_4 is True

    def test_calcolo_non_alterato(self):
        profilo_senza = _make_profilo(rivalsa_inps_4=False)
        profilo_con = _make_profilo(rivalsa_inps_4=True)

        sim_senza = simulate(
            profilo=profilo_senza,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        sim_con = simulate(
            profilo=profilo_con,
            ricavi_per_ateco={"74.90.99": Decimal("40000")},
            anno_fiscale=2024,
        )
        assert sim_senza.imposta_sostitutiva == sim_con.imposta_sostitutiva
        assert sim_senza.reddito_imponibile == sim_con.reddito_imponibile


class TestSogliaRicavi:
    """Test 4: Soglia ricavi alta — warning.
    Ricavi stimati=82.000€.
    Atteso: warning soglia presente nell'output simulazione.
    """

    def test_warning_presente(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("82000")},
            anno_fiscale=2024,
        )
        assert len(sim.warnings) >= 1
        assert any("85.000" in w or "soglia" in w.lower() for w in sim.warnings)


class TestSuggerimentoATECO:
    """Test 5: Suggerimento ATECO via Claude API (mock)."""

    @patch("agents.agent0_wizard.explainer._call_claude")
    def test_suggest_ateco(self, mock_claude):
        mock_claude.return_value = (
            '[{"codice": "62.01.00", "descrizione": "Sviluppo software", '
            '"coefficiente": "0.78", "motivazione": "Sviluppo app mobile"}]'
        )

        from agents.agent0_wizard.explainer import suggest_ateco

        risultati = suggest_ateco("sviluppo applicazioni mobile per clienti aziendali")
        assert len(risultati) >= 1
        codici = [r.codice for r in risultati]
        assert "62.01.00" in codici


class TestConfrontoRegimi:
    """Test 6: Confronto regimi.
    60.000€ ricavi. Atteso: risparmio_forfettario > 0.
    """

    def test_risparmio_positivo(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("60000")},
            anno_fiscale=2024,
        )
        assert sim.risparmio_vs_ordinario > Decimal("0")

    def test_confronto_struttura(self):
        profilo = _make_profilo()
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={"74.90.99": Decimal("60000")},
            anno_fiscale=2024,
        )
        assert "forfettario" in sim.confronto_regimi
        assert "ordinario_stimato" in sim.confronto_regimi
        assert "risparmio_forfettario" in sim.confronto_regimi


class TestMultiATECO:
    """Test 7: Multi-ATECO.
    30.000€ su 62.01.00 + 15.000€ su 74.90.99.
    Atteso: calcolo corretto su entrambi gli ATECO.
    """

    def test_multi_ateco_calcolo(self):
        profilo = _make_profilo(
            ateco_principale="62.01.00",
            ateco_secondari=["74.90.99"],
        )
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={
                "62.01.00": Decimal("30000"),
                "74.90.99": Decimal("15000"),
            },
            anno_fiscale=2024,
        )
        # 30000*0.78 + 15000*0.78 = 23400 + 11700 = 35100
        assert sim.reddito_lordo == Decimal("35100.00")
        assert sim.ricavi_totali == Decimal("45000.00")

    def test_multi_ateco_dettaglio(self):
        profilo = _make_profilo(
            ateco_principale="62.01.00",
            ateco_secondari=["74.90.99"],
        )
        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco={
                "62.01.00": Decimal("30000"),
                "74.90.99": Decimal("15000"),
            },
            anno_fiscale=2024,
        )
        assert len(sim.dettaglio_ateco) == 2

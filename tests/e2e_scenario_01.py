"""E2E Scenario 01: Onboarding → Calcolo → Validazione → Persistence.

Tests the full core flow without external services (no Redis, no Claude).
This is the critical path: if this breaks, nothing works.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from agents.agent0_wizard.models import ProfiloContribuente
from agents.agent0_wizard.simulator import simulate, SimulationError
from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput
from agents.agent3b_validator.models import InputFiscale
from agents.agent3b_validator.validator import validate
from agents.supervisor.persistence import SupervisorStore


class TestE2EConsulentePrimoAnno:
    """Full flow: new consultant, first year, 50k revenue."""

    @pytest.fixture
    def profilo(self) -> ProfiloContribuente:
        return ProfiloContribuente(
            contribuente_id="e2e-consulente-001",
            nome="Marco",
            cognome="Bianchi",
            codice_fiscale="BNCMRC90A01H501X",
            comune_residenza="Roma",
            data_apertura_piva=date(2024, 3, 1),
            primo_anno=True,
            ateco_principale="62.01",
            ateco_secondari=[],
            regime_agevolato=True,
            gestione_inps="separata",
        )

    @pytest.fixture
    def ricavi(self) -> dict[str, Decimal]:
        return {"62.01": Decimal("50000")}

    def test_full_flow(self, profilo, ricavi, tmp_path):
        """Onboarding → Agent3 → Agent3b → Supervisor: everything connects."""

        # === STEP 1: Simulation (wraps Agent3 + Agent3b) ===
        sim = simulate(profilo=profilo, ricavi_per_ateco=ricavi, anno_fiscale=2024)

        # Core values must be present and consistent
        assert sim.ricavi_totali == Decimal("50000")
        assert sim.reddito_lordo > Decimal("0")
        assert sim.imposta_sostitutiva > Decimal("0")
        assert sim.contributo_inps > Decimal("0")
        assert sim.aliquota == Decimal("0.05")  # primo anno agevolato
        assert sim.checksum  # non-empty

        # First year: zero advances
        assert sim.acconto_prima_rata == Decimal("0")
        assert sim.acconto_seconda_rata == Decimal("0")

        # Monthly savings must be positive
        assert sim.rata_mensile_da_accantonare > Decimal("0")

        # Regime comparison
        assert sim.risparmio_vs_ordinario > Decimal("0")  # forfettario wins

        # Schedule must have entries
        assert len(sim.scadenze_anno_corrente) >= 1

        # === STEP 2: Independent Agent3 calculation ===
        a3_input = ContribuenteInput(
            contribuente_id=profilo.contribuente_id,
            anno_fiscale=2024,
            primo_anno=True,
            ateco_ricavi=ricavi,
            rivalsa_inps_applicata=Decimal("0"),
            regime_agevolato=True,
            gestione_inps="separata",
            riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"),
            imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"),
            crediti_precedenti=Decimal("0"),
        )
        result = calcola(a3_input)
        assert result.checksum == sim.checksum  # Must match simulator

        # === STEP 3: Independent Agent3b validation ===
        a3b_input = InputFiscale(
            id_contribuente=profilo.contribuente_id,
            anno=2024,
            is_primo_anno=True,
            ricavi_per_ateco=ricavi,
            rivalsa_4_percento=Decimal("0"),
            aliquota_agevolata=True,
            tipo_gestione_inps="separata",
            ha_riduzione_35=False,
            inps_gia_versati=Decimal("0"),
            imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"),
            crediti_da_prima=Decimal("0"),
        )
        a3_dict = {
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
        esito = validate(a3b_input, a3_dict)
        assert esito.valid is True
        assert esito.blocco is False
        assert len(esito.divergenze) == 0

        # === STEP 4: Persist to Supervisor ===
        store = SupervisorStore(storage_dir=tmp_path)
        store.save_from_agent0(asdict(profilo))

        # Verify persistence
        saved = store.get_profile(profilo.contribuente_id)
        assert saved is not None
        assert saved["anagrafica"]["codice_fiscale"] == "BNCMRC90A01H501X"
        assert saved["piva"]["ateco_principale"] == "62.01"

        # Verify survives "restart"
        store2 = SupervisorStore(storage_dir=tmp_path)
        assert store2.get_profile(profilo.contribuente_id) is not None


class TestE2EArtigianoMultiAteco:
    """Full flow: artisan, second year, multi-ATECO, riduzione 35%."""

    def test_full_flow(self, tmp_path):
        profilo = ProfiloContribuente(
            contribuente_id="e2e-artigiano-001",
            nome="Giuseppe",
            cognome="Verdi",
            codice_fiscale="VRDGPP85M01F205Z",
            comune_residenza="Milano",
            data_apertura_piva=date(2022, 1, 10),
            primo_anno=False,
            ateco_principale="43.21",
            ateco_secondari=["43.29"],
            regime_agevolato=False,
            gestione_inps="artigiani",
            riduzione_inps_35=True,
        )
        ricavi = {
            "43.21": Decimal("40000"),
            "43.29": Decimal("20000"),
        }

        sim = simulate(
            profilo=profilo,
            ricavi_per_ateco=ricavi,
            imposta_anno_prec=Decimal("3000"),
            anno_fiscale=2024,
        )

        # Second year: must have advances
        assert sim.aliquota == Decimal("0.15")  # non agevolato
        assert sim.acconto_prima_rata > Decimal("0")
        assert sim.acconto_seconda_rata > Decimal("0")

        # Multi-ATECO: both must appear
        assert len(sim.dettaglio_ateco) == 2

        # INPS artigiani with riduzione 35%
        assert sim.contributo_inps > Decimal("0")

        # Persist
        store = SupervisorStore(storage_dir=tmp_path)
        store.save_from_agent0(asdict(profilo))
        assert store.get_profile(profilo.contribuente_id)["inps"]["riduzione_35"] is True


class TestE2EValidationBlock:
    """Agent3b must block on tampered data."""

    def test_tampered_checksum_blocks(self):
        profilo = ProfiloContribuente(
            contribuente_id="e2e-tamper-001",
            nome="Test",
            cognome="Tamper",
            codice_fiscale="TMPTST90A01H501X",
            comune_residenza="Roma",
            data_apertura_piva=date(2024, 1, 1),
            primo_anno=True,
            ateco_principale="62.01",
            regime_agevolato=True,
            gestione_inps="separata",
        )
        ricavi = {"62.01": Decimal("30000")}

        a3_input = ContribuenteInput(
            contribuente_id=profilo.contribuente_id,
            anno_fiscale=2024,
            primo_anno=True,
            ateco_ricavi=ricavi,
            rivalsa_inps_applicata=Decimal("0"),
            regime_agevolato=True,
            gestione_inps="separata",
            riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"),
            imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"),
            crediti_precedenti=Decimal("0"),
        )
        result = calcola(a3_input)

        # Tamper with the amount
        a3_dict = {
            "reddito_lordo": str(result.reddito_lordo),
            "reddito_imponibile": str(result.reddito_imponibile),
            "imposta_sostitutiva": str(result.imposta_sostitutiva + Decimal("0.01")),
            "acconti_dovuti": str(result.acconti_dovuti),
            "acconto_prima_rata": str(result.acconto_prima_rata),
            "acconto_seconda_rata": str(result.acconto_seconda_rata),
            "da_versare": str(result.da_versare),
            "credito_anno_prossimo": str(result.credito_anno_prossimo),
            "contributo_inps_calcolato": str(result.contributo_inps_calcolato),
            "checksum": result.checksum,
        }

        a3b_input = InputFiscale(
            id_contribuente=profilo.contribuente_id,
            anno=2024,
            is_primo_anno=True,
            ricavi_per_ateco=ricavi,
            rivalsa_4_percento=Decimal("0"),
            aliquota_agevolata=True,
            tipo_gestione_inps="separata",
            ha_riduzione_35=False,
            inps_gia_versati=Decimal("0"),
            imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"),
            crediti_da_prima=Decimal("0"),
        )

        esito = validate(a3b_input, a3_dict)
        assert esito.blocco is True
        assert len(esito.divergenze) >= 1


class TestE2ENormativeAudit:
    """Agent10 diff engine + audit integration."""

    def test_diff_and_audit(self):
        from agents.agent10_normative.diff_engine import (
            compute_diff,
            filter_needs_review,
        )
        from agents.agent10_normative.models import ParameterChange

        changes = [
            ParameterChange(
                nome_parametro="forfettario_limits.soglia_ricavi",
                file_destinazione="shared/forfettario_limits.json",
                valore_precedente="85000",
                valore_nuovo="90000",
                data_efficacia=date(2025, 1, 1),
                norma_riferimento="Legge di Bilancio 2025",
                certezza="alta",
                url_fonte="https://example.com",
            ),
            ParameterChange(
                nome_parametro="forfettario_limits.aliquota_ordinaria",
                file_destinazione="shared/forfettario_limits.json",
                valore_precedente="0.15",
                valore_nuovo="0.15",  # no change
                data_efficacia=date(2025, 1, 1),
                norma_riferimento="Legge di Bilancio 2025",
                certezza="bassa",
                url_fonte="https://example.com",
            ),
        ]

        # Diff should filter out unchanged
        real = compute_diff(changes)
        assert len(real) == 1
        assert real[0].valore_nuovo == "90000"

        # Filter: only alta goes to auto
        auto, review = filter_needs_review(real, anomaly_threshold_pct=50.0)
        assert len(auto) == 1
        assert len(review) == 0

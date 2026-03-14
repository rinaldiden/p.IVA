"""Root conftest — shared fixtures for all test suites."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agents.agent0_wizard.models import ProfiloContribuente


@pytest.fixture
def profilo_base() -> ProfiloContribuente:
    """Standard contribuente profile for testing."""
    return ProfiloContribuente(
        contribuente_id="test-contribuente-001",
        nome="Mario",
        cognome="Rossi",
        codice_fiscale="RSSMRA85M01H501Z",
        comune_residenza="Roma",
        data_apertura_piva=date(2024, 3, 15),
        primo_anno=True,
        ateco_principale="62.01",
        ateco_secondari=[],
        regime_agevolato=True,
        gestione_inps="separata",
        riduzione_inps_35=False,
        rivalsa_inps_4=False,
    )


@pytest.fixture
def profilo_artigiano() -> ProfiloContribuente:
    """Artigiano profile for testing."""
    return ProfiloContribuente(
        contribuente_id="test-contribuente-002",
        nome="Luigi",
        cognome="Verdi",
        codice_fiscale="VRDLGU90A01F205X",
        comune_residenza="Milano",
        data_apertura_piva=date(2022, 1, 10),
        primo_anno=False,
        ateco_principale="43.21",
        ateco_secondari=[],
        regime_agevolato=False,
        gestione_inps="artigiani",
        riduzione_inps_35=True,
        rivalsa_inps_4=False,
    )


@pytest.fixture
def ricavi_consulente() -> dict[str, Decimal]:
    """Standard consulting revenue for tests."""
    return {"62.01": Decimal("50000")}


@pytest.fixture
def ricavi_multi_ateco() -> dict[str, Decimal]:
    """Multi-ATECO revenue for tests."""
    return {
        "62.01": Decimal("35000"),
        "73.11": Decimal("15000"),
    }

"""Test suite for Agent4 Compliance Monitor — 10 test cases."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from agents.agent4_compliance.compliance import (
    check_anomalie,
    check_compliance,
    check_scadenze,
    check_soglia_85k,
    genera_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fatture(importi, anno=2025, cliente="Cliente A", start_num=1):
    """Generate a list of invoice dicts."""
    fatture = []
    for i, importo in enumerate(importi):
        fatture.append({
            "numero": f"{start_num + i}",
            "importo": str(importo),
            "data": f"{anno}-{(i % 12) + 1:02d}-15",
            "cliente": cliente,
        })
    return fatture


def _make_profile(**overrides):
    """Create a minimal profile dict."""
    profile = {
        "contribuente_id": "TEST001",
        "anagrafica": {
            "codice_fiscale": "RSSMRA80A01H501Z",
            "ateco_principale": "62.01.00",
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
# Test: Soglia 85k
# ---------------------------------------------------------------------------

class TestSoglia85k:
    """Tests for revenue threshold monitoring."""

    def test_well_below_threshold(self):
        fatture = _make_fatture([Decimal("5000")] * 6, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.livello_alert == "ok"
        assert result.fatturato_corrente == Decimal("30000.00")
        assert not result.superata

    def test_warning_at_70_percent(self):
        # 70% of 85000 = 59500
        fatture = _make_fatture([Decimal("10000")] * 6, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.fatturato_corrente == Decimal("60000.00")
        assert result.livello_alert == "warning_70"

    def test_warning_at_80_percent(self):
        # 80% of 85000 = 68000
        fatture = _make_fatture([Decimal("14000")] * 5, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.fatturato_corrente == Decimal("70000.00")
        assert result.livello_alert == "warning_80"

    def test_warning_at_90_percent(self):
        fatture = _make_fatture([Decimal("16000")] * 5, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.fatturato_corrente == Decimal("80000.00")
        assert result.livello_alert == "warning_90"

    def test_critical_threshold_exceeded(self):
        fatture = _make_fatture([Decimal("9000")] * 10, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.fatturato_corrente == Decimal("90000.00")
        assert result.livello_alert == "critical"
        assert result.superata
        assert "2026" in result.messaggio

    def test_projection_calculation(self):
        # 6 months of 8000 = 48000, projection = 96000
        fatture = _make_fatture([Decimal("8000")] * 6, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.proiezione_annua == Decimal("96000.00")
        assert result.mese_proiezione == 6

    def test_filters_by_year(self):
        fatture = _make_fatture([Decimal("40000")] * 2, anno=2024)
        fatture += _make_fatture([Decimal("5000")] * 2, anno=2025)
        result = check_soglia_85k(fatture, 2025)
        assert result.fatturato_corrente == Decimal("10000.00")


# ---------------------------------------------------------------------------
# Test: Anomalie
# ---------------------------------------------------------------------------

class TestAnomalie:
    """Tests for anomaly detection."""

    def test_client_concentration_over_50_percent(self):
        fatture = [
            {"numero": "1", "importo": "8000", "cliente": "Big Client"},
            {"numero": "2", "importo": "1000", "cliente": "Small Client A"},
            {"numero": "3", "importo": "1000", "cliente": "Small Client B"},
        ]
        anomalie = check_anomalie(fatture)
        concentration = [a for a in anomalie if a.tipo == "concentrazione_cliente"]
        assert len(concentration) == 1
        assert "Big Client" in concentration[0].descrizione
        assert concentration[0].severita == "warning"

    def test_no_concentration_anomaly(self):
        fatture = [
            {"numero": "1", "importo": "3000", "cliente": "A"},
            {"numero": "2", "importo": "3000", "cliente": "B"},
            {"numero": "3", "importo": "4000", "cliente": "C"},
        ]
        anomalie = check_anomalie(fatture)
        concentration = [a for a in anomalie if a.tipo == "concentrazione_cliente"]
        assert len(concentration) == 0

    def test_numbering_gap(self):
        fatture = [
            {"numero": "1", "importo": "1000", "cliente": "A"},
            {"numero": "2", "importo": "1000", "cliente": "A"},
            {"numero": "5", "importo": "1000", "cliente": "A"},
        ]
        anomalie = check_anomalie(fatture)
        gaps = [a for a in anomalie if a.tipo == "gap_numerazione"]
        assert len(gaps) == 1
        assert gaps[0].dettaglio["numeri_mancanti"] == 2

    def test_unusually_large_invoice(self):
        fatture = [
            {"numero": "1", "importo": "1000", "cliente": "A"},
            {"numero": "2", "importo": "1000", "cliente": "B"},
            {"numero": "3", "importo": "1000", "cliente": "C"},
            {"numero": "4", "importo": "10000", "cliente": "D"},
        ]
        anomalie = check_anomalie(fatture)
        anomalo = [a for a in anomalie if a.tipo == "importo_anomalo"]
        assert len(anomalo) >= 1

    def test_empty_fatture(self):
        assert check_anomalie([]) == []


# ---------------------------------------------------------------------------
# Test: Scadenze
# ---------------------------------------------------------------------------

class TestScadenze:
    """Tests for deadline compliance."""

    def test_primo_anno_no_acconti(self):
        profile = _make_profile()
        scadenze = check_scadenze(profile, 2025)
        acconto_ids = [s.scadenza_id for s in scadenze if "acconto" in s.scadenza_id]
        assert len(acconto_ids) == 0

    def test_artigiani_has_quarterly(self):
        profile = _make_profile()
        profile["anagrafica"]["gestione_inps"] = "artigiani"
        profile["anagrafica"]["primo_anno"] = False
        scadenze = check_scadenze(profile, 2025)
        fisso_ids = [s.scadenza_id for s in scadenze if "fisso_q" in s.scadenza_id]
        assert len(fisso_ids) == 4

    def test_scadenza_dichiarazione_included(self):
        profile = _make_profile()
        scadenze = check_scadenze(profile, 2025)
        dichiarazione = [s for s in scadenze if s.scadenza_id == "invio_redditi_pf"]
        assert len(dichiarazione) == 1


# ---------------------------------------------------------------------------
# Test: Full compliance + alerts
# ---------------------------------------------------------------------------

class TestFullCompliance:
    """Tests for the full compliance check and alert generation."""

    def test_clean_profile_ok_status(self):
        # Use current year, small amounts with bollo, different clients
        anno = 2025
        fatture = [
            {"numero": "1", "importo": "3000", "data": f"{anno}-01-15",
             "cliente": "A", "bollo": True},
            {"numero": "2", "importo": "3000", "data": f"{anno}-02-15",
             "cliente": "B", "bollo": True},
            {"numero": "3", "importo": "2000", "data": f"{anno}-03-15",
             "cliente": "C", "bollo": True},
            {"numero": "4", "importo": "2000", "data": f"{anno}-04-15",
             "cliente": "D", "bollo": True},
        ]
        profile = _make_profile(fatture=fatture)
        # Mark all past scadenze as paid
        profile["pagamenti"] = [
            {"scadenza_id": "saldo_imposta", "anno": anno, "importo": "100", "tipo": "imposta"},
        ]
        report = check_compliance(profile, anno)
        # Soglia should be OK at 10k, no bollo issues, no concentration
        assert report.soglia.livello_alert == "ok"
        assert all(b.conforme for b in report.bolli)
        anomalie_gravi = [a for a in report.anomalie if a.severita in ("warning", "critical")]
        assert len(anomalie_gravi) == 0

    def test_high_revenue_generates_alerts(self):
        profile = _make_profile(fatture=_make_fatture([Decimal("9000")] * 10, anno=2025))
        report = check_compliance(profile, 2025)
        assert report.overall_status == "critical"
        alerts = genera_alert(report)
        soglia_alerts = [a for a in alerts if a["type"] == "soglia_85k"]
        assert len(soglia_alerts) == 1
        assert soglia_alerts[0]["priority"] == "high"

    def test_bollo_mancante_generates_alert(self):
        fatture = [
            {"numero": "1", "importo": "100.00", "data": "2025-03-15", "cliente": "A", "bollo": False},
            {"numero": "2", "importo": "50.00", "data": "2025-04-15", "cliente": "B"},
        ]
        profile = _make_profile(fatture=fatture)
        report = check_compliance(profile, 2025)
        bolli_non_conformi = [b for b in report.bolli if not b.conforme]
        assert len(bolli_non_conformi) == 1
        assert bolli_non_conformi[0].numero_fattura == "1"

        alerts = genera_alert(report)
        bollo_alerts = [a for a in alerts if a["type"] == "bollo_mancante"]
        assert len(bollo_alerts) == 1

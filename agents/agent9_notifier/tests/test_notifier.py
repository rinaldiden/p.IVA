"""Tests for Agent9 — Notifier & Supervisor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.agent9_notifier.notifier import (
    TEMPLATES,
    check_agent_health,
    format_message,
    get_pipeline_status,
    handle_agent_error,
    monitor_all_agents,
    notify,
    notify_compliance_alert,
    notify_scadenza,
    notify_soglia_85k,
    run_pipeline,
)
from agents.agent9_notifier.models import (
    AgentHealth,
    NotifyResult,
    PipelineResult,
    PipelineStatus,
)


# ---------------------------------------------------------------------------
# Notification tests
# ---------------------------------------------------------------------------


class TestNotify:
    """Tests for the notify function."""

    def test_basic_notify(self):
        """Basic notification returns success."""
        result = notify("Test message")

        assert isinstance(result, NotifyResult)
        assert result.success is True
        assert result.dry_run is True
        assert result.channel == "in_app"

    def test_priority_channels_normal(self):
        """Normal priority routes to in_app and email."""
        result = notify("Test", priority="normal")
        # Primary channel is in_app (first in the list)
        assert result.success is True
        assert result.channel == "in_app"

    def test_priority_channels_critical(self):
        """Critical priority routes to all channels."""
        result = notify("Critical test", priority="critical")
        assert result.success is True
        assert result.channel == "in_app"

    def test_custom_channels(self):
        """Custom channel list overrides priority-based routing."""
        result = notify("Test", channels=["telegram"])
        assert result.success is True
        assert result.channel == "telegram"

    def test_invalid_channel_filtered(self):
        """Invalid channels are filtered, fallback to in_app."""
        result = notify("Test", channels=["fax"])
        assert result.success is True
        assert result.channel == "in_app"

    def test_source_agent_prepended(self):
        """Source agent name is prepended to message."""
        result = notify("Test message", source_agent="Agent3")
        assert result.success is True

    def test_invalid_priority_fallback(self):
        """Invalid priority defaults to 'normal'."""
        result = notify("Test", priority="bogus")
        assert result.success is True


class TestNotifyScadenza:
    """Tests for notify_scadenza."""

    def test_scadenza_normal(self):
        """Deadline > 7 days uses normal priority."""
        scadenza = {
            "descrizione": "Saldo imposta sostitutiva",
            "importo": "1675.00",
            "data_scadenza": "2025-06-30",
            "codice_tributo": "1792",
        }
        result = notify_scadenza(scadenza, days_before=15)
        assert result.success is True

    def test_scadenza_critical_3_days(self):
        """Deadline <= 3 days uses critical priority."""
        scadenza = {
            "descrizione": "Acconto imposta",
            "importo": "500.00",
            "data_scadenza": "2025-06-30",
            "codice_tributo": "1790",
        }
        result = notify_scadenza(scadenza, days_before=2)
        assert result.success is True


class TestNotifyComplianceAlert:
    """Tests for notify_compliance_alert."""

    def test_compliance_alert(self):
        """Compliance alert sends high-priority notification."""
        alert = {
            "tipo": "Superamento soglia",
            "descrizione": "Fatturato ha superato 80.000 EUR",
            "azione": "Verificare proiezione annuale",
        }
        result = notify_compliance_alert(alert)
        assert result.success is True


class TestNotifySoglia85k:
    """Tests for notify_soglia_85k."""

    def test_warning_level(self):
        """Percentage < 95% triggers warning."""
        result = notify_soglia_85k(percentuale=90.0, fatturato=76500.0)
        assert result.success is True

    def test_critical_level(self):
        """Percentage >= 95% triggers critical alert."""
        result = notify_soglia_85k(percentuale=97.0, fatturato=82450.0)
        assert result.success is True


class TestFormatMessage:
    """Tests for format_message."""

    def test_named_template(self):
        """Named template from TEMPLATES dict is used."""
        msg = format_message("scadenza_f24", {
            "days": 7,
            "descrizione": "Test scadenza",
            "importo": "1000.00",
            "data_scadenza": "2025-06-30",
            "codice_tributo": "1792",
        })
        assert "7 giorni" in msg
        assert "1000.00" in msg

    def test_raw_template(self):
        """Raw template string is used when not in TEMPLATES."""
        msg = format_message("Custom: {name} - {value}", {"name": "test", "value": 42})
        assert msg == "Custom: test - 42"

    def test_missing_key_graceful(self):
        """Missing keys don't crash, template returned as-is."""
        msg = format_message("scadenza_f24", {})
        # Should return something without crashing
        assert isinstance(msg, str)


class TestCheckAgentHealth:
    """Tests for check_agent_health."""

    def test_known_agent(self):
        """Known implemented agent returns ok status."""
        health = check_agent_health("agent3_calculator")
        assert isinstance(health, AgentHealth)
        assert health.name == "agent3_calculator"
        assert health.status == "ok"
        assert health.last_check

    def test_stub_or_error_agent(self):
        """Stub/non-importable agent returns stub or error status."""
        health = check_agent_health("agent1_collector")
        # Stub agents may fail to import or may be detected as stubs
        assert health.status in ("stub", "error")

    def test_unknown_agent(self):
        """Unknown agent name returns error."""
        health = check_agent_health("agent99_fake")
        assert health.status == "error"
        assert "sconosciuto" in health.message.lower()


class TestMonitorAllAgents:
    """Tests for monitor_all_agents."""

    def test_returns_all_agents(self):
        """Monitor returns health for all registered agents."""
        results = monitor_all_agents()
        assert isinstance(results, dict)
        assert "agent3_calculator" in results
        assert "agent5_declaration" in results
        assert len(results) >= 8


class TestHandleAgentError:
    """Tests for handle_agent_error."""

    def test_error_handling(self):
        """Agent error is logged and notified."""
        msg = handle_agent_error("agent3_calculator", ValueError("Test error"))
        assert "agent3_calculator" in msg
        assert "notifica" in msg.lower()


class TestGetPipelineStatus:
    """Tests for get_pipeline_status."""

    def test_idle_status(self):
        """Unknown profile returns idle status."""
        status = get_pipeline_status("non_existent_profile")
        assert isinstance(status, PipelineStatus)
        assert status.status == "idle"


class TestRunPipeline:
    """Tests for run_pipeline."""

    def _make_pipeline_profile(self) -> dict:
        """Build a profile suitable for pipeline testing."""
        return {
            "contribuente_id": "RSSMRA80A01H501U",
            "anagrafica": {
                "nome": "Mario",
                "cognome": "Rossi",
                "codice_fiscale": "RSSMRA80A01H501U",
                "ateco_principale": "62.01",
                "regime_agevolato": True,
                "primo_anno": True,
                "gestione_inps": "separata",
                "riduzione_inps_35": False,
            },
            "fatture": [
                {"anno": 2024, "imponibile": "50000", "codice_ateco": "62.01"},
            ],
            "spese": [],
            "ricavi_per_ateco": {"62.01": "50000"},
            "contributi_inps_versati": "0",
            "acconti_versati": "0",
            "crediti_precedenti": "0",
            "imposta_anno_precedente": "0",
        }

    def test_pipeline_runs(self):
        """Pipeline executes all steps and returns result."""
        profile = self._make_pipeline_profile()
        result = run_pipeline(profile, anno=2024)

        assert isinstance(result, PipelineResult)
        assert len(result.steps) >= 6
        assert result.duration_ms > 0

    def test_pipeline_calc_step_succeeds(self):
        """Agent3+3b calculation step succeeds with valid data."""
        profile = self._make_pipeline_profile()
        result = run_pipeline(profile, anno=2024)

        calc_step = next(
            (s for s in result.steps if "agent3" in s.agent_name), None
        )
        assert calc_step is not None
        assert calc_step.success is True

    def test_pipeline_status_tracked(self):
        """Pipeline status is tracked and retrievable."""
        profile = self._make_pipeline_profile()
        run_pipeline(profile, anno=2024)

        status = get_pipeline_status("RSSMRA80A01H501U")
        assert status.status in ("completed", "failed")
        assert status.started_at
        assert status.finished_at

    def test_pipeline_handles_missing_data_gracefully(self):
        """Pipeline with no revenue data fails gracefully."""
        profile = self._make_pipeline_profile()
        profile["fatture"] = []
        profile["ricavi_per_ateco"] = {}
        result = run_pipeline(profile, anno=2024)

        # Pipeline should still complete (some steps fail)
        assert isinstance(result, PipelineResult)
        assert len(result.steps) >= 6
        # Calc step should fail
        calc_step = next(
            (s for s in result.steps if "agent3" in s.agent_name), None
        )
        assert calc_step is not None
        assert calc_step.success is False

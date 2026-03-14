"""Test suite for Agent10 NormativeWatcher — 8 test cases."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent10_normative.diff_engine import (
    compute_diff,
    filter_needs_review,
)
from agents.agent10_normative.models import (
    NormativeUpdate,
    ParameterChange,
    RelevanceCheck,
    SourceResult,
)
from agents.agent10_normative.scheduler import NormativeScheduler
from agents.agent10_normative.sources import _matches_keywords, _parse_rss
from agents.agent10_normative.updater import _write_audit, apply_change
from agents.agent10_normative.watcher import NormativeWatcher


# --- Fixtures ---

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Gazzetta Ufficiale</title>
  <item>
    <title>Modifica aliquote contributi INPS gestione separata forfettario 2025</title>
    <link>https://www.gazzettaufficiale.it/atto/123</link>
    <description>Nuove aliquote contributive gestione separata per regime forfettario</description>
    <pubDate>2024-12-15</pubDate>
  </item>
  <item>
    <title>Regolamento sulla pesca nel Mediterraneo</title>
    <link>https://www.gazzettaufficiale.it/atto/456</link>
    <description>Normativa sulla pesca sostenibile</description>
    <pubDate>2024-12-15</pubDate>
  </item>
</channel>
</rss>
"""


def _make_change(**overrides) -> ParameterChange:
    defaults = {
        "nome_parametro": "inps_rates.2025.gestione_separata.aliquota",
        "file_destinazione": "shared/inps_rates.json",
        "valore_precedente": "0.2607",
        "valore_nuovo": "0.2650",
        "data_efficacia": date(2025, 1, 1),
        "norma_riferimento": "Legge di Bilancio 2025",
        "certezza": "alta",
        "url_fonte": "https://example.com",
    }
    defaults.update(overrides)
    return ParameterChange(**defaults)


def _make_update(changes: list[ParameterChange] | None = None, **overrides) -> NormativeUpdate:
    defaults = {
        "update_id": "test-update-001",
        "timestamp_rilevazione": datetime.now(timezone.utc),
        "fonte": "gazzetta_ufficiale",
        "documento_titolo": "Test Document",
        "documento_url": "https://example.com/doc",
        "hash_documento": "abc123",
        "parametri_modificati": changes or [_make_change()],
        "stato": "pending",
    }
    defaults.update(overrides)
    return NormativeUpdate(**defaults)


class TestFetchFiltroGU:
    """Test 1: Fetch e filtro GU.
    Mock RSS con articolo su forfettario.
    Verifica: documento estratto e classificato come rilevante.
    """

    def test_rss_parsing_filters_relevant(self):
        results = _parse_rss(SAMPLE_RSS, fonte="gazzetta_ufficiale")
        # Only the INPS article should match keywords
        assert len(results) == 1
        assert "INPS" in results[0].titolo
        assert results[0].fonte == "gazzetta_ufficiale"

    def test_irrelevant_filtered_out(self):
        results = _parse_rss(SAMPLE_RSS, fonte="gazzetta_ufficiale")
        titoli = [r.titolo for r in results]
        assert not any("pesca" in t.lower() for t in titoli)

    def test_keywords_match(self):
        assert _matches_keywords("Nuova aliquota INPS gestione separata")
        assert _matches_keywords("Modifica soglia ricavi forfettario")
        assert not _matches_keywords("Regolamento pesca Mediterraneo")


class TestEstrazioneParametri:
    """Test 2: Estrazione parametri via LLM (mock Claude API)."""

    def test_extract_parameters(self):
        # Use a value that differs from current but within 5% anomaly threshold
        # soglia_marca_bollo: 77.47 → 78.00 (~0.7% change)
        mock_changes = [
            _make_change(
                nome_parametro="forfettario_limits.soglia_marca_bollo",
                file_destinazione="shared/forfettario_limits.json",
                valore_precedente="77.47",
                valore_nuovo="78.00",
                data_efficacia=date.today() - timedelta(days=1),
                certezza="alta",
            )
        ]

        watcher = NormativeWatcher(
            check_relevance_fn=lambda t: RelevanceCheck(
                rilevante=True,
                parametri_coinvolti=["soglia marca da bollo"],
            ),
            extract_params_fn=lambda t, v: mock_changes,
        )

        doc = SourceResult(
            fonte="gazzetta_ufficiale",
            titolo="Modifica soglia marca da bollo",
            url="https://example.com",
            testo="La soglia per la marca da bollo è portata a 78.00€",
            data_pubblicazione=date(2024, 12, 15),
            hash_documento="testhashbollo",
        )

        # Save original value
        import json
        limits_path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "forfettario_limits.json"
        with open(limits_path, encoding="utf-8") as f:
            original = json.load(f)

        try:
            update = watcher._process_document(doc)
            assert update is not None
            assert update.stato == "applied"
            assert len(update.parametri_modificati) == 1
            assert update.parametri_modificati[0].valore_nuovo == "78.00"
        finally:
            # Restore original
            with open(limits_path, "w", encoding="utf-8") as f:
                json.dump(original, f, indent=2, ensure_ascii=False)
                f.write("\n")


class TestSchedulingFuturo:
    """Test 3: data_efficacia = futuro → schedulato, non applicato subito."""

    def test_future_scheduled(self):
        future_date = date.today() + timedelta(days=30)

        scheduler = NormativeScheduler()
        update = _make_update(
            changes=[_make_change(data_efficacia=future_date)],
        )
        update.data_applicazione = future_date

        scheduler.schedule(update)

        due = scheduler.get_due_updates(as_of=date.today())
        assert len(due) == 0  # Not yet due

        upcoming = scheduler.get_upcoming(within_days=60)
        assert len(upcoming) >= 1

    def test_future_becomes_due(self):
        future_date = date.today() + timedelta(days=30)

        scheduler = NormativeScheduler()
        update = _make_update(
            changes=[_make_change(data_efficacia=future_date)],
        )
        update.data_applicazione = future_date
        scheduler.schedule(update)

        # Check as if it's 31 days from now
        due = scheduler.get_due_updates(as_of=future_date)
        assert len(due) >= 1


class TestApplicazioneImmediata:
    """Test 4: data_efficacia = ieri → applicato subito, file shared/ aggiornato."""

    def test_immediate_application(self):
        # Work on a copy of the shared dir
        shared_dir = Path(__file__).resolve().parent.parent.parent.parent / "shared"
        inps_path = shared_dir / "inps_rates.json"

        if not inps_path.exists():
            pytest.skip("shared/inps_rates.json not found")

        # Read original
        with open(inps_path, encoding="utf-8") as f:
            original = json.load(f)

        # Verify 2024 exists
        assert "2024" in original

        change = _make_change(
            nome_parametro="inps_rates.2024.gestione_separata.test_field",
            file_destinazione="shared/inps_rates.json",
            valore_precedente="",
            valore_nuovo="test_value",
            data_efficacia=date.today() - timedelta(days=1),
        )

        applied = apply_change(change)
        assert applied is True

        # Verify the file was updated
        with open(inps_path, encoding="utf-8") as f:
            updated = json.load(f)
        assert updated["2024"]["gestione_separata"]["test_field"] == "test_value"

        # Cleanup: remove test field
        del updated["2024"]["gestione_separata"]["test_field"]
        with open(inps_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
            f.write("\n")


class TestAuditTrail:
    """Test 5: Audit trail append-only."""

    def test_audit_append_only(self):
        audit_dir = Path(__file__).resolve().parent.parent / "audit"
        changes_file = audit_dir / "changes.jsonl"
        audit_dir.mkdir(parents=True, exist_ok=True)

        # Save existing content
        existing = ""
        if changes_file.exists():
            existing = changes_file.read_text()

        try:
            # Clear for test
            changes_file.write_text("")

            # Write 3 updates
            for i in range(3):
                update = _make_update(
                    update_id=f"audit-test-{i}",
                    changes=[_make_change(
                        nome_parametro=f"test.param_{i}",
                        valore_nuovo=f"value_{i}",
                    )],
                )
                _write_audit(update)

            # Verify
            lines = [
                l for l in changes_file.read_text().strip().split("\n") if l
            ]
            assert len(lines) == 3

            entries = [json.loads(l) for l in lines]
            assert entries[0]["update_id"] == "audit-test-0"
            assert entries[1]["update_id"] == "audit-test-1"
            assert entries[2]["update_id"] == "audit-test-2"

        finally:
            # Restore
            changes_file.write_text(existing)


class TestHumanReview:
    """Test 6: certezza=bassa → non applicato, finisce in review queue."""

    def test_low_confidence_review(self):
        changes = [_make_change(certezza="bassa")]
        auto, review = filter_needs_review(changes)
        assert len(auto) == 0
        assert len(review) == 1
        assert review[0].certezza == "bassa"

    def test_anomalous_change_review(self):
        # 50% change exceeds 5% threshold
        changes = [_make_change(
            valore_precedente="0.15",
            valore_nuovo="0.25",
            certezza="alta",
        )]
        auto, review = filter_needs_review(changes, anomaly_threshold_pct=5.0)
        assert len(auto) == 0
        assert len(review) == 1

    def test_normal_change_auto(self):
        # ~1.6% change, within threshold
        changes = [_make_change(
            valore_precedente="0.2607",
            valore_nuovo="0.2650",
            certezza="alta",
        )]
        auto, review = filter_needs_review(changes, anomaly_threshold_pct=5.0)
        assert len(auto) == 1
        assert len(review) == 0


class TestNonRilevante:
    """Test 7: Documento non rilevante → nessuna modifica."""

    def test_irrelevant_skipped(self):
        watcher = NormativeWatcher(
            check_relevance_fn=lambda t: RelevanceCheck(rilevante=False),
            extract_params_fn=lambda t, v: [],
        )

        doc = SourceResult(
            fonte="gazzetta_ufficiale",
            titolo="Regolamento pesca",
            url="https://example.com/pesca",
            testo="Normativa sulla pesca sostenibile nel Mediterraneo",
            data_pubblicazione=date.today(),
            hash_documento="irrelevanthash",
        )

        result = watcher._process_document(doc)
        assert result is None


class TestDiffEngine:
    """Test: diff engine filters out unchanged values."""

    def test_no_diff_on_same_value(self):
        changes = [_make_change(
            nome_parametro="forfettario_limits.soglia_ricavi",
            valore_precedente="85000",
            valore_nuovo="85000",
        )]
        result = compute_diff(changes)
        assert len(result) == 0

    def test_diff_on_changed_value(self):
        changes = [_make_change(
            nome_parametro="forfettario_limits.soglia_ricavi",
            valore_precedente="85000",
            valore_nuovo="100000",
        )]
        result = compute_diff(changes)
        assert len(result) == 1

"""Tests for SupervisorStore persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agents.supervisor.persistence import SupervisorStore


@pytest.fixture
def store(tmp_path: Path) -> SupervisorStore:
    return SupervisorStore(storage_dir=tmp_path)


@pytest.fixture
def sample_profile() -> dict:
    return {
        "contribuente_id": "test-user-001",
        "nome": "Mario",
        "cognome": "Rossi",
        "codice_fiscale": "RSSMRA85M01H501Z",
        "comune_residenza": "Roma",
        "data_apertura_piva": "2024-01-15",
        "primo_anno": True,
        "ateco_principale": "62.01",
        "ateco_secondari": ["73.11"],
        "regime_agevolato": True,
        "gestione_inps": "separata",
        "riduzione_inps_35": False,
        "rivalsa_inps_4": False,
        "stato": "onboarding",
    }


class TestSaveAndGet:
    def test_save_and_retrieve(self, store: SupervisorStore) -> None:
        store.save_profile("user-1", {"nome": "Mario", "stato": "active"})
        profile = store.get_profile("user-1")
        assert profile is not None
        assert profile["nome"] == "Mario"
        assert "_updated_at" in profile

    def test_get_missing_returns_none(self, store: SupervisorStore) -> None:
        assert store.get_profile("nonexistent") is None

    def test_overwrite_profile(self, store: SupervisorStore) -> None:
        store.save_profile("user-1", {"nome": "Mario"})
        store.save_profile("user-1", {"nome": "Luigi"})
        profile = store.get_profile("user-1")
        assert profile["nome"] == "Luigi"


class TestListAndDelete:
    def test_list_profiles(self, store: SupervisorStore) -> None:
        store.save_profile("user-1", {"nome": "Mario"})
        store.save_profile("user-2", {"nome": "Luigi"})
        ids = store.list_profiles()
        assert set(ids) == {"user-1", "user-2"}

    def test_delete_existing(self, store: SupervisorStore) -> None:
        store.save_profile("user-1", {"nome": "Mario"})
        assert store.delete_profile("user-1") is True
        assert store.get_profile("user-1") is None

    def test_delete_missing(self, store: SupervisorStore) -> None:
        assert store.delete_profile("nonexistent") is False


class TestSaveFromAgent0:
    def test_save_from_agent0(self, store: SupervisorStore, sample_profile: dict) -> None:
        store.save_from_agent0(sample_profile)
        profile = store.get_profile("test-user-001")
        assert profile is not None
        assert profile["anagrafica"]["nome"] == "Mario"
        assert profile["anagrafica"]["cognome"] == "Rossi"
        assert profile["piva"]["ateco_principale"] == "62.01"
        assert profile["regime"]["agevolato"] is True
        assert profile["inps"]["gestione"] == "separata"
        assert profile["_source"] == "agent0_wizard"

    def test_save_from_agent0_missing_id(self, store: SupervisorStore) -> None:
        with pytest.raises(ValueError, match="missing contribuente_id"):
            store.save_from_agent0({"nome": "Senza ID"})

    def test_survives_reload(self, tmp_path: Path, sample_profile: dict) -> None:
        """Profile persists across store instances (simulates restart)."""
        store1 = SupervisorStore(storage_dir=tmp_path)
        store1.save_from_agent0(sample_profile)

        # New instance, same directory
        store2 = SupervisorStore(storage_dir=tmp_path)
        profile = store2.get_profile("test-user-001")
        assert profile is not None
        assert profile["anagrafica"]["codice_fiscale"] == "RSSMRA85M01H501Z"

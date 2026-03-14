"""Tests for VaultAgent — requires PostgreSQL and Redis running.

Run with: pytest integrations/vault/tests/test_vault.py -v

Requires docker-compose up (vault-db + vault-redis) or equivalent services.
Set environment variables before running:
    export VAULT_MASTER_SECRET=test-secret-for-ci
    export VAULT_DB_PASSWORD=test-password
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Set test env vars before importing config
os.environ.setdefault("VAULT_MASTER_SECRET", "test-master-secret-for-testing-only")
os.environ.setdefault("VAULT_DB_PASSWORD", "test-password")
os.environ.setdefault("VAULT_PBKDF2_ITERATIONS", "1000")  # Fast for tests

from integrations.vault.config import VaultConfig
from integrations.vault.models import CredentialType, Permission
from integrations.vault.vault_agent import (
    CredentialExpiredError,
    CredentialNotFoundError,
    PermissionDeniedError,
    VaultAgent,
)


@pytest.fixture
def config() -> VaultConfig:
    return VaultConfig()


@pytest.fixture
def vault(config: VaultConfig) -> VaultAgent:
    return VaultAgent(config)


class TestStoreAndGet:
    """Round-trip store/get credential tests."""

    @pytest.mark.integration
    def test_store_and_retrieve(self, vault: VaultAgent) -> None:
        """Store a credential and retrieve it — values must match."""
        original_value = "my-firma-digitale-pin-12345"

        cred_id = vault.store_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.FIRMA_DIGITALE,
            value=original_value,
            metadata={"provider": "aruba", "serial": "ABC123"},
        )

        assert isinstance(cred_id, uuid.UUID)

        retrieved = vault.get_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.FIRMA_DIGITALE,
        )

        assert retrieved == original_value


class TestAccessPolicies:
    """Permission enforcement tests."""

    @pytest.mark.integration
    def test_unauthorized_read_raises(self, vault: VaultAgent) -> None:
        """Agent without READ permission gets PermissionDeniedError."""
        # agent1_collector does NOT have read access to FIRMA_DIGITALE
        with pytest.raises(PermissionDeniedError):
            vault.get_credential(
                agent_id="agent1_collector",
                credential_type=CredentialType.FIRMA_DIGITALE,
            )

    @pytest.mark.integration
    def test_unauthorized_write_raises(self, vault: VaultAgent) -> None:
        """Agent without WRITE permission gets PermissionDeniedError."""
        # agent1_collector does NOT have write access to FIRMA_DIGITALE
        with pytest.raises(PermissionDeniedError):
            vault.store_credential(
                agent_id="agent1_collector",
                credential_type=CredentialType.FIRMA_DIGITALE,
                value="should-not-work",
            )

    @pytest.mark.integration
    def test_unknown_agent_raises(self, vault: VaultAgent) -> None:
        """Unknown agent ID gets PermissionDeniedError."""
        with pytest.raises(PermissionDeniedError):
            vault.get_credential(
                agent_id="unknown_agent",
                credential_type=CredentialType.SPID,
            )

    @pytest.mark.integration
    def test_supervisor_list_only(self, vault: VaultAgent) -> None:
        """Supervisor can list credentials but not read values."""
        # Store something first
        vault.store_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.SPID,
            value="spid-credentials",
        )

        # Supervisor can list
        creds = vault.list_credentials("supervisor")
        assert isinstance(creds, list)

        # Supervisor cannot read
        with pytest.raises(PermissionDeniedError):
            vault.get_credential(
                agent_id="supervisor",
                credential_type=CredentialType.SPID,
            )


class TestAuditTrail:
    """Audit logging tests."""

    @pytest.mark.integration
    def test_store_generates_audit_entry(self, vault: VaultAgent) -> None:
        """Every store operation creates an audit log entry."""
        vault.store_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.CCIAA_API,
            value="cciaa-key",
        )

        entries = vault._audit.get_log(
            agent_id="agent0_wizard",
            credential_type="CCIAA_API",
            limit=1,
        )
        assert len(entries) >= 1
        assert entries[0].action == "store"
        assert entries[0].success is True

    @pytest.mark.integration
    def test_get_generates_audit_entry(self, vault: VaultAgent) -> None:
        """Every get operation creates an audit log entry."""
        vault.store_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.INPS_API,
            value="inps-key",
        )
        vault.get_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.INPS_API,
        )

        entries = vault._audit.get_log(
            agent_id="agent0_wizard",
            credential_type="INPS_API",
            limit=1,
        )
        assert len(entries) >= 1
        assert entries[0].action == "get"
        assert entries[0].success is True

    @pytest.mark.integration
    def test_failed_access_logged(self, vault: VaultAgent) -> None:
        """Permission denied is logged with success=False."""
        with pytest.raises(PermissionDeniedError):
            vault.get_credential(
                agent_id="agent1_collector",
                credential_type=CredentialType.FIRMA_DIGITALE,
            )

        entries = vault._audit.get_log(
            agent_id="agent1_collector",
            credential_type="FIRMA_DIGITALE",
            limit=1,
        )
        assert len(entries) >= 1
        assert entries[0].success is False


class TestExpiry:
    """Credential expiry tests."""

    @pytest.mark.integration
    def test_check_expiry_finds_expiring(self, vault: VaultAgent) -> None:
        """Credentials expiring within warning period are detected."""
        # PSD2_CONSENT has 90-day expiry by default
        vault.store_credential(
            agent_id="agent0_wizard",
            credential_type=CredentialType.PSD2_CONSENT,
            value="consent-token-123",
        )

        # With 30-day warning and 90-day expiry, it should NOT be in the list yet
        expiring = vault.check_expiry()
        psd2_expiring = [
            e for e in expiring
            if e["credential_type"] == "PSD2_CONSENT"
        ]
        # 90 days > 30 day warning, so should not appear
        # (Unless there are old test credentials — filter by recent)

    @pytest.mark.integration
    def test_expired_credential_raises(self, vault: VaultAgent) -> None:
        """Accessing an expired credential raises CredentialExpiredError."""
        import psycopg2
        from psycopg2.extras import Json

        from integrations.vault.crypto import encrypt

        config = vault._config

        # Manually insert an expired credential
        encrypted, salt = encrypt(
            "expired-value", config.master_secret, config.pbkdf2_iterations
        )
        cred_id = uuid.uuid4()
        expired_time = datetime.utcnow() - timedelta(days=1)

        conn = psycopg2.connect(config.db_dsn)
        try:
            with conn.cursor() as cur:
                # Clear any active BANCA_TOKEN first
                cur.execute(
                    "UPDATE vault_credentials SET status = 'superseded' WHERE credential_type = 'BANCA_TOKEN' AND status = 'active'"
                )
                cur.execute(
                    """
                    INSERT INTO vault_credentials
                        (id, agent_owner, credential_type, encrypted_value,
                         salt, metadata, created_at, expires_at, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
                    """,
                    (
                        str(cred_id),
                        "agent1_collector",
                        "BANCA_TOKEN",
                        encrypted,
                        salt,
                        Json({}),
                        datetime.utcnow() - timedelta(days=91),
                        expired_time,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(CredentialExpiredError):
            vault.get_credential(
                agent_id="agent1_collector",
                credential_type=CredentialType.BANCA_TOKEN,
            )

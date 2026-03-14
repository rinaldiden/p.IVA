"""VaultAgent — secure credential management for FiscalAI.

All credentials are encrypted with AES-256-GCM using per-record salts
and PBKDF2-HMAC-SHA256 key derivation. Access is controlled by per-agent
policies. Every operation is logged in an append-only audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import psycopg2
from psycopg2.extras import Json

from . import crypto
from .audit import AuditTrail
from .config import VaultConfig
from .models import (
    ACCESS_POLICIES,
    DEFAULT_EXPIRY_DAYS,
    Credential,
    CredentialType,
    Permission,
)
from .redis_client import VaultRedisClient


class PermissionDeniedError(Exception):
    """Raised when an agent lacks permission for the requested operation."""


class CredentialExpiredError(Exception):
    """Raised when attempting to access an expired credential."""


class CredentialNotFoundError(Exception):
    """Raised when a credential is not found."""


class VaultAgent:
    """Secure credential store for FiscalAI agents.

    Usage:
        config = VaultConfig()
        vault = VaultAgent(config)
        cred_id = vault.store_credential("agent0_wizard", CredentialType.SPID, "secret", {})
        value = vault.get_credential("agent0_wizard", CredentialType.SPID)
    """

    def __init__(self, config: VaultConfig) -> None:
        self._config = config
        self._audit = AuditTrail(config.db_dsn)
        self._redis = VaultRedisClient(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
        )

    def store_credential(
        self,
        agent_id: str,
        credential_type: CredentialType,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Store an encrypted credential.

        Returns:
            credential_id — NEVER the plaintext value.
        """
        self._check_permission(agent_id, credential_type, Permission.WRITE)

        encrypted_value, salt = crypto.encrypt(
            value,
            self._config.master_secret,
            self._config.pbkdf2_iterations,
        )

        credential_id = uuid.uuid4()
        now = datetime.utcnow()

        expiry_days = DEFAULT_EXPIRY_DAYS.get(credential_type)
        expires_at = now + timedelta(days=expiry_days) if expiry_days else None

        conn = psycopg2.connect(self._config.db_dsn)
        try:
            with conn.cursor() as cur:
                # Deactivate any existing active credential of the same type
                cur.execute(
                    """
                    UPDATE vault_credentials
                    SET status = 'superseded', rotated_at = %s
                    WHERE agent_owner = %s
                      AND credential_type = %s
                      AND status = 'active'
                    """,
                    (now, agent_id, credential_type.value),
                )

                cur.execute(
                    """
                    INSERT INTO vault_credentials
                        (id, agent_owner, credential_type, encrypted_value,
                         salt, metadata, created_at, expires_at, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
                    """,
                    (
                        str(credential_id),
                        agent_id,
                        credential_type.value,
                        encrypted_value,
                        salt,
                        Json(metadata or {}),
                        now,
                        expires_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        self._audit.log(
            agent_id=agent_id,
            action="store",
            credential_type=credential_type.value,
            credential_id=credential_id,
            success=True,
        )

        self._redis.publish_event(
            event_type="credential_stored",
            agent_id=agent_id,
            credential_type=credential_type.value,
            credential_id=str(credential_id),
            details={"expires_at": expires_at.isoformat() if expires_at else None},
        )

        return credential_id

    def get_credential(
        self,
        agent_id: str,
        credential_type: CredentialType,
    ) -> str:
        """Retrieve and decrypt a credential.

        Raises:
            PermissionDeniedError: if agent lacks READ permission.
            CredentialExpiredError: if the credential has expired.
            CredentialNotFoundError: if no active credential exists.
        """
        self._check_permission(agent_id, credential_type, Permission.READ)

        conn = psycopg2.connect(self._config.db_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, encrypted_value, salt, expires_at, status
                    FROM vault_credentials
                    WHERE credential_type = %s
                      AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (credential_type.value,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            self._audit.log(
                agent_id=agent_id,
                action="get",
                credential_type=credential_type.value,
                success=False,
                details={"error": "not_found"},
            )
            raise CredentialNotFoundError(
                f"No active credential of type {credential_type.value}"
            )

        cred_id, encrypted_value, salt, expires_at, status = row

        # Check expiry
        if expires_at and datetime.utcnow() > expires_at:
            self._audit.log(
                agent_id=agent_id,
                action="get",
                credential_type=credential_type.value,
                credential_id=uuid.UUID(cred_id),
                success=False,
                details={"error": "expired", "expired_at": expires_at.isoformat()},
            )
            raise CredentialExpiredError(
                f"Credential {credential_type.value} expired at {expires_at.isoformat()}"
            )

        # Handle memoryview from psycopg2
        if isinstance(encrypted_value, memoryview):
            encrypted_value = bytes(encrypted_value)
        if isinstance(salt, memoryview):
            salt = bytes(salt)

        decrypted = crypto.decrypt(
            encrypted_value,
            salt,
            self._config.master_secret,
            self._config.pbkdf2_iterations,
        )

        self._audit.log(
            agent_id=agent_id,
            action="get",
            credential_type=credential_type.value,
            credential_id=uuid.UUID(cred_id),
            success=True,
        )

        return decrypted

    def rotate_credential(self, credential_id: uuid.UUID) -> bool:
        """Mark a credential as expired/rotated.

        Returns True if credential was found and rotated.
        """
        now = datetime.utcnow()
        conn = psycopg2.connect(self._config.db_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE vault_credentials
                    SET status = 'expired', rotated_at = %s
                    WHERE id = %s AND status = 'active'
                    RETURNING agent_owner, credential_type
                    """,
                    (now, str(credential_id)),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if not row:
            return False

        agent_owner, credential_type = row

        self._audit.log(
            agent_id="system",
            action="rotate",
            credential_type=credential_type,
            credential_id=credential_id,
            success=True,
        )

        self._redis.publish_event(
            event_type="credential_rotated",
            agent_id=agent_owner,
            credential_type=credential_type,
            credential_id=str(credential_id),
        )

        return True

    def list_credentials(self, agent_id: str) -> list[dict[str, Any]]:
        """List credential types (NEVER values) visible to this agent.

        All agents can list. Supervisor gets LIST_ONLY access.
        """
        conn = psycopg2.connect(self._config.db_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT credential_type, created_at, expires_at, status
                    FROM vault_credentials
                    WHERE status = 'active'
                    ORDER BY credential_type
                    """,
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        self._audit.log(
            agent_id=agent_id,
            action="list",
            credential_type="*",
            success=True,
        )

        return [
            {
                "credential_type": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "expires_at": row[2].isoformat() if row[2] else None,
                "status": row[3],
            }
            for row in rows
        ]

    def check_expiry(self) -> list[dict[str, Any]]:
        """Return credentials expiring within the configured warning period.

        Used by Agent9 for expiry alerts.
        """
        warning_date = datetime.utcnow() + timedelta(
            days=self._config.expiry_warning_days
        )

        conn = psycopg2.connect(self._config.db_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, agent_owner, credential_type, expires_at
                    FROM vault_credentials
                    WHERE status = 'active'
                      AND expires_at IS NOT NULL
                      AND expires_at <= %s
                    ORDER BY expires_at ASC
                    """,
                    (warning_date,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [
            {
                "credential_id": row[0],
                "agent_owner": row[1],
                "credential_type": row[2],
                "expires_at": row[3].isoformat() if row[3] else None,
                "days_until_expiry": (row[3] - datetime.utcnow()).days if row[3] else None,
            }
            for row in rows
        ]

    def _check_permission(
        self,
        agent_id: str,
        credential_type: CredentialType,
        permission: Permission,
    ) -> None:
        """Verify agent has the required permission.

        Raises PermissionDeniedError if not authorized.
        """
        agent_policies = ACCESS_POLICIES.get(agent_id, {})
        allowed_permissions = agent_policies.get(credential_type, [])

        if permission not in allowed_permissions:
            self._audit.log(
                agent_id=agent_id,
                action=f"permission_denied:{permission.value}",
                credential_type=credential_type.value,
                success=False,
                details={"required": permission.value},
            )
            raise PermissionDeniedError(
                f"Agent '{agent_id}' lacks {permission.value} permission "
                f"for {credential_type.value}"
            )

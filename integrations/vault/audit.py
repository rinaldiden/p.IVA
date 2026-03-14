"""Append-only audit trail for the Vault Agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json

from .models import AuditEntry


class AuditTrail:
    """Append-only audit log. No UPDATE, no DELETE — ever."""

    def __init__(self, db_dsn: str) -> None:
        self._db_dsn = db_dsn

    def log(
        self,
        agent_id: str,
        action: str,
        credential_type: str,
        credential_id: uuid.UUID | None = None,
        success: bool = True,
        ip_address: str = "",
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Append an entry to the audit log."""
        entry = AuditEntry(
            id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            action=action,
            credential_type=credential_type,
            credential_id=credential_id,
            success=success,
            ip_address=ip_address,
            details=details or {},
        )

        conn = psycopg2.connect(self._db_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_log
                        (id, timestamp, agent_id, action, credential_type,
                         credential_id, success, ip_address, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(entry.id),
                        entry.timestamp,
                        entry.agent_id,
                        entry.action,
                        entry.credential_type,
                        str(entry.credential_id) if entry.credential_id else None,
                        entry.success,
                        entry.ip_address,
                        Json(entry.details),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        return entry

    def get_log(
        self,
        agent_id: str | None = None,
        credential_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Read audit entries (no modification allowed)."""
        conn = psycopg2.connect(self._db_dsn)
        try:
            with conn.cursor() as cur:
                query = "SELECT id, timestamp, agent_id, action, credential_type, credential_id, success, ip_address, details FROM audit_log"
                conditions: list[str] = []
                params: list[Any] = []

                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)
                if credential_type:
                    conditions.append("credential_type = %s")
                    params.append(credential_type)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY timestamp DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                rows = cur.fetchall()

                return [
                    AuditEntry(
                        id=uuid.UUID(row[0]),
                        timestamp=row[1],
                        agent_id=row[2],
                        action=row[3],
                        credential_type=row[4],
                        credential_id=uuid.UUID(row[5]) if row[5] else None,
                        success=row[6],
                        ip_address=row[7],
                        details=row[8] or {},
                    )
                    for row in rows
                ]
        finally:
            conn.close()

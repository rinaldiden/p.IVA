"""Data models for the Vault Agent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CredentialType(str, Enum):
    FIRMA_DIGITALE = "FIRMA_DIGITALE"
    SPID = "SPID"
    PSD2_CONSENT = "PSD2_CONSENT"
    AGENZIA_ENTRATE_API = "AGENZIA_ENTRATE_API"
    INPS_API = "INPS_API"
    CCIAA_API = "CCIAA_API"
    SDI_CREDENTIALS = "SDI_CREDENTIALS"
    BANCA_TOKEN = "BANCA_TOKEN"
    INTERMEDIARIO_TELEMATICO = "INTERMEDIARIO_TELEMATICO"


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    LIST = "list"


# Default expiry in days per credential type (None = no auto-expiry)
DEFAULT_EXPIRY_DAYS: dict[CredentialType, int | None] = {
    CredentialType.FIRMA_DIGITALE: 1095,  # 3 years
    CredentialType.SPID: None,  # session-based, configurable
    CredentialType.PSD2_CONSENT: 90,
    CredentialType.AGENZIA_ENTRATE_API: None,
    CredentialType.INPS_API: None,
    CredentialType.CCIAA_API: None,
    CredentialType.SDI_CREDENTIALS: None,
    CredentialType.BANCA_TOKEN: 90,
    CredentialType.INTERMEDIARIO_TELEMATICO: None,
}


# Access policies: agent_id -> {credential_type: [permissions]}
ACCESS_POLICIES: dict[str, dict[CredentialType, list[Permission]]] = {
    "agent0_wizard": {
        CredentialType.FIRMA_DIGITALE: [Permission.READ, Permission.WRITE],
        CredentialType.SPID: [Permission.READ, Permission.WRITE],
        CredentialType.AGENZIA_ENTRATE_API: [Permission.READ, Permission.WRITE],
        CredentialType.INPS_API: [Permission.READ, Permission.WRITE],
        CredentialType.CCIAA_API: [Permission.READ, Permission.WRITE],
        CredentialType.PSD2_CONSENT: [Permission.WRITE],
        CredentialType.BANCA_TOKEN: [Permission.WRITE],
        CredentialType.SDI_CREDENTIALS: [Permission.WRITE],
        CredentialType.INTERMEDIARIO_TELEMATICO: [Permission.WRITE],
    },
    "agent1_collector": {
        CredentialType.PSD2_CONSENT: [Permission.READ],
        CredentialType.SDI_CREDENTIALS: [Permission.READ],
        CredentialType.BANCA_TOKEN: [Permission.READ],
    },
    "agent5_declaration": {
        CredentialType.FIRMA_DIGITALE: [Permission.READ],
        CredentialType.INTERMEDIARIO_TELEMATICO: [Permission.READ],
    },
    "agent8_invoicing": {
        CredentialType.SDI_CREDENTIALS: [Permission.READ],
        CredentialType.FIRMA_DIGITALE: [Permission.READ],
    },
    "supervisor": {
        # LIST_ONLY — can list credential types, never read values
    },
}


@dataclass
class Credential:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_owner: str = ""
    credential_type: CredentialType = CredentialType.SPID
    encrypted_value: bytes = b""
    salt: bytes = b""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    rotated_at: datetime | None = None
    status: str = "active"


@dataclass
class AccessPolicy:
    agent_id: str
    credential_type: CredentialType
    permission: Permission


@dataclass
class AuditEntry:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str = ""
    action: str = ""
    credential_type: str = ""
    credential_id: uuid.UUID | None = None
    success: bool = True
    ip_address: str = ""
    details: dict[str, Any] = field(default_factory=dict)

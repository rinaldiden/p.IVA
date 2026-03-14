"""FiscalAI Vault — secure credential management."""

from .vault_agent import (
    CredentialExpiredError,
    CredentialNotFoundError,
    PermissionDeniedError,
    VaultAgent,
)

__all__ = [
    "VaultAgent",
    "PermissionDeniedError",
    "CredentialExpiredError",
    "CredentialNotFoundError",
]

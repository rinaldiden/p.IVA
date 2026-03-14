# Vault — Auth Agent & Credential Manager

Secure credential storage for FiscalAI. All credentials are encrypted
with AES-256-GCM, access is controlled by per-agent policies, and every
operation is logged in an append-only audit trail.

## Quick Start

### 1. Start infrastructure

```bash
cd integrations/vault
cp .env.example .env
# Edit .env — set VAULT_MASTER_SECRET and VAULT_DB_PASSWORD

docker compose -f docker-compose.vault.yml up -d
```

### 2. Verify services

```bash
docker compose -f docker-compose.vault.yml ps
# Both vault-db and vault-redis should be healthy
```

### 3. Install Python dependencies

```bash
pip install psycopg2-binary redis cryptography pytest
```

### 4. Run tests

```bash
# From repo root
export VAULT_MASTER_SECRET=test-secret-for-ci
export VAULT_DB_PASSWORD=test-password  # must match .env
pytest integrations/vault/tests/ -v
```

## Usage

```python
from integrations.vault import VaultAgent
from integrations.vault.config import VaultConfig
from integrations.vault.models import CredentialType

config = VaultConfig()  # reads from env vars
vault = VaultAgent(config)

# Store a credential (only agent0_wizard can write SPID)
cred_id = vault.store_credential(
    agent_id="agent0_wizard",
    credential_type=CredentialType.SPID,
    value="user-spid-password-here",
    metadata={"provider": "poste_id", "level": "L2"},
)

# Retrieve (only agents with READ permission)
value = vault.get_credential(
    agent_id="agent0_wizard",
    credential_type=CredentialType.SPID,
)

# List credentials (no values exposed — supervisor safe)
creds = vault.list_credentials("supervisor")

# Check for expiring credentials (used by Agent9)
expiring = vault.check_expiry()
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VAULT_MASTER_SECRET` | Yes | — | Master encryption key (generate strong random) |
| `VAULT_DB_PASSWORD` | Yes | — | PostgreSQL password |
| `VAULT_DB_HOST` | No | localhost | PostgreSQL host |
| `VAULT_DB_PORT` | No | 5432 | PostgreSQL port |
| `VAULT_DB_NAME` | No | fiscalai_vault | Database name |
| `VAULT_DB_USER` | No | vault | Database user |
| `VAULT_REDIS_HOST` | No | localhost | Redis host |
| `VAULT_REDIS_PORT` | No | 6379 | Redis port |
| `VAULT_REDIS_DB` | No | 0 | Redis database number |
| `VAULT_PBKDF2_ITERATIONS` | No | 100000 | Key derivation iterations |
| `VAULT_EXPIRY_WARNING_DAYS` | No | 30 | Days before expiry to trigger alerts |

## Access Policies

| Agent | Credentials | Permissions |
|-------|------------|-------------|
| agent0_wizard | FIRMA_DIGITALE, SPID, AGENZIA_ENTRATE_API, INPS_API, CCIAA_API | read + write |
| agent0_wizard | PSD2_CONSENT, BANCA_TOKEN, SDI_CREDENTIALS, INTERMEDIARIO_TELEMATICO | write only |
| agent1_collector | PSD2_CONSENT, SDI_CREDENTIALS, BANCA_TOKEN | read |
| agent5_declaration | FIRMA_DIGITALE, INTERMEDIARIO_TELEMATICO | read |
| agent8_invoicing | SDI_CREDENTIALS, FIRMA_DIGITALE | read |
| supervisor | all | list only (no values) |

## Security

- **Encryption**: AES-256-GCM with 12-byte random nonce
- **Key derivation**: PBKDF2-HMAC-SHA256, 100k iterations, 16-byte random salt per record
- **No plaintext in logs**: audit trail records actions, never credential values
- **Append-only audit**: PostgreSQL trigger prevents UPDATE/DELETE on audit_log
- **Per-record salt**: same credential encrypted twice produces different ciphertext

## Migration to HashiCorp Vault

This implementation is designed for local development and small deployments.
For production, replace with HashiCorp Vault:

1. The `VaultAgent` API stays the same — only the storage backend changes
2. Replace `crypto.py` with Vault Transit engine for encryption
3. Replace PostgreSQL storage with Vault KV v2 engine
4. Replace `access_policies` table with Vault ACL policies
5. Keep the `AuditTrail` class — Vault has its own audit log but
   the application-level log adds agent context

The `VaultAgent` class is designed as an adapter — swap the implementation,
keep the interface.

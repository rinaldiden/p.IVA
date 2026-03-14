-- FiscalAI Vault — PostgreSQL Schema
-- Executed on first startup via docker-compose

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Encrypted credentials store
CREATE TABLE IF NOT EXISTS vault_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_owner VARCHAR(50) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    encrypted_value BYTEA NOT NULL,
    salt BYTEA NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    rotated_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    CONSTRAINT valid_status CHECK (status IN ('active', 'expired', 'superseded'))
);

CREATE INDEX IF NOT EXISTS idx_credentials_type_status
    ON vault_credentials (credential_type, status);
CREATE INDEX IF NOT EXISTS idx_credentials_expiry
    ON vault_credentials (expires_at)
    WHERE status = 'active' AND expires_at IS NOT NULL;

-- Access control policies
CREATE TABLE IF NOT EXISTS access_policies (
    agent_id VARCHAR(50) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    permission VARCHAR(20) NOT NULL,
    PRIMARY KEY (agent_id, credential_type, permission),
    CONSTRAINT valid_permission CHECK (permission IN ('read', 'write', 'list'))
);

-- Append-only audit log — NO UPDATE, NO DELETE triggers enforced
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_id VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    credential_id UUID,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    ip_address VARCHAR(45) DEFAULT '',
    details JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log (agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_credential ON audit_log (credential_id)
    WHERE credential_id IS NOT NULL;

-- Prevent UPDATE and DELETE on audit_log
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % operations are not allowed', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS no_audit_update ON audit_log;
CREATE TRIGGER no_audit_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_modification();

-- Seed access policies from hardcoded rules
INSERT INTO access_policies (agent_id, credential_type, permission) VALUES
    ('agent0_wizard', 'FIRMA_DIGITALE', 'read'),
    ('agent0_wizard', 'FIRMA_DIGITALE', 'write'),
    ('agent0_wizard', 'SPID', 'read'),
    ('agent0_wizard', 'SPID', 'write'),
    ('agent0_wizard', 'AGENZIA_ENTRATE_API', 'read'),
    ('agent0_wizard', 'AGENZIA_ENTRATE_API', 'write'),
    ('agent0_wizard', 'INPS_API', 'read'),
    ('agent0_wizard', 'INPS_API', 'write'),
    ('agent0_wizard', 'CCIAA_API', 'read'),
    ('agent0_wizard', 'CCIAA_API', 'write'),
    ('agent0_wizard', 'PSD2_CONSENT', 'write'),
    ('agent0_wizard', 'BANCA_TOKEN', 'write'),
    ('agent0_wizard', 'SDI_CREDENTIALS', 'write'),
    ('agent0_wizard', 'INTERMEDIARIO_TELEMATICO', 'write'),
    ('agent1_collector', 'PSD2_CONSENT', 'read'),
    ('agent1_collector', 'SDI_CREDENTIALS', 'read'),
    ('agent1_collector', 'BANCA_TOKEN', 'read'),
    ('agent5_declaration', 'FIRMA_DIGITALE', 'read'),
    ('agent5_declaration', 'INTERMEDIARIO_TELEMATICO', 'read'),
    ('agent8_invoicing', 'SDI_CREDENTIALS', 'read'),
    ('agent8_invoicing', 'FIRMA_DIGITALE', 'read')
ON CONFLICT DO NOTHING;

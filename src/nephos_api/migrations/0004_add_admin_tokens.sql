-- ADR 20260726 (authenticated secret reveal): bearer tokens issued by
-- /auth/login, gating the reveal endpoint.
--
-- Only the hash is stored, mirroring admin_accounts.password_hash: reading this
-- table must not yield a usable credential. The token itself is returned once at
-- login and never persisted in plaintext.
--
-- token_hash is UNIQUE so a lookup is a single indexed read; revocation and
-- expiry cleanup are row deletes.
CREATE TABLE admin_tokens (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_admin_tokens_expires_at ON admin_tokens(expires_at);

CREATE TABLE IF NOT EXISTS identity.external_identities (
    external_identity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES identity.users ON DELETE CASCADE,
    provider text NOT NULL,
    issuer text NOT NULL,
    subject text NOT NULL,
    email text NOT NULL,
    email_verified boolean NOT NULL DEFAULT false,
    hosted_domain text,
    linked_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject),
    UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS external_identities_user_idx
    ON identity.external_identities (user_id, provider);

CREATE TABLE IF NOT EXISTS identity.oidc_login_transactions (
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    state_digest char(64) NOT NULL UNIQUE,
    nonce text NOT NULL,
    code_verifier text NOT NULL,
    redirect_uri text NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS oidc_login_transactions_expiry_idx
    ON identity.oidc_login_transactions (expires_at)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS identity.oidc_login_codes (
    login_code_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code_digest char(64) NOT NULL UNIQUE,
    user_id uuid NOT NULL REFERENCES identity.users ON DELETE CASCADE,
    provider text NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS oidc_login_codes_expiry_idx
    ON identity.oidc_login_codes (expires_at)
    WHERE consumed_at IS NULL;

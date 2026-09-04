-- H6: password credentials are stored separately from the human identity record.
-- Password material is a salted one-way hash created only by the VPS bootstrap command.
CREATE TABLE identity.user_credentials (
    user_id uuid PRIMARY KEY REFERENCES identity.users ON DELETE CASCADE,
    password_hash text NOT NULL CHECK (char_length(password_hash) >= 80),
    failed_attempt_count integer NOT NULL DEFAULT 0 CHECK (failed_attempt_count >= 0),
    locked_until timestamptz,
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    last_authenticated_at timestamptz
);

CREATE INDEX user_credentials_locked_until_idx
    ON identity.user_credentials (locked_until)
    WHERE locked_until IS NOT NULL;

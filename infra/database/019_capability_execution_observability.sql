ALTER TABLE agents.agent_runs
    ADD COLUMN IF NOT EXISTS handler_id text,
    ADD COLUMN IF NOT EXISTS evidence_references jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS verification_status text,
    ADD COLUMN IF NOT EXISTS provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE agents.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_verification_status_check;

ALTER TABLE agents.agent_runs
    ADD CONSTRAINT agent_runs_verification_status_check
    CHECK (
        verification_status IS NULL
        OR verification_status IN ('VERIFIED', 'PROVISIONAL', 'UNVERIFIED')
    );

CREATE INDEX IF NOT EXISTS agent_runs_capability_status_idx
    ON agents.agent_runs (capability, status, started_at DESC);

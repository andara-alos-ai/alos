ALTER TABLE agents.agent_runs
    ADD COLUMN IF NOT EXISTS capability_version text,
    ADD COLUMN IF NOT EXISTS capability_contract_digest char(64);

ALTER TABLE agents.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_capability_version_check;

ALTER TABLE agents.agent_runs
    ADD CONSTRAINT agent_runs_capability_version_check
    CHECK (
        capability_version IS NULL
        OR capability_version ~ '^\d+\.\d+\.\d+$'
    );

ALTER TABLE agents.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_capability_digest_check;

ALTER TABLE agents.agent_runs
    ADD CONSTRAINT agent_runs_capability_digest_check
    CHECK (
        capability_contract_digest IS NULL
        OR capability_contract_digest ~ '^[a-f0-9]{64}$'
    );

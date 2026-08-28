CREATE SCHEMA IF NOT EXISTS sales;

ALTER TABLE agents.agent_runs
    ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS agent_runs_idempotency_idx
    ON agents.agent_runs (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE audit.entries
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

CREATE INDEX IF NOT EXISTS audit_organization_chain_idx
    ON audit.entries (organization_id, occurred_at, audit_entry_id);

CREATE TABLE IF NOT EXISTS sales.leads (
    lead_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    work_item_id uuid NOT NULL UNIQUE REFERENCES platform.work_items,
    full_name text NOT NULL,
    phone text,
    email text,
    source text NOT NULL,
    consent_recorded boolean NOT NULL DEFAULT false,
    status text NOT NULL CHECK (
        status IN ('RECEIVED', 'VALIDATED', 'ASSIGNED', 'FOLLOW_UP', 'QUALIFIED',
                   'RESERVED', 'DISQUALIFIED', 'EXCEPTION')
    ),
    assigned_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (phone IS NOT NULL OR email IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS leads_pipeline_idx
    ON sales.leads (organization_id, project_id, status, created_at);

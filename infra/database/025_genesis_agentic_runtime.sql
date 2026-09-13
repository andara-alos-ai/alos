-- GENESIS agentic runtime: explicit scoped context and cumulative accounting.
ALTER TABLE runtime.agent_runs
    ADD COLUMN division_id uuid REFERENCES identity.divisions,
    ADD COLUMN project_id uuid REFERENCES portfolio.projects,
    ADD COLUMN tenant_id uuid,
    ADD COLUMN execution_mode text NOT NULL DEFAULT 'LIVE'
        CHECK (execution_mode IN ('TEST', 'LIVE')),
    ADD COLUMN classification text NOT NULL DEFAULT 'INTERNAL'
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED'));

ALTER TABLE observability.usage_ledger
    ADD COLUMN model_calls integer NOT NULL DEFAULT 1 CHECK (model_calls >= 0),
    ADD COLUMN tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0);

CREATE INDEX agent_runs_scope_created_idx
    ON runtime.agent_runs (
        organization_id, workspace_id, tenant_id, division_id, project_id, created_at DESC
    );

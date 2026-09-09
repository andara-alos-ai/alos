-- Operational bounded delegation lineage and terminal accounting.
ALTER TABLE runtime.delegations
    DROP CONSTRAINT delegations_status_check;

ALTER TABLE runtime.delegations
    ADD COLUMN parent_agent_version_id uuid REFERENCES agents.versions,
    ADD COLUMN organization_id uuid REFERENCES identity.organizations,
    ADD COLUMN workspace_id uuid REFERENCES workspace.workspaces,
    ADD COLUMN division_id uuid REFERENCES identity.divisions,
    ADD COLUMN project_id uuid REFERENCES portfolio.projects,
    ADD COLUMN tenant_id uuid,
    ADD COLUMN completed_at timestamptz,
    ADD COLUMN model_calls integer NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    ADD COLUMN tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
    ADD COLUMN total_tokens integer NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    ADD COLUMN estimated_cost_usd numeric(12, 6) NOT NULL DEFAULT 0
        CHECK (estimated_cost_usd >= 0),
    ADD COLUMN block_reason text,
    ADD CONSTRAINT delegations_status_check CHECK (
        status IN ('REQUESTED', 'RUNNING', 'SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED')
    ),
    ADD CONSTRAINT delegations_completion_check CHECK (
        (status IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED') AND completed_at IS NOT NULL)
        OR (status IN ('REQUESTED', 'RUNNING') AND completed_at IS NULL)
    );

CREATE INDEX runtime_delegations_parent_status_idx
    ON runtime.delegations (parent_run_id, status, created_at DESC);
CREATE INDEX runtime_delegations_correlation_idx
    ON runtime.delegations (correlation_id, depth, created_at);
CREATE INDEX runtime_delegations_tenant_idx
    ON runtime.delegations (organization_id, workspace_id, tenant_id, created_at DESC);

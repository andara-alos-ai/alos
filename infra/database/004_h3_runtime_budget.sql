-- H3 Runtime: persistent in-flight reservations make daily budget caps deterministic.
CREATE TABLE runtime.budget_reservations (
    agent_run_id uuid PRIMARY KEY REFERENCES runtime.agent_runs ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    reserved_output_tokens integer NOT NULL CHECK (reserved_output_tokens > 0),
    reserved_cost_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX active_cost_limit_per_workspace_idx
    ON governance.cost_limits (organization_id, workspace_id)
    WHERE active AND workspace_id IS NOT NULL;
CREATE INDEX budget_reservations_workspace_created_idx
    ON runtime.budget_reservations (organization_id, workspace_id, created_at DESC);

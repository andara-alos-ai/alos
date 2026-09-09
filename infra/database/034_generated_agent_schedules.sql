-- Governed schedules and immutable dispatch evidence for generated active Agents.
CREATE TABLE jobs.agent_schedules (
    agent_schedule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    tenant_id uuid,
    agent_contract_id uuid NOT NULL REFERENCES agents.contracts ON DELETE RESTRICT,
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    schedule_expression text NOT NULL,
    timezone text NOT NULL,
    input_fixture jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(input_fixture) = 'object'),
    requested_tool_keys jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(requested_tool_keys) = 'array'),
    enabled boolean NOT NULL DEFAULT false,
    confirmed_by_user_id uuid REFERENCES identity.users,
    next_run_at timestamptz NOT NULL,
    last_run_at timestamptz,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (agent_contract_id, workspace_id, tenant_id)
);

CREATE INDEX jobs_agent_schedules_due_idx
    ON jobs.agent_schedules (next_run_at)
    WHERE enabled AND confirmed_by_user_id IS NOT NULL;

CREATE TABLE jobs.agent_schedule_dispatches (
    schedule_dispatch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_schedule_id uuid NOT NULL REFERENCES jobs.agent_schedules ON DELETE RESTRICT,
    agent_version_id uuid REFERENCES agents.versions ON DELETE RESTRICT,
    job_id uuid REFERENCES jobs.queue ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('ENQUEUED', 'SKIPPED', 'BLOCKED')),
    reason text NOT NULL,
    scheduled_for timestamptz NOT NULL,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX jobs_agent_dispatch_schedule_idx
    ON jobs.agent_schedule_dispatches (agent_schedule_id, scheduled_for DESC);

CREATE TRIGGER jobs_agent_schedule_dispatches_no_update
BEFORE UPDATE ON jobs.agent_schedule_dispatches
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER jobs_agent_schedule_dispatches_no_delete
BEFORE DELETE ON jobs.agent_schedule_dispatches
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

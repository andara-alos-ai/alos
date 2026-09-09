-- Hari 1 extension. This migration is append-only; do not edit baseline 001.

CREATE TABLE agents.tool_definitions (
    tool_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    tool_key text NOT NULL CHECK (tool_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    name text NOT NULL,
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    manifest jsonb NOT NULL,
    lifecycle_status text NOT NULL DEFAULT 'DRAFT' CHECK (
        lifecycle_status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'RETIRED')
    ),
    owner_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, tool_key)
);

CREATE TABLE governance.permission_policies (
    permission_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    permission_key text NOT NULL CHECK (permission_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    effect text NOT NULL CHECK (effect IN ('ALLOW', 'DENY')),
    resource_scope jsonb NOT NULL DEFAULT '{}'::jsonb,
    approval_required boolean NOT NULL DEFAULT false,
    lifecycle_status text NOT NULL DEFAULT 'DRAFT' CHECK (
        lifecycle_status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'REVOKED')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_version_id, permission_key)
);

CREATE TABLE governance.test_cases (
    test_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    test_key text NOT NULL CHECK (test_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    category text NOT NULL CHECK (category IN ('POSITIVE', 'NEGATIVE', 'SECURITY', 'RECOVERY')),
    input_fixture jsonb NOT NULL,
    expected_assertions jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_version_id, test_key)
);

CREATE TABLE governance.test_runs (
    test_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    test_case_id uuid REFERENCES governance.test_cases,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    correlation_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'PASSED', 'FAILED', 'BLOCKED', 'ERROR')),
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX permission_policies_agent_version_idx
    ON governance.permission_policies (agent_version_id, lifecycle_status);
CREATE INDEX test_runs_agent_version_started_idx
    ON governance.test_runs (agent_version_id, started_at DESC);

-- Provider-neutral integration status and governed software-change workflow.

CREATE SCHEMA IF NOT EXISTS integrations;

CREATE TABLE integrations.configurations (
    integration_configuration_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    integration_key text NOT NULL CHECK (integration_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    provider text NOT NULL,
    status text NOT NULL DEFAULT 'NOT_CONFIGURED'
        CHECK (status IN ('NOT_CONFIGURED', 'CONFIGURED', 'UNAVAILABLE', 'DEGRADED')),
    allowed_hosts text[] NOT NULL DEFAULT '{}'::text[],
    configuration_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(configuration_metadata) = 'object'),
    secret_reference text,
    updated_by_user_id uuid REFERENCES identity.users,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, integration_key),
    CHECK (status = 'NOT_CONFIGURED' OR secret_reference IS NOT NULL)
);

CREATE TABLE integrations.external_research_runs (
    external_research_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    query text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'EXTERNAL_RESEARCH_NOT_CONFIGURED'
    )),
    results jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(results) = 'array'),
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE SCHEMA IF NOT EXISTS software_factory;

CREATE TABLE software_factory.change_requests (
    software_change_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    requirement text NOT NULL,
    repository_url text NOT NULL,
    base_branch text NOT NULL DEFAULT 'develop',
    work_branch text,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT', 'ANALYZED', 'PATCH_READY', 'CI_FAILED', 'IN_TECHNICAL_REVIEW',
        'APPROVED', 'PULL_REQUEST_OPEN', 'STAGED', 'RELEASED', 'REJECTED', 'NOT_CONFIGURED'
    )),
    diff_digest char(64),
    ci_evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(ci_evidence) = 'object'),
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    technical_reviewer_user_id uuid REFERENCES identity.users,
    approved_by_user_id uuid REFERENCES identity.users,
    pull_request_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (requested_by_user_id IS NULL OR approved_by_user_id IS NULL OR requested_by_user_id <> approved_by_user_id)
);

CREATE INDEX integrations_external_research_scope_idx
    ON integrations.external_research_runs (organization_id, workspace_id, created_at DESC);
CREATE INDEX software_change_requests_status_idx
    ON software_factory.change_requests (organization_id, workspace_id, status, created_at DESC);


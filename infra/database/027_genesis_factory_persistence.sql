-- Durable, tenant-scoped GENESIS Factory requests and generated test proposals.
CREATE TABLE genesis.factory_requests (
    factory_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    tenant_id uuid,
    requirement text NOT NULL CHECK (char_length(btrim(requirement)) BETWEEN 10 AND 10000),
    source_type text NOT NULL DEFAULT 'DIRECT'
        CHECK (source_type IN ('DIRECT', 'RESEARCH')),
    source_research_id uuid REFERENCES research.projects,
    status text NOT NULL DEFAULT 'REQUEST'
        CHECK (status IN (
            'REQUEST', 'ANALYZING', 'DRAFT', 'NEEDS_CONFIGURATION',
            'NEEDS_IMPLEMENTATION', 'BLOCKED', 'TESTING', 'TESTED', 'IN_REVIEW'
        )),
    requirement_understanding jsonb CHECK (
        requirement_understanding IS NULL
        OR jsonb_typeof(requirement_understanding) = 'object'
    ),
    implementation_decision jsonb CHECK (
        implementation_decision IS NULL
        OR jsonb_typeof(implementation_decision) = 'object'
    ),
    dependency_resolution jsonb CHECK (
        dependency_resolution IS NULL
        OR jsonb_typeof(dependency_resolution) = 'object'
    ),
    factory_proposal jsonb CHECK (
        factory_proposal IS NULL OR jsonb_typeof(factory_proposal) = 'object'
    ),
    blockers jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(blockers) = 'array'),
    agent_contract_id uuid REFERENCES agents.contracts,
    agent_version_id uuid REFERENCES agents.versions,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    owner_user_id uuid REFERENCES identity.users,
    reviewer_user_id uuid REFERENCES identity.users,
    idempotency_key text NOT NULL CHECK (char_length(btrim(idempotency_key)) BETWEEN 1 AND 200),
    correlation_id uuid NOT NULL,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    analyzed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (source_type = 'DIRECT' AND source_research_id IS NULL)
        OR (source_type = 'RESEARCH' AND source_research_id IS NOT NULL)
    ),
    CHECK (
        (agent_contract_id IS NULL AND agent_version_id IS NULL)
        OR (agent_contract_id IS NOT NULL AND agent_version_id IS NOT NULL)
    ),
    UNIQUE (organization_id, requested_by_user_id, idempotency_key)
);

CREATE INDEX genesis_factory_requests_scope_status_idx
    ON genesis.factory_requests (
        organization_id, workspace_id, tenant_id, status, updated_at DESC
    );
CREATE INDEX genesis_factory_requests_division_project_idx
    ON genesis.factory_requests (division_id, project_id, updated_at DESC);
CREATE INDEX genesis_factory_requests_research_idx
    ON genesis.factory_requests (source_research_id)
    WHERE source_research_id IS NOT NULL;

CREATE TABLE genesis.factory_generated_tests (
    factory_test_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_request_id uuid NOT NULL REFERENCES genesis.factory_requests ON DELETE RESTRICT,
    category text NOT NULL CHECK (category IN (
        'POSITIVE', 'NEGATIVE', 'REGRESSION', 'SECURITY', 'RECOVERY',
        'PERMISSION', 'TENANT_ISOLATION', 'TOOL_DENIAL', 'BUDGET',
        'SOURCE_VALIDATION', 'EVIDENCE'
    )),
    objective text NOT NULL,
    expected_status text NOT NULL DEFAULT 'EVIDENCE_REQUIRED'
        CHECK (expected_status = 'EVIDENCE_REQUIRED'),
    execution_status text NOT NULL DEFAULT 'NOT_RUN'
        CHECK (execution_status IN ('NOT_RUN', 'RUNNING', 'PASSED', 'FAILED', 'BLOCKED', 'ERROR')),
    agent_version_id uuid REFERENCES agents.versions,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (factory_request_id, category)
);

CREATE INDEX genesis_factory_generated_tests_request_idx
    ON genesis.factory_generated_tests (factory_request_id, category);

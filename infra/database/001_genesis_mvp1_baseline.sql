-- ALOS Genesis MVP1 clean baseline. Apply only to a fresh local/staging database.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS workspace;
CREATE SCHEMA IF NOT EXISTS sources;
CREATE SCHEMA IF NOT EXISTS genesis;
CREATE SCHEMA IF NOT EXISTS agents;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE identity.organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z][A-Z0-9_]{1,39}$'),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.divisions (
    division_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    code text NOT NULL CHECK (code IN ('FINANCE', 'SALES_MARKETING', 'PROPERTY', 'HR', 'LEGAL', 'IT')),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE identity.users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    email text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, email)
);

CREATE TABLE identity.role_assignments (
    role_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES identity.users,
    division_id uuid REFERENCES identity.divisions,
    role_code text NOT NULL CHECK (role_code IN (
        'DIRECTOR', 'DIVISION_OWNER', 'IT_LEAD', 'TECHNICAL_REVIEWER',
        'BUSINESS_REVIEWER', 'QA_SECURITY'
    )),
    assigned_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE TABLE workspace.workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    division_id uuid REFERENCES identity.divisions,
    workspace_key text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, workspace_key)
);

CREATE TABLE workspace.memberships (
    membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    user_id uuid NOT NULL REFERENCES identity.users,
    access_level text NOT NULL CHECK (access_level IN ('VIEWER', 'EDITOR', 'OWNER')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id)
);

CREATE TABLE sources.sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    source_key text NOT NULL,
    name text NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('DOCX', 'PDF', 'TEXT', 'URL')),
    classification text NOT NULL DEFAULT 'INTERNAL' CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    access_mode text NOT NULL DEFAULT 'READ_ONLY' CHECK (access_mode = 'READ_ONLY'),
    owner_user_id uuid REFERENCES identity.users,
    status text NOT NULL DEFAULT 'SOURCE_RECEIVED' CHECK (status IN ('SOURCE_RECEIVED', 'VALIDATED', 'VERIFIED', 'RETIRED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, source_key)
);

CREATE TABLE sources.versions (
    source_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources.sources,
    version_label text NOT NULL,
    sha256 char(64),
    locator text,
    received_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, version_label)
);

CREATE TABLE genesis.conversations (
    conversation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    created_by_user_id uuid REFERENCES identity.users,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE genesis.messages (
    message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES genesis.conversations,
    actor_kind text NOT NULL CHECK (actor_kind IN ('HUMAN', 'SYSTEM')),
    actor_user_id uuid REFERENCES identity.users,
    system_actor text CHECK (system_actor IS NULL OR system_actor = 'GENESIS'),
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (actor_kind = 'HUMAN' AND actor_user_id IS NOT NULL AND system_actor IS NULL)
        OR (actor_kind = 'SYSTEM' AND actor_user_id IS NULL AND system_actor = 'GENESIS')
    )
);

CREATE TABLE genesis.artifacts (
    artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES genesis.conversations,
    artifact_type text NOT NULL CHECK (artifact_type IN ('ANALYSIS', 'BLUEPRINT', 'CONTRACT', 'TEST_PLAN', 'DIFF', 'RELEASE_PROPOSAL')),
    version integer NOT NULL CHECK (version > 0),
    content jsonb NOT NULL,
    digest char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, artifact_type, version)
);

CREATE TABLE genesis.change_requests (
    change_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    conversation_id uuid REFERENCES genesis.conversations,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    requirement text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'VALIDATED', 'TESTED', 'IN_REVIEW', 'APPROVED', 'STAGED', 'RELEASED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agents.contracts (
    agent_contract_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    agent_key text NOT NULL CHECK (agent_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    parent_agent_contract_id uuid REFERENCES agents.contracts,
    name text NOT NULL,
    owner_user_id uuid REFERENCES identity.users,
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, agent_key),
    CHECK (parent_agent_contract_id IS NULL OR parent_agent_contract_id <> agent_contract_id)
);

CREATE TABLE agents.versions (
    agent_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_contract_id uuid NOT NULL REFERENCES agents.contracts,
    semantic_version text NOT NULL,
    lifecycle_status text NOT NULL DEFAULT 'DRAFT' CHECK (lifecycle_status IN ('DRAFT', 'VALIDATED', 'TESTED', 'IN_REVIEW', 'APPROVED', 'STAGED', 'RELEASED', 'ACTIVE', 'SUSPENDED', 'ROLLED_BACK', 'RETIRED')),
    contract_snapshot jsonb NOT NULL,
    digest char(64) NOT NULL,
    rollback_target_version_id uuid REFERENCES agents.versions,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_contract_id, semantic_version)
);

CREATE TABLE agents.registry (
    agent_contract_id uuid PRIMARY KEY REFERENCES agents.contracts,
    released_version_id uuid REFERENCES agents.versions,
    active_version_id uuid REFERENCES agents.versions,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE governance.reviews (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_request_id uuid NOT NULL REFERENCES genesis.change_requests,
    reviewer_user_id uuid NOT NULL REFERENCES identity.users,
    review_gate text NOT NULL CHECK (review_gate IN ('BUSINESS', 'TECHNICAL')),
    decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    notes text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (change_request_id, reviewer_user_id, review_gate)
);

CREATE TABLE governance.release_proposals (
    release_proposal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_request_id uuid NOT NULL UNIQUE REFERENCES genesis.change_requests,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    target_environment text NOT NULL CHECK (target_environment IN ('STAGING', 'PILOT')),
    status text NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED', 'STAGED', 'RELEASED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE governance.cost_limits (
    cost_limit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    daily_request_limit integer NOT NULL CHECK (daily_request_limit > 0),
    daily_output_token_limit integer NOT NULL CHECK (daily_output_token_limit > 0),
    daily_cost_cap_usd numeric(12, 4) NOT NULL CHECK (daily_cost_cap_usd >= 0),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE governance.kill_switches (
    kill_switch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_contract_id uuid REFERENCES agents.contracts,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    active boolean NOT NULL DEFAULT false,
    reason text NOT NULL,
    activated_by_user_id uuid REFERENCES identity.users,
    activated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE governance.rollback_records (
    rollback_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_contract_id uuid NOT NULL REFERENCES agents.contracts,
    from_version_id uuid NOT NULL REFERENCES agents.versions,
    to_version_id uuid NOT NULL REFERENCES agents.versions,
    reason text NOT NULL,
    performed_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_version_id <> to_version_id)
);

CREATE TABLE runtime.agent_runs (
    agent_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    requested_by_user_id uuid REFERENCES identity.users,
    correlation_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'SUSPENDED', 'KILLED')),
    input_reference jsonb NOT NULL DEFAULT '[]'::jsonb,
    output_reference jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE runtime.tool_calls (
    tool_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid NOT NULL REFERENCES runtime.agent_runs,
    tool_key text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('ALLOWED', 'DENIED', 'BLOCKED')),
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observability.usage_ledger (
    usage_ledger_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid NOT NULL REFERENCES runtime.agent_runs,
    provider text NOT NULL,
    model text NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    latency_ms integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    estimated_cost_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit.events (
    audit_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    actor_kind text NOT NULL CHECK (actor_kind IN ('HUMAN', 'SYSTEM')),
    actor_user_id uuid REFERENCES identity.users,
    system_actor text CHECK (system_actor IS NULL OR system_actor = 'GENESIS'),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid,
    correlation_id uuid NOT NULL,
    reason text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (actor_kind = 'HUMAN' AND actor_user_id IS NOT NULL AND system_actor IS NULL)
        OR (actor_kind = 'SYSTEM' AND actor_user_id IS NULL AND system_actor = 'GENESIS')
    )
);

CREATE OR REPLACE FUNCTION audit.reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit.events is append-only';
END;
$$;

CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE INDEX agent_runs_organization_created_idx ON runtime.agent_runs (organization_id, created_at DESC);
CREATE INDEX audit_events_organization_occurred_idx ON audit.events (organization_id, occurred_at DESC);
CREATE INDEX source_versions_source_idx ON sources.versions (source_id, received_at DESC);

INSERT INTO identity.organizations (code, name)
VALUES ('ALOS', 'ALOS Internal Organization')
ON CONFLICT (code) DO NOTHING;

INSERT INTO identity.divisions (organization_id, code, name)
SELECT organization_id, division.code, division.name
FROM identity.organizations
CROSS JOIN (
    VALUES
        ('FINANCE', 'Keuangan'),
        ('SALES_MARKETING', 'Sales & Marketing'),
        ('PROPERTY', 'Property'),
        ('HR', 'Human Resources'),
        ('LEGAL', 'Legal'),
        ('IT', 'Information Technology')
) AS division(code, name)
WHERE identity.organizations.code = 'ALOS'
ON CONFLICT (organization_id, code) DO NOTHING;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS platform;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS workflow;
CREATE SCHEMA IF NOT EXISTS agents;
CREATE SCHEMA IF NOT EXISTS executive;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS identity.organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity.divisions (
    division_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    code text NOT NULL,
    name text NOT NULL,
    parent_layer text NOT NULL DEFAULT 'AI_EXECUTIVE_OPERATING_LAYER',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS identity.users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_subject text UNIQUE,
    email text NOT NULL UNIQUE,
    display_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('INVITED', 'ACTIVE', 'SUSPENDED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS identity.role_assignments (
    assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES identity.users,
    division_id uuid REFERENCES identity.divisions,
    role_code text NOT NULL,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE TABLE IF NOT EXISTS platform.projects (
    project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'ON_HOLD', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS platform.work_items (
    work_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid REFERENCES platform.projects,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    title text NOT NULL,
    work_type text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')),
    status text NOT NULL CHECK (status IN ('DRAFT', 'OPEN', 'IN_PROGRESS', 'NEEDS_REVIEW', 'PENDING_APPROVAL', 'BLOCKED', 'COMPLETED', 'CANCELLED', 'FAILED')),
    owner_user_id uuid REFERENCES identity.users,
    due_at timestamptz,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS platform.documents (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid REFERENCES platform.projects,
    logical_name text NOT NULL,
    classification text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users
);

CREATE TABLE IF NOT EXISTS platform.document_versions (
    document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES platform.documents,
    version_number integer NOT NULL CHECK (version_number > 0),
    object_key text NOT NULL,
    sha256 char(64) NOT NULL,
    media_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    verification_status text NOT NULL CHECK (verification_status IN ('UNVERIFIED', 'VERIFIED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users,
    UNIQUE (document_id, version_number),
    UNIQUE (document_id, sha256)
);

CREATE TABLE IF NOT EXISTS platform.evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id uuid NOT NULL REFERENCES platform.work_items,
    document_version_id uuid REFERENCES platform.document_versions,
    claim_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('SUBMITTED', 'NEEDS_REVIEW', 'ACCEPTED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users
);

CREATE TABLE IF NOT EXISTS governance.approval_requests (
    approval_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id uuid NOT NULL REFERENCES platform.work_items,
    requester_user_id uuid NOT NULL REFERENCES identity.users,
    policy_code text NOT NULL,
    policy_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED', 'EXPIRED')),
    material_fingerprint char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS governance.approval_decisions (
    approval_decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    approval_request_id uuid NOT NULL REFERENCES governance.approval_requests,
    approver_user_id uuid NOT NULL REFERENCES identity.users,
    decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED', 'REVISION_REQUESTED')),
    reason text NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (approval_request_id, approver_user_id)
);

CREATE TABLE IF NOT EXISTS governance.exceptions (
    exception_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id uuid REFERENCES platform.work_items,
    category text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status text NOT NULL CHECK (status IN ('OPEN', 'INVESTIGATING', 'CAPA_REQUIRED', 'RESOLVED')),
    owner_user_id uuid REFERENCES identity.users,
    due_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS governance.capas (
    capa_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    exception_id uuid NOT NULL REFERENCES governance.exceptions,
    status text NOT NULL CHECK (status IN ('OPEN', 'ANALYSIS', 'ACTION_IN_PROGRESS', 'VERIFICATION', 'CLOSED')),
    root_cause text,
    corrective_action text,
    preventive_action text,
    reviewer_user_id uuid REFERENCES identity.users,
    due_at timestamptz,
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow.workflow_releases (
    workflow_release_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id text NOT NULL,
    version text NOT NULL,
    definition jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('STAGED', 'RELEASED', 'DEPRECATED')),
    released_at timestamptz,
    UNIQUE (workflow_id, version)
);

CREATE TABLE IF NOT EXISTS workflow.workflow_runs (
    workflow_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_release_id uuid NOT NULL REFERENCES workflow.workflow_releases,
    work_item_id uuid REFERENCES platform.work_items,
    current_step text NOT NULL,
    status text NOT NULL,
    correlation_id uuid NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS agents.agent_releases (
    agent_release_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id text NOT NULL,
    version text NOT NULL,
    definition jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('STAGED', 'RELEASED', 'DEPRECATED')),
    released_at timestamptz,
    UNIQUE (agent_id, version)
);

CREATE TABLE IF NOT EXISTS agents.agent_runs (
    agent_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_release_id uuid NOT NULL REFERENCES agents.agent_releases,
    workflow_run_id uuid REFERENCES workflow.workflow_runs,
    status text NOT NULL CHECK (status IN ('RECEIVED', 'VALIDATING', 'RUNNING', 'NEEDS_REVIEW', 'PENDING_APPROVAL', 'COMPLETED', 'FAILED', 'BLOCKED')),
    input_reference jsonb NOT NULL,
    output_reference jsonb,
    correlation_id uuid NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit.entries (
    audit_entry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_type text NOT NULL,
    actor_id text NOT NULL,
    active_role text,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    reason text,
    before_masked jsonb,
    after_masked jsonb,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    previous_hash char(64),
    entry_hash char(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS work_items_queue_idx ON platform.work_items (division_id, status, priority, due_at);
CREATE INDEX IF NOT EXISTS approval_pending_idx ON governance.approval_requests (status, created_at);
CREATE INDEX IF NOT EXISTS exception_open_idx ON governance.exceptions (status, severity, due_at);
CREATE INDEX IF NOT EXISTS workflow_runs_active_idx ON workflow.workflow_runs (status, started_at);
CREATE INDEX IF NOT EXISTS agent_runs_status_idx ON agents.agent_runs (status, started_at);
CREATE INDEX IF NOT EXISTS audit_entity_idx ON audit.entries (entity_type, entity_id, occurred_at);

INSERT INTO identity.organizations (code, name)
VALUES ('ARM', 'PT Andara Rejo Makmur')
ON CONFLICT (code) DO NOTHING;

INSERT INTO identity.divisions (organization_id, code, name)
SELECT organization_id, division.code, division.name
FROM identity.organizations
CROSS JOIN (VALUES
    ('FINANCE', 'Keuangan'),
    ('SALES_MARKETING', 'Sales & Marketing'),
    ('PROPERTY', 'Property'),
    ('HR', 'HR'),
    ('LEGAL', 'Legal'),
    ('IT', 'IT')
) AS division(code, name)
WHERE identity.organizations.code = 'ARM'
ON CONFLICT (organization_id, code) DO NOTHING;

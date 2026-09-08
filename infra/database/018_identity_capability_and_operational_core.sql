-- ALOS integrated operating core. Additive only: migrations 001-017 remain immutable.

ALTER TABLE identity.role_assignments
    DROP CONSTRAINT IF EXISTS role_assignments_role_code_check;
ALTER TABLE identity.role_assignments
    ADD CONSTRAINT role_assignments_role_code_check CHECK (role_code IN (
        'DIRECTOR', 'DIVISION_LEAD', 'DIVISION_MEMBER', 'IT_ADMIN', 'AI_ADMIN',
        'TECHNICAL_REVIEWER', 'BUSINESS_REVIEWER', 'QA_SECURITY',
        -- Compatibility for identities created before role normalization.
        'DIVISION_OWNER', 'IT_LEAD'
    ));

ALTER TABLE identity.users
    ADD COLUMN default_data_scope text NOT NULL DEFAULT 'OWN_ASSIGNED'
    CHECK (default_data_scope IN ('COMPANY', 'DIVISION', 'PROJECT', 'OWN_ASSIGNED'));

UPDATE identity.users AS user_record
SET default_data_scope = CASE
    WHEN EXISTS (
        SELECT 1 FROM identity.role_assignments AS assignment
        WHERE assignment.user_id = user_record.user_id
          AND assignment.revoked_at IS NULL
          AND assignment.role_code = 'DIRECTOR'
    ) THEN 'COMPANY'
    WHEN EXISTS (
        SELECT 1 FROM identity.role_assignments AS assignment
        WHERE assignment.user_id = user_record.user_id
          AND assignment.revoked_at IS NULL
          AND assignment.role_code = 'DIVISION_OWNER'
    ) THEN 'DIVISION'
    ELSE default_data_scope
END;

CREATE TABLE identity.duty_assignments (
    duty_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES identity.users,
    duty_code text NOT NULL CHECK (duty_code IN (
        'IT_ADMIN', 'AI_ADMIN', 'TECHNICAL_REVIEWER', 'BUSINESS_REVIEWER', 'QA_SECURITY'
    )),
    workspace_id uuid REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    assigned_by_user_id uuid NOT NULL REFERENCES identity.users,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (revoked_at IS NULL OR revoked_at >= assigned_at)
);

CREATE UNIQUE INDEX identity_active_duty_assignment_idx
    ON identity.duty_assignments (user_id, duty_code, workspace_id, division_id)
    WHERE revoked_at IS NULL;

CREATE SCHEMA IF NOT EXISTS capabilities;

CREATE TABLE capabilities.definitions (
    capability_key text PRIMARY KEY CHECK (
        capability_key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'
    ),
    domain text NOT NULL CHECK (domain ~ '^[a-z][a-z0-9_]{1,39}$'),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 160),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 4 AND 1000),
    supported_scopes text[] NOT NULL CHECK (
        cardinality(supported_scopes) > 0
        AND supported_scopes <@ ARRAY['COMPANY', 'DIVISION', 'PROJECT', 'OWN_ASSIGNED']::text[]
    ),
    allowed_data_classification text[] NOT NULL CHECK (
        cardinality(allowed_data_classification) > 0
        AND allowed_data_classification <@ ARRAY['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED']::text[]
    ),
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    access_mode text NOT NULL CHECK (access_mode IN (
        'READ', 'CREATE_DRAFT', 'UPDATE_SCOPED', 'REQUEST_APPROVAL',
        'EXECUTE_APPROVED_ACTION'
    )),
    availability text NOT NULL DEFAULT 'AVAILABLE'
        CHECK (availability IN ('AVAILABLE', 'UNAVAILABLE', 'DEGRADED')),
    configuration_status text NOT NULL DEFAULT 'CONFIGURED'
        CHECK (configuration_status IN ('CONFIGURED', 'NEEDS_CONFIGURATION', 'NOT_APPLICABLE')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE capabilities.tools (
    tool_key text PRIMARY KEY CHECK (tool_key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    capability_key text NOT NULL REFERENCES capabilities.definitions,
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 4 AND 1000),
    input_schema jsonb NOT NULL CHECK (jsonb_typeof(input_schema) = 'object'),
    output_schema jsonb NOT NULL CHECK (jsonb_typeof(output_schema) = 'object'),
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    allowed_scopes text[] NOT NULL CHECK (
        cardinality(allowed_scopes) > 0
        AND allowed_scopes <@ ARRAY['COMPANY', 'DIVISION', 'PROJECT', 'OWN_ASSIGNED']::text[]
    ),
    required_permission text NOT NULL,
    access_mode text NOT NULL CHECK (access_mode IN (
        'READ', 'CREATE_DRAFT', 'UPDATE_SCOPED', 'REQUEST_APPROVAL',
        'EXECUTE_APPROVED_ACTION'
    )),
    timeout_seconds integer NOT NULL DEFAULT 15 CHECK (timeout_seconds BETWEEN 1 AND 300),
    idempotency_policy text NOT NULL CHECK (
        idempotency_policy IN ('NONE', 'OPTIONAL', 'REQUIRED')
    ),
    audit_policy text NOT NULL DEFAULT 'ALWAYS' CHECK (audit_policy IN ('ALWAYS', 'ON_WRITE')),
    runtime_handler text NOT NULL CHECK (runtime_handler ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    lifecycle_status text NOT NULL DEFAULT 'APPROVED'
        CHECK (lifecycle_status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'RETIRED')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX capability_definitions_domain_idx
    ON capabilities.definitions (domain, availability, configuration_status);
CREATE INDEX capability_tools_capability_idx
    ON capabilities.tools (capability_key, lifecycle_status);

ALTER TABLE governance.permission_policies
    ADD COLUMN capability_key text REFERENCES capabilities.definitions,
    ADD COLUMN tool_key text REFERENCES capabilities.tools,
    ADD COLUMN access_mode text NOT NULL DEFAULT 'READ' CHECK (access_mode IN (
        'READ', 'CREATE_DRAFT', 'UPDATE_SCOPED', 'REQUEST_APPROVAL',
        'EXECUTE_APPROVED_ACTION'
    )),
    ADD COLUMN resource_type text NOT NULL DEFAULT 'GENERIC',
    ADD COLUMN organization_scope uuid REFERENCES identity.organizations,
    ADD COLUMN division_scope uuid REFERENCES identity.divisions,
    ADD COLUMN project_scope uuid REFERENCES portfolio.projects,
    ADD COLUMN classification text NOT NULL DEFAULT 'INTERNAL'
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    ADD COLUMN conditions jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(conditions) = 'object');

ALTER TABLE governance.permission_policies
    DROP CONSTRAINT IF EXISTS permission_policies_permission_key_check;
ALTER TABLE governance.permission_policies
    ADD CONSTRAINT permission_policies_permission_key_check CHECK (
        permission_key ~ '^[A-Za-z][A-Za-z0-9_.]{2,119}$'
    );

CREATE INDEX permission_policies_capability_tool_idx
    ON governance.permission_policies (capability_key, tool_key, lifecycle_status);

CREATE SCHEMA IF NOT EXISTS operational;

CREATE TABLE operational.tasks (
    task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects ON DELETE RESTRICT,
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 2 AND 200),
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'TODO'
        CHECK (status IN ('DRAFT', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'CANCELLED')),
    priority text NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    due_date date,
    assignee_user_id uuid REFERENCES identity.users,
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    created_by_user_id uuid REFERENCES identity.users,
    created_by_actor_kind text NOT NULL DEFAULT 'HUMAN'
        CHECK (created_by_actor_kind IN ('HUMAN', 'GENESIS', 'AGENT')),
    created_by_agent_version_id uuid REFERENCES agents.versions,
    evidence_required boolean NOT NULL DEFAULT false,
    idempotency_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK ((status = 'DONE') = (completed_at IS NOT NULL)),
    CHECK (created_by_actor_kind <> 'AGENT' OR created_by_agent_version_id IS NOT NULL),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE operational.evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects ON DELETE RESTRICT,
    task_id uuid REFERENCES operational.tasks ON DELETE RESTRICT,
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    uploaded_by_user_id uuid NOT NULL REFERENCES identity.users,
    document_id uuid REFERENCES documents.records ON DELETE RESTRICT,
    object_key text,
    classification text NOT NULL DEFAULT 'INTERNAL'
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    validation_status text NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING', 'VALID', 'INVALID', 'WAIVED')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (task_id IS NOT NULL OR project_id IS NOT NULL),
    CHECK (document_id IS NOT NULL OR object_key IS NOT NULL)
);

CREATE TABLE operational.findings (
    finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects ON DELETE RESTRICT,
    source_kind text NOT NULL CHECK (source_kind IN (
        'DOCUMENT', 'TASK', 'EVIDENCE', 'PROJECT', 'GENESIS', 'AGENT', 'EXTERNAL'
    )),
    source_id uuid,
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 2 AND 200),
    description text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status text NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'DISMISSED')),
    owner_user_id uuid REFERENCES identity.users,
    recommendation text NOT NULL DEFAULT '',
    citation_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(citation_refs) = 'array'),
    generated_by text NOT NULL CHECK (generated_by IN ('HUMAN', 'GENESIS', 'AGENT')),
    generated_by_agent_version_id uuid REFERENCES agents.versions,
    resolution text,
    due_date date,
    created_by_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (generated_by <> 'AGENT' OR generated_by_agent_version_id IS NOT NULL)
);

CREATE TABLE operational.proposed_actions (
    proposed_action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    action_type text NOT NULL CHECK (action_type ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_digest char(64) NOT NULL,
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status text NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVAL_REQUIRED', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED')),
    requested_by_user_id uuid REFERENCES identity.users,
    requested_by_agent_version_id uuid REFERENCES agents.versions,
    created_at timestamptz NOT NULL DEFAULT now(),
    executed_at timestamptz,
    idempotency_key text,
    UNIQUE (organization_id, idempotency_key),
    CHECK (requested_by_user_id IS NOT NULL OR requested_by_agent_version_id IS NOT NULL)
);

CREATE TABLE operational.approval_requests (
    approval_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    approval_kind text NOT NULL CHECK (approval_kind IN (
        'BUSINESS', 'DOCUMENT', 'AGENT', 'PROPOSED_ACTION', 'REPORT'
    )),
    subject_type text NOT NULL,
    subject_id uuid NOT NULL,
    payload_digest char(64) NOT NULL,
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 2 AND 200),
    description text NOT NULL DEFAULT '',
    urgency text NOT NULL DEFAULT 'NORMAL' CHECK (urgency IN ('NORMAL', 'URGENT')),
    status text NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')),
    requested_by_user_id uuid REFERENCES identity.users,
    requested_by_agent_version_id uuid REFERENCES agents.versions,
    approver_user_id uuid REFERENCES identity.users,
    decision_notes text,
    requested_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    approval_token_digest char(64),
    CHECK (requested_by_user_id IS NOT NULL OR requested_by_agent_version_id IS NOT NULL),
    CHECK (requested_by_user_id IS NULL OR approver_user_id IS NULL OR requested_by_user_id <> approver_user_id),
    CHECK (
        (status = 'PENDING' AND approver_user_id IS NULL AND decided_at IS NULL)
        OR (status IN ('APPROVED', 'REJECTED') AND approver_user_id IS NOT NULL AND decided_at IS NOT NULL)
        OR status IN ('CANCELLED', 'EXPIRED')
    )
);

CREATE INDEX operational_tasks_scope_idx
    ON operational.tasks (organization_id, workspace_id, division_id, status, due_date);
CREATE INDEX operational_tasks_assignee_idx
    ON operational.tasks (assignee_user_id, status, due_date);
CREATE INDEX operational_evidence_scope_idx
    ON operational.evidence (organization_id, workspace_id, division_id, task_id, project_id);
CREATE INDEX operational_findings_scope_idx
    ON operational.findings (organization_id, workspace_id, division_id, status, severity, due_date);
CREATE INDEX operational_approvals_inbox_idx
    ON operational.approval_requests (organization_id, workspace_id, status, urgency, requested_at DESC);
CREATE INDEX operational_proposed_actions_status_idx
    ON operational.proposed_actions (organization_id, workspace_id, status, created_at DESC);

CREATE SCHEMA IF NOT EXISTS reporting;

CREATE TABLE reporting.definitions (
    report_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 160),
    template_key text NOT NULL DEFAULT 'EXECUTIVE_SUMMARY',
    scope text NOT NULL CHECK (scope IN ('COMPANY', 'DIVISION', 'PROJECT', 'OWN_ASSIGNED')),
    period text NOT NULL DEFAULT 'ON_DEMAND',
    sections jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sections) = 'array'),
    data_sources jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(data_sources) = 'array'),
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED')),
    review_required boolean NOT NULL DEFAULT true,
    recipient_user_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reporting.schedules (
    report_schedule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_definition_id uuid NOT NULL REFERENCES reporting.definitions ON DELETE CASCADE,
    timezone text NOT NULL DEFAULT 'Asia/Jakarta',
    schedule_expression text NOT NULL,
    next_run_at timestamptz NOT NULL,
    last_run_at timestamptz,
    active boolean NOT NULL DEFAULT false,
    confirmed_by_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_definition_id)
);

CREATE TABLE reporting.reports (
    report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_definition_id uuid NOT NULL REFERENCES reporting.definitions,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    status text NOT NULL DEFAULT 'QUEUED' CHECK (
        status IN ('QUEUED', 'GENERATING', 'DRAFT', 'READY', 'REVIEWED', 'PUBLISHED', 'FAILED')
    ),
    period_start timestamptz,
    period_end timestamptz,
    content jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(content) = 'object'),
    provenance jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(provenance) = 'array'),
    artifact_object_key text,
    idempotency_key text NOT NULL,
    requested_by_user_id uuid REFERENCES identity.users,
    reviewed_by_user_id uuid REFERENCES identity.users,
    published_at timestamptz,
    failure_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_definition_id, idempotency_key)
);

CREATE INDEX reporting_schedules_due_idx ON reporting.schedules (next_run_at) WHERE active;
CREATE INDEX reporting_reports_scope_idx
    ON reporting.reports (organization_id, workspace_id, status, created_at DESC);

CREATE SCHEMA IF NOT EXISTS jobs;

CREATE TABLE jobs.queue (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    job_type text NOT NULL CHECK (job_type IN (
        'DOCUMENT_EXTRACTION', 'DOCUMENT_INDEXING', 'EXTERNAL_RESEARCH', 'AGENT_RUN',
        'SCHEDULED_REPORT', 'RECURRING_MONITOR', 'NOTIFICATION', 'CONNECTOR_SYNC'
    )),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    status text NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    next_retry_at timestamptz NOT NULL DEFAULT now(),
    correlation_id uuid NOT NULL,
    owner_user_id uuid REFERENCES identity.users,
    idempotency_key text NOT NULL,
    locked_by text,
    locked_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    safe_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, job_type, idempotency_key)
);

CREATE INDEX jobs_queue_claim_idx
    ON jobs.queue (status, next_retry_at, created_at) WHERE status IN ('QUEUED', 'FAILED');

CREATE SCHEMA IF NOT EXISTS notifications;

CREATE TABLE notifications.inbox (
    notification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    recipient_user_id uuid NOT NULL REFERENCES identity.users,
    notification_type text NOT NULL CHECK (notification_type IN (
        'PENDING_APPROVAL', 'CRITICAL_FINDING', 'REPORT_READY', 'AGENT_ACTION_APPROVAL'
    )),
    title text NOT NULL,
    body text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX notifications_recipient_unread_idx
    ON notifications.inbox (recipient_user_id, created_at DESC) WHERE read_at IS NULL;

CREATE SCHEMA IF NOT EXISTS kpi;

CREATE TABLE kpi.definitions (
    kpi_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    division_id uuid REFERENCES identity.divisions,
    name text NOT NULL,
    scope text NOT NULL CHECK (scope IN ('COMPANY', 'DIVISION', 'PROJECT')),
    target jsonb NOT NULL CHECK (jsonb_typeof(target) = 'object'),
    data_source_mapping jsonb NOT NULL CHECK (jsonb_typeof(data_source_mapping) = 'object'),
    calculation_strategy text NOT NULL DEFAULT 'NEEDS_CONFIGURATION',
    configuration_status text NOT NULL DEFAULT 'NEEDS_CONFIGURATION'
        CHECK (configuration_status IN ('CONFIGURED', 'NEEDS_CONFIGURATION')),
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    active_from date,
    active_until date,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (active_until IS NULL OR active_from IS NULL OR active_until >= active_from)
);

CREATE TABLE runtime.run_steps (
    run_step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid NOT NULL REFERENCES runtime.agent_runs ON DELETE CASCADE,
    step_sequence integer NOT NULL CHECK (step_sequence > 0),
    step_type text NOT NULL CHECK (step_type IN (
        'PLAN', 'MODEL', 'TOOL_REQUEST', 'TOOL_RESULT', 'APPROVAL_REQUIRED',
        'FINAL', 'FAILED', 'BLOCKED'
    )),
    content jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(content) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_run_id, step_sequence)
);

CREATE TABLE runtime.citations (
    runtime_citation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid NOT NULL REFERENCES runtime.agent_runs ON DELETE CASCADE,
    source_kind text NOT NULL,
    source_id uuid NOT NULL,
    source_version text,
    anchor text,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE genesis.conversations
    ADD COLUMN title text,
    ADD COLUMN context_mode text NOT NULL DEFAULT 'AUTO'
        CHECK (context_mode IN ('AUTO', 'INTERNAL', 'EXTERNAL', 'INTERNAL_AND_EXTERNAL')),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE genesis.conversation_context (
    conversation_context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES genesis.conversations ON DELETE CASCADE,
    entity_type text NOT NULL CHECK (entity_type IN (
        'DOCUMENT', 'PROJECT', 'TASK', 'EVIDENCE', 'FINDING', 'REPORT'
    )),
    entity_id uuid NOT NULL,
    source_version text,
    attached_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, entity_type, entity_id, source_version)
);

CREATE TABLE documents.comparisons (
    document_comparison_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    source_versions jsonb NOT NULL CHECK (
        jsonb_typeof(source_versions) = 'array' AND jsonb_array_length(source_versions) >= 2
    ),
    result jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(result) = 'object'),
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'REVIEWED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE documents.records
    ADD COLUMN source_document_id uuid REFERENCES documents.records ON DELETE RESTRICT,
    ADD COLUMN source_version_number integer CHECK (
        source_version_number IS NULL OR source_version_number > 0
    ),
    ADD CONSTRAINT documents_revision_source_pair_check CHECK (
        (source_document_id IS NULL AND source_version_number IS NULL)
        OR (source_document_id IS NOT NULL AND source_version_number IS NOT NULL)
    );

CREATE INDEX documents_revision_source_idx
    ON documents.records (source_document_id, source_version_number)
    WHERE source_document_id IS NOT NULL;

CREATE INDEX documents_content_search_idx
    ON documents.versions USING gin (to_tsvector('simple', content));
CREATE INDEX operational_tasks_search_idx
    ON operational.tasks USING gin (to_tsvector('simple', title || ' ' || description));
CREATE INDEX operational_findings_search_idx
    ON operational.findings USING gin (to_tsvector('simple', title || ' ' || description));

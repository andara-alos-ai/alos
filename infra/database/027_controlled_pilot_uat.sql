CREATE SCHEMA IF NOT EXISTS uat;

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_id_organization
    ON platform.projects (project_id, organization_id);

CREATE TABLE IF NOT EXISTS uat.runs (
    uat_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    title text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 160),
    cycle_number integer NOT NULL CHECK (cycle_number > 0),
    status text NOT NULL CHECK (status IN (
        'DRAFT', 'IN_PROGRESS', 'READY_FOR_SIGNOFF',
        'ACCEPTED', 'ACCEPTED_WITH_RISK', 'REJECTED'
    )),
    data_policy text NOT NULL CHECK (data_policy = 'SYNTHETIC_OR_SANITIZED'),
    created_by_user_id uuid REFERENCES identity.users,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (project_id, cycle_number)
);

ALTER TABLE uat.runs
    ADD CONSTRAINT uat_runs_project_organization_fk
    FOREIGN KEY (project_id, organization_id)
    REFERENCES platform.projects (project_id, organization_id);

CREATE TABLE IF NOT EXISTS uat.scenario_results (
    scenario_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uat_run_id uuid NOT NULL REFERENCES uat.runs ON DELETE CASCADE,
    scenario_id text NOT NULL CHECK (scenario_id ~ '^UAT-[0-9]{2}$'),
    status text NOT NULL CHECK (status IN (
        'NOT_STARTED', 'IN_PROGRESS', 'PASSED', 'PASSED_WITH_RISK',
        'FAILED', 'BLOCKED'
    )),
    tester_user_id uuid REFERENCES identity.users,
    actual_result text,
    defect_severity text CHECK (
        defect_severity IS NULL OR defect_severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    defect_summary text,
    tested_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (uat_run_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS uat.evidence_references (
    evidence_reference_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_result_id uuid NOT NULL REFERENCES uat.scenario_results ON DELETE CASCADE,
    document_version_id uuid REFERENCES platform.document_versions,
    reference text,
    created_by_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        document_version_id IS NOT NULL
        OR (reference IS NOT NULL AND char_length(reference) BETWEEN 3 AND 500)
    )
);

CREATE TABLE IF NOT EXISTS uat.signoffs (
    signoff_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uat_run_id uuid NOT NULL REFERENCES uat.runs ON DELETE CASCADE,
    signoff_scope text NOT NULL CHECK (signoff_scope IN (
        'SALES_MARKETING', 'FINANCE', 'PROPERTY', 'HR', 'LEGAL',
        'IT', 'AI_EXECUTIVE', 'DIRECTOR'
    )),
    decision text NOT NULL CHECK (decision IN (
        'ACCEPTED', 'ACCEPTED_WITH_RISK', 'REJECTED'
    )),
    signer_user_id uuid REFERENCES identity.users,
    signer_role text NOT NULL,
    notes text NOT NULL CHECK (char_length(notes) BETWEEN 8 AND 1000),
    signed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (uat_run_id, signoff_scope)
);

CREATE INDEX IF NOT EXISTS uat_runs_project_status_idx
    ON uat.runs (organization_id, project_id, status, cycle_number DESC);

CREATE INDEX IF NOT EXISTS uat_scenario_results_run_status_idx
    ON uat.scenario_results (uat_run_id, status, scenario_id);

CREATE INDEX IF NOT EXISTS uat_evidence_scenario_idx
    ON uat.evidence_references (scenario_result_id, created_at);

CREATE INDEX IF NOT EXISTS uat_signoffs_run_scope_idx
    ON uat.signoffs (uat_run_id, signoff_scope);

COMMENT ON SCHEMA uat IS
    'Controlled pilot acceptance records. Human evidence and sign-off remain mandatory.';

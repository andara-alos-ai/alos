CREATE SCHEMA IF NOT EXISTS hr;

CREATE TABLE IF NOT EXISTS hr.recruitment_requests (
    recruitment_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    work_item_id uuid NOT NULL UNIQUE REFERENCES platform.work_items,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    submitted_by_user_id uuid NOT NULL REFERENCES identity.users,
    position_title text NOT NULL,
    requesting_division_code text NOT NULL,
    employment_type text NOT NULL CHECK (
        employment_type IN ('PERMANENT', 'CONTRACT', 'INTERNSHIP')
    ),
    headcount integer NOT NULL CHECK (headcount BETWEEN 1 AND 50),
    justification text NOT NULL,
    criteria_version text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('PENDING_HR_REVIEW', 'SELECTED', 'REJECTED')
    ),
    reviewer_user_id uuid REFERENCES identity.users,
    decision_notes text,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS hr.candidates (
    candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recruitment_request_id uuid NOT NULL UNIQUE REFERENCES hr.recruitment_requests,
    document_version_id uuid NOT NULL REFERENCES platform.document_versions,
    candidate_alias text NOT NULL,
    required_criteria jsonb NOT NULL,
    met_criteria jsonb NOT NULL,
    missing_criteria jsonb NOT NULL,
    screening_status text NOT NULL CHECK (screening_status IN ('COMPLETE', 'INCOMPLETE')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hr.personnel_checklists (
    personnel_checklist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recruitment_request_id uuid NOT NULL UNIQUE REFERENCES hr.recruitment_requests,
    candidate_id uuid NOT NULL UNIQUE REFERENCES hr.candidates,
    created_by_agent_run_id uuid NOT NULL REFERENCES agents.agent_runs,
    status text NOT NULL CHECK (status IN ('OPEN', 'COMPLETE')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hr.personnel_requirements (
    personnel_requirement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    personnel_checklist_id uuid NOT NULL REFERENCES hr.personnel_checklists,
    requirement_code text NOT NULL,
    status text NOT NULL CHECK (status IN ('MISSING', 'SUBMITTED', 'VERIFIED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (personnel_checklist_id, requirement_code)
);

CREATE INDEX IF NOT EXISTS recruitment_queue_idx
    ON hr.recruitment_requests (organization_id, project_id, status, created_at);

CREATE INDEX IF NOT EXISTS personnel_requirements_status_idx
    ON hr.personnel_requirements (personnel_checklist_id, status);

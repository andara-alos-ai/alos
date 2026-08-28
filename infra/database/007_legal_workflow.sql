CREATE SCHEMA IF NOT EXISTS legal;

CREATE TABLE IF NOT EXISTS legal.cases (
    legal_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    work_item_id uuid NOT NULL UNIQUE REFERENCES platform.work_items,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    document_version_id uuid NOT NULL REFERENCES platform.document_versions,
    submitted_by_user_id uuid NOT NULL REFERENCES identity.users,
    document_type text NOT NULL CHECK (document_type IN ('PERMIT', 'CONTRACT')),
    reference_code text NOT NULL,
    title text NOT NULL,
    counterparty text,
    source_authority text,
    effective_date date,
    expiry_date date,
    status text NOT NULL CHECK (
        status IN ('PENDING_REVIEW', 'APPROVED', 'REVISION_REQUESTED', 'REJECTED')
    ),
    reviewer_user_id uuid REFERENCES identity.users,
    legal_status text CHECK (legal_status IN ('VERIFIED', 'CONDITIONAL', 'NOT_APPROVED')),
    official_source_verified boolean NOT NULL DEFAULT false,
    review_notes text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (project_id, document_type, reference_code),
    CHECK (expiry_date IS NULL OR effective_date IS NULL OR expiry_date >= effective_date),
    CHECK (document_type <> 'PERMIT' OR source_authority IS NOT NULL),
    CHECK (document_type <> 'CONTRACT' OR counterparty IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS legal_cases_queue_idx
    ON legal.cases (organization_id, project_id, document_type, status, expiry_date);

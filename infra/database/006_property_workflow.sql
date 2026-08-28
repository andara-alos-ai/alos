CREATE SCHEMA IF NOT EXISTS property;

CREATE TABLE IF NOT EXISTS property.site_evidence (
    site_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    work_item_id uuid NOT NULL UNIQUE REFERENCES platform.work_items,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    document_version_id uuid NOT NULL REFERENCES platform.document_versions,
    submitted_by_user_id uuid NOT NULL REFERENCES identity.users,
    work_package_code text NOT NULL,
    claim_date date NOT NULL,
    claimed_progress numeric(5,2) NOT NULL CHECK (claimed_progress BETWEEN 0 AND 100),
    measured_progress numeric(5,2) NOT NULL CHECK (measured_progress BETWEEN 0 AND 100),
    variance numeric(5,2) NOT NULL CHECK (variance BETWEEN -100 AND 100),
    measurement_note text NOT NULL,
    status text NOT NULL CHECK (status IN ('PENDING_REVIEW', 'ACCEPTED', 'VARIANCE')),
    reviewer_user_id uuid REFERENCES identity.users,
    verified_progress numeric(5,2) CHECK (verified_progress BETWEEN 0 AND 100),
    review_notes text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (project_id, work_package_code, claim_date)
);

CREATE TABLE IF NOT EXISTS executive.kpi_snapshots (
    kpi_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    metric_code text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    value numeric(18,4) NOT NULL,
    unit text NOT NULL,
    source_entity_type text NOT NULL,
    source_entity_id uuid NOT NULL,
    source_agent_run_id uuid REFERENCES agents.agent_runs,
    verification_status text NOT NULL CHECK (verification_status IN ('VERIFIED', 'BLOCKED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start),
    UNIQUE (metric_code, source_entity_type, source_entity_id)
);

CREATE INDEX IF NOT EXISTS site_evidence_queue_idx
    ON property.site_evidence (organization_id, project_id, status, claim_date);

CREATE INDEX IF NOT EXISTS kpi_snapshots_project_idx
    ON executive.kpi_snapshots (organization_id, project_id, metric_code, period_end);

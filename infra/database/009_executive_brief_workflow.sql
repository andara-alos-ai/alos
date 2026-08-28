CREATE TABLE IF NOT EXISTS executive.snapshots (
    executive_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid REFERENCES platform.projects,
    period_start date NOT NULL,
    period_end date NOT NULL,
    facts jsonb NOT NULL,
    source_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start)
);

CREATE TABLE IF NOT EXISTS executive.briefs (
    executive_brief_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    executive_snapshot_id uuid NOT NULL UNIQUE REFERENCES executive.snapshots,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    title text NOT NULL,
    narrative text NOT NULL,
    source_references jsonb NOT NULL,
    status text NOT NULL CHECK (
        status IN ('PENDING_REVIEW', 'PUBLISHED', 'REVISION_REQUESTED')
    ),
    generated_by_agent_run_id uuid NOT NULL REFERENCES agents.agent_runs,
    reviewer_user_id uuid REFERENCES identity.users,
    review_notes text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS executive.decision_items (
    decision_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    executive_brief_id uuid NOT NULL REFERENCES executive.briefs,
    category text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('NORMAL', 'HIGH', 'CRITICAL')),
    title text NOT NULL,
    source_path text NOT NULL,
    status text NOT NULL CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (executive_brief_id, category)
);

CREATE INDEX IF NOT EXISTS executive_snapshots_period_idx
    ON executive.snapshots (organization_id, project_id, period_end);

CREATE INDEX IF NOT EXISTS executive_briefs_status_idx
    ON executive.briefs (status, created_at);

CREATE INDEX IF NOT EXISTS executive_decision_queue_idx
    ON executive.decision_items (status, priority, created_at);

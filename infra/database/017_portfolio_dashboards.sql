-- Canonical portfolio source for the Divisions and Projects dashboards.
-- This migration creates storage only; it deliberately does not seed business data.
CREATE SCHEMA IF NOT EXISTS portfolio;

CREATE TABLE portfolio.projects (
    project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    code text NOT NULL CHECK (code ~ '^[A-Z0-9][A-Z0-9_-]{1,39}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 2 AND 160),
    category text NOT NULL CHECK (length(btrim(category)) BETWEEN 2 AND 80),
    owner_user_id uuid REFERENCES identity.users,
    status text NOT NULL DEFAULT 'ON_TRACK' CHECK (
        status IN ('ON_TRACK', 'AT_RISK', 'CRITICAL', 'COMPLETED', 'ARCHIVED')
    ),
    progress_percent numeric(5,2) NOT NULL DEFAULT 0 CHECK (
        progress_percent >= 0 AND progress_percent <= 100
    ),
    start_date date,
    deadline date,
    budget_planned numeric(18,2) CHECK (budget_planned IS NULL OR budget_planned >= 0),
    budget_spent numeric(18,2) CHECK (budget_spent IS NULL OR budget_spent >= 0),
    currency char(3) NOT NULL DEFAULT 'IDR' CHECK (currency ~ '^[A-Z]{3}$'),
    overdue_tasks integer NOT NULL DEFAULT 0 CHECK (overdue_tasks >= 0),
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (deadline IS NULL OR start_date IS NULL OR deadline >= start_date),
    UNIQUE (organization_id, code)
);

CREATE TABLE portfolio.project_progress_history (
    project_progress_history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES portfolio.projects ON DELETE RESTRICT,
    recorded_on date NOT NULL,
    progress_percent numeric(5,2) NOT NULL CHECK (
        progress_percent >= 0 AND progress_percent <= 100
    ),
    status text NOT NULL CHECK (
        status IN ('ON_TRACK', 'AT_RISK', 'CRITICAL', 'COMPLETED')
    ),
    recorded_by_user_id uuid REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, recorded_on)
);

CREATE TABLE portfolio.project_milestones (
    milestone_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES portfolio.projects ON DELETE RESTRICT,
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 2 AND 180),
    due_date date NOT NULL,
    status text NOT NULL DEFAULT 'ON_TRACK' CHECK (
        status IN ('ON_TRACK', 'AT_RISK', 'CRITICAL', 'COMPLETED')
    ),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE portfolio.division_issues (
    issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects ON DELETE RESTRICT,
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 2 AND 180),
    description text NOT NULL DEFAULT '',
    severity text NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
    owner_user_id uuid REFERENCES identity.users,
    due_date date,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX portfolio_projects_scope_idx
    ON portfolio.projects (organization_id, workspace_id, status, deadline);
CREATE INDEX portfolio_projects_division_idx
    ON portfolio.projects (division_id, status);
CREATE INDEX portfolio_project_history_period_idx
    ON portfolio.project_progress_history (recorded_on, project_id);
CREATE INDEX portfolio_milestones_due_idx
    ON portfolio.project_milestones (due_date, status);
CREATE INDEX portfolio_division_issues_scope_idx
    ON portfolio.division_issues (organization_id, workspace_id, status, severity, due_date);

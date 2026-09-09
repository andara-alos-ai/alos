-- Scoped memory, governed skills, bounded delegation, and generic R&D records.
CREATE SCHEMA IF NOT EXISTS memory;
CREATE TABLE memory.entries (
    memory_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    tenant_id uuid,
    kind text NOT NULL,
    classification text NOT NULL,
    content_digest char(64) NOT NULL,
    source_reference text NOT NULL,
    lineage jsonb NOT NULL CHECK (jsonb_typeof(lineage) = 'object'),
    retention_until timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (retention_until > created_at)
);
CREATE INDEX memory_entries_scope_idx ON memory.entries
    (organization_id, workspace_id, tenant_id, division_id, project_id, created_at DESC);

CREATE SCHEMA IF NOT EXISTS skills;
CREATE TABLE skills.versions (
    skill_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    skill_key text NOT NULL,
    semantic_version text NOT NULL,
    status text NOT NULL CHECK (status IN
        ('PROPOSED','DRAFT','TEST','REVIEW','APPROVED','ACTIVE','DEPRECATED')),
    procedure jsonb NOT NULL CHECK (jsonb_typeof(procedure) = 'object'),
    required_permissions text[] NOT NULL DEFAULT '{}',
    digest char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, workspace_id, skill_key, semantic_version)
);

CREATE TABLE runtime.delegations (
    delegation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_run_id uuid NOT NULL REFERENCES runtime.agent_runs,
    child_run_id uuid REFERENCES runtime.agent_runs,
    child_agent_version_id uuid NOT NULL REFERENCES agents.versions,
    depth integer NOT NULL CHECK (depth >= 1),
    status text NOT NULL CHECK (status IN ('REQUESTED','RUNNING','SUCCEEDED','BLOCKED','FAILED')),
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE SCHEMA IF NOT EXISTS research;
CREATE TABLE research.projects (
    research_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    tenant_id uuid,
    research_type text NOT NULL,
    domain text NOT NULL,
    title text NOT NULL,
    objective text NOT NULL,
    questions jsonb NOT NULL CHECK (jsonb_typeof(questions) = 'array'),
    status text NOT NULL DEFAULT 'REQUEST',
    research_data jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(research_data) = 'object'),
    decision_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX research_projects_scope_status_idx ON research.projects
    (organization_id, workspace_id, tenant_id, status, created_at DESC);

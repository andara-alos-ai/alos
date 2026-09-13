-- Durable governed Skill identity and scoped version lifecycle.
CREATE TABLE skills.skills (
    skill_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects,
    tenant_id uuid,
    skill_key text NOT NULL CHECK (skill_key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 200),
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (organization_id, workspace_id, tenant_id, skill_key)
);

ALTER TABLE skills.versions
    ADD COLUMN skill_id uuid REFERENCES skills.skills,
    ADD COLUMN activated_at timestamptz,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
    ADD CONSTRAINT skill_versions_activation_check CHECK (
        (status = 'ACTIVE' AND activated_at IS NOT NULL) OR status <> 'ACTIVE'
    );

CREATE UNIQUE INDEX skill_versions_scoped_version_idx
    ON skills.versions (skill_id, semantic_version) WHERE skill_id IS NOT NULL;
CREATE INDEX skills_scope_key_idx
    ON skills.skills (organization_id, workspace_id, tenant_id, skill_key);
CREATE INDEX skill_versions_active_idx
    ON skills.versions (skill_id, updated_at DESC) WHERE status = 'ACTIVE';

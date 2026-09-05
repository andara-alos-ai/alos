-- H5 controlled Source Vault boundary. The Runtime never fetches external URLs;
-- this policy records the human-approved Drive root and explicit excluded folder.

CREATE TABLE sources.vault_policies (
    source_vault_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    allowed_root_url text NOT NULL,
    allowed_root_folder_id text NOT NULL,
    excluded_folder_url text NOT NULL,
    excluded_folder_id text NOT NULL,
    access_mode text NOT NULL DEFAULT 'READ_ONLY' CHECK (access_mode = 'READ_ONLY'),
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_by_user_id uuid NOT NULL REFERENCES identity.users,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (allowed_root_folder_id <> excluded_folder_id),
    UNIQUE (organization_id, workspace_id)
);

ALTER TABLE sources.versions
    ADD COLUMN source_vault_policy_id uuid REFERENCES sources.vault_policies,
    ADD COLUMN vault_attested_by_user_id uuid REFERENCES identity.users;

CREATE INDEX source_vault_policies_workspace_idx
    ON sources.vault_policies (organization_id, workspace_id);
CREATE INDEX source_versions_vault_policy_idx
    ON sources.versions (source_vault_policy_id);

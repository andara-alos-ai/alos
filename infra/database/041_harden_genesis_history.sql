-- Tahap 1-3: tenant integrity and auditable Genesis conversation provenance.
-- Existing conversation rows are preserved; invalid cross-tenant references fail
-- the migration instead of being silently repaired.

CREATE UNIQUE INDEX IF NOT EXISTS identity_users_user_organization_uq
    ON identity.users (user_id, organization_id);

CREATE UNIQUE INDEX IF NOT EXISTS platform_projects_project_organization_uq
    ON platform.projects (project_id, organization_id);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM genesis.conversations AS c
        LEFT JOIN platform.projects AS p
          ON p.project_id = c.project_id
         AND p.organization_id = c.organization_id
        WHERE c.project_id IS NOT NULL AND p.project_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Genesis conversation memiliki project lintas organisasi';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM genesis.conversations AS c
        LEFT JOIN identity.users AS u
          ON u.user_id = c.created_by_user_id
         AND u.organization_id = c.organization_id
        WHERE u.user_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Genesis conversation memiliki creator lintas organisasi';
    END IF;
END $$;

ALTER TABLE genesis.conversations
    DROP CONSTRAINT IF EXISTS conversations_project_id_fkey,
    DROP CONSTRAINT IF EXISTS conversations_created_by_user_id_fkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_conversations_project_organization_fk'
    ) THEN
        ALTER TABLE genesis.conversations
            ADD CONSTRAINT genesis_conversations_project_organization_fk
            FOREIGN KEY (project_id, organization_id)
            REFERENCES platform.projects (project_id, organization_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_conversations_creator_organization_fk'
    ) THEN
        ALTER TABLE genesis.conversations
            ADD CONSTRAINT genesis_conversations_creator_organization_fk
            FOREIGN KEY (created_by_user_id, organization_id)
            REFERENCES identity.users (user_id, organization_id);
    END IF;
END $$;

ALTER TABLE genesis.messages
    ADD COLUMN IF NOT EXISTS source_references jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS llm_provider text,
    ADD COLUMN IF NOT EXISTS llm_model text,
    ADD COLUMN IF NOT EXISTS prompt_id text,
    ADD COLUMN IF NOT EXISTS prompt_version text,
    ADD COLUMN IF NOT EXISTS llm_result_status text;

ALTER TABLE genesis.artifact_versions
    ADD COLUMN IF NOT EXISTS diff_data jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS pipeline_request_id uuid REFERENCES genesis.change_requests;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_messages_source_references_array_ck'
    ) THEN
        ALTER TABLE genesis.messages
            ADD CONSTRAINT genesis_messages_source_references_array_ck
            CHECK (jsonb_typeof(source_references) = 'array');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_messages_metadata_object_ck'
    ) THEN
        ALTER TABLE genesis.messages
            ADD CONSTRAINT genesis_messages_metadata_object_ck
            CHECK (jsonb_typeof(metadata) = 'object');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_artifacts_diff_array_ck'
    ) THEN
        ALTER TABLE genesis.artifact_versions
            ADD CONSTRAINT genesis_artifacts_diff_array_ck
            CHECK (jsonb_typeof(diff_data) = 'array');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_artifacts_metadata_object_ck'
    ) THEN
        ALTER TABLE genesis.artifact_versions
            ADD CONSTRAINT genesis_artifacts_metadata_object_ck
            CHECK (jsonb_typeof(metadata) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_genesis_messages_source_refs
    ON genesis.messages USING gin (source_references);

CREATE INDEX IF NOT EXISTS idx_genesis_artifacts_pipeline_request
    ON genesis.artifact_versions (pipeline_request_id)
    WHERE pipeline_request_id IS NOT NULL;

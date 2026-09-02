-- Tahap 3: enforce tenant ownership for every Genesis history actor/reference.
-- Organization identity is copied from the parent conversation, never accepted
-- from a caller, so messages and artifacts cannot point to another tenant.

CREATE UNIQUE INDEX IF NOT EXISTS genesis_conversations_id_organization_uq
    ON genesis.conversations (conversation_id, organization_id);

ALTER TABLE genesis.messages
    ADD COLUMN IF NOT EXISTS organization_id uuid;

UPDATE genesis.messages AS m
SET organization_id = c.organization_id
FROM genesis.conversations AS c
WHERE c.conversation_id = m.conversation_id
  AND m.organization_id IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM genesis.messages WHERE organization_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Genesis message memiliki conversation yang tidak ditemukan';
    END IF;
END $$;

ALTER TABLE genesis.messages
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE genesis.artifact_versions
    ADD COLUMN IF NOT EXISTS organization_id uuid;

UPDATE genesis.artifact_versions AS a
SET organization_id = c.organization_id
FROM genesis.conversations AS c
WHERE c.conversation_id = a.conversation_id
  AND a.organization_id IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM genesis.artifact_versions WHERE organization_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Genesis artifact memiliki conversation yang tidak ditemukan';
    END IF;
END $$;

ALTER TABLE genesis.artifact_versions
    ALTER COLUMN organization_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_messages_conversation_organization_fk'
    ) THEN
        ALTER TABLE genesis.messages
            ADD CONSTRAINT genesis_messages_conversation_organization_fk
            FOREIGN KEY (conversation_id, organization_id)
            REFERENCES genesis.conversations (conversation_id, organization_id)
            ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_messages_sender_organization_fk'
    ) THEN
        ALTER TABLE genesis.messages
            ADD CONSTRAINT genesis_messages_sender_organization_fk
            FOREIGN KEY (sender_user_id, organization_id)
            REFERENCES identity.users (user_id, organization_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_artifacts_conversation_organization_fk'
    ) THEN
        ALTER TABLE genesis.artifact_versions
            ADD CONSTRAINT genesis_artifacts_conversation_organization_fk
            FOREIGN KEY (conversation_id, organization_id)
            REFERENCES genesis.conversations (conversation_id, organization_id)
            ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'genesis_artifacts_creator_organization_fk'
    ) THEN
        ALTER TABLE genesis.artifact_versions
            ADD CONSTRAINT genesis_artifacts_creator_organization_fk
            FOREIGN KEY (created_by_user_id, organization_id)
            REFERENCES identity.users (user_id, organization_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_genesis_messages_org
    ON genesis.messages (organization_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_genesis_artifacts_org
    ON genesis.artifact_versions (organization_id, created_at ASC);

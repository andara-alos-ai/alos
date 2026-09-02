CREATE TABLE IF NOT EXISTS genesis.conversations (
    conversation_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid REFERENCES platform.projects,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    title text NOT NULL,
    status text NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED', 'RELEASED')),
    context_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_genesis_conversations_org
    ON genesis.conversations (organization_id, created_at DESC);

CREATE TABLE IF NOT EXISTS genesis.messages (
    message_id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES genesis.conversations ON DELETE CASCADE,
    sender_type text NOT NULL CHECK (sender_type IN ('USER', 'GENESIS_ASSISTANT', 'SYSTEM')),
    sender_user_id uuid REFERENCES identity.users,
    message_text text NOT NULL,
    analysis_result jsonb,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_genesis_messages_conv
    ON genesis.messages (conversation_id, created_at ASC);

CREATE TABLE IF NOT EXISTS genesis.artifact_versions (
    artifact_version_id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES genesis.conversations ON DELETE CASCADE,
    version_number integer NOT NULL CHECK (version_number >= 1),
    agent_id text NOT NULL,
    spec_data jsonb NOT NULL,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    change_summary text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (conversation_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_genesis_artifact_versions_conv
    ON genesis.artifact_versions (conversation_id, version_number DESC);

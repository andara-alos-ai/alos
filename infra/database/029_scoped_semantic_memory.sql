-- pgvector-backed semantic memory with scope filtering before similarity ranking.
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE memory.entries
    ADD COLUMN content text,
    ADD COLUMN created_by_user_id uuid REFERENCES identity.users,
    ADD COLUMN idempotency_key text,
    ADD COLUMN expired_at timestamptz,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
    ADD CONSTRAINT memory_entries_classification_check CHECK (
        classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')
    ),
    ADD CONSTRAINT memory_entries_expiry_check CHECK (
        expired_at IS NULL OR expired_at >= created_at
    );

CREATE UNIQUE INDEX memory_entries_idempotency_idx
    ON memory.entries (organization_id, created_by_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE memory.embeddings (
    memory_id uuid PRIMARY KEY REFERENCES memory.entries ON DELETE CASCADE,
    provider text NOT NULL CHECK (char_length(btrim(provider)) BETWEEN 1 AND 100),
    model text NOT NULL CHECK (char_length(btrim(model)) BETWEEN 1 AND 200),
    dimension integer NOT NULL CHECK (dimension BETWEEN 1 AND 2000),
    embedding vector NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    estimated_cost_usd numeric(12, 6) NOT NULL DEFAULT 0
        CHECK (estimated_cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (vector_dims(embedding) = dimension)
);

CREATE INDEX memory_embeddings_model_idx ON memory.embeddings (provider, model, dimension);

CREATE INDEX memory_entries_retrieval_idx ON memory.entries (
    organization_id, workspace_id, tenant_id, division_id, project_id, retention_until
) WHERE expired_at IS NULL;

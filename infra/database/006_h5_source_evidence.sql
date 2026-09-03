-- H5 Source Registry: versioned, read-only evidence content for local/staging validation.
-- Source rows and audit events are never deleted by application code.

CREATE TABLE sources.content_chunks (
    source_chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version_id uuid NOT NULL REFERENCES sources.versions ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    citation_key text NOT NULL,
    anchor text NOT NULL,
    content_text text NOT NULL,
    content_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_version_id, chunk_index),
    UNIQUE (source_version_id, citation_key)
);

CREATE INDEX source_content_chunks_version_idx
    ON sources.content_chunks (source_version_id, chunk_index);
CREATE INDEX source_content_chunks_digest_idx
    ON sources.content_chunks (content_sha256);

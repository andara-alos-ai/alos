-- Genesis document intake: an uploaded binary is retained separately from
-- canonical Documents and source evidence. Every row remains SOURCE_RECEIVED
-- until a later human review/import step explicitly promotes it.

CREATE TABLE genesis.document_uploads (
    genesis_upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    uploaded_by_user_id uuid NOT NULL REFERENCES identity.users,
    original_filename text NOT NULL CHECK (char_length(original_filename) BETWEEN 1 AND 200),
    extension text NOT NULL CHECK (extension IN ('pdf', 'docx', 'xlsx', 'xls', 'csv', 'json', 'md', 'txt')),
    declared_content_type text,
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    object_key text NOT NULL UNIQUE,
    file_sha256 char(64) NOT NULL,
    status text NOT NULL DEFAULT 'SOURCE_RECEIVED' CHECK (status = 'SOURCE_RECEIVED'),
    extraction_status text NOT NULL CHECK (
        extraction_status IN ('EXTRACTED', 'NO_TEXT', 'EXTRACTOR_UNAVAILABLE', 'TRUNCATED')
    ),
    extraction_complete boolean NOT NULL DEFAULT false,
    extracted_text text,
    extracted_text_sha256 char(64),
    extraction_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (extracted_text IS NULL AND extracted_text_sha256 IS NULL)
        OR (extracted_text IS NOT NULL AND extracted_text_sha256 IS NOT NULL)
    )
);

CREATE INDEX genesis_document_uploads_workspace_created_idx
    ON genesis.document_uploads (organization_id, workspace_id, created_at DESC);

-- Document Center: one canonical record for human and Genesis-originated drafts.
-- Content revisions are append-only. A document can never become ACTIVE automatically.
CREATE SCHEMA IF NOT EXISTS documents;

CREATE TABLE documents.records (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid REFERENCES identity.divisions,
    genesis_conversation_id uuid REFERENCES genesis.conversations,
    title text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 200),
    category text NOT NULL DEFAULT 'GENERAL' CHECK (category ~ '^[A-Z][A-Z0-9_ ]{1,79}$'),
    classification text NOT NULL DEFAULT 'INTERNAL'
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    origin text NOT NULL CHECK (origin IN ('MANUAL', 'GENESIS')),
    status text NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'ACTIVE', 'REJECTED', 'ARCHIVED')),
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents.versions (
    document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents.records,
    version_number integer NOT NULL CHECK (version_number > 0),
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 50000),
    content_sha256 char(64) NOT NULL,
    created_by_user_id uuid REFERENCES identity.users,
    generated_by_system boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, version_number)
);

CREATE TABLE documents.checklist_items (
    document_checklist_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id uuid NOT NULL REFERENCES documents.versions,
    check_key text NOT NULL CHECK (check_key ~ '^[A-Z][A-Z0-9_]{2,79}$'),
    label text NOT NULL,
    check_type text NOT NULL CHECK (check_type IN ('AUTOMATED', 'HUMAN')),
    required boolean NOT NULL DEFAULT true,
    status text NOT NULL CHECK (status IN ('PENDING', 'PASSED', 'WAIVED')),
    notes text,
    completed_by_user_id uuid REFERENCES identity.users,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (check_type = 'AUTOMATED' AND status = 'PASSED' AND completed_by_user_id IS NULL)
        OR (check_type = 'HUMAN')
    ),
    UNIQUE (document_version_id, check_key)
);

CREATE TABLE documents.review_requests (
    document_review_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents.records,
    document_version_id uuid NOT NULL REFERENCES documents.versions,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    submitted_by_user_id uuid NOT NULL REFERENCES identity.users,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    reviewer_user_id uuid REFERENCES identity.users,
    decided_at timestamptz,
    notes text,
    CHECK (
        (status = 'PENDING' AND reviewer_user_id IS NULL AND decided_at IS NULL)
        OR (status IN ('APPROVED', 'REJECTED') AND reviewer_user_id IS NOT NULL AND decided_at IS NOT NULL)
    )
);

CREATE INDEX documents_records_workspace_updated_idx
    ON documents.records (workspace_id, updated_at DESC);
CREATE INDEX documents_records_organization_status_idx
    ON documents.records (organization_id, status, updated_at DESC);
CREATE INDEX documents_versions_document_idx
    ON documents.versions (document_id, version_number DESC);
CREATE INDEX documents_review_requests_document_idx
    ON documents.review_requests (document_id, submitted_at DESC);

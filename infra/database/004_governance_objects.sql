ALTER TABLE platform.documents
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS documents_project_idx
    ON platform.documents (organization_id, project_id, created_at);

CREATE INDEX IF NOT EXISTS evidence_work_item_idx
    ON platform.evidence (work_item_id, status, created_at);

CREATE INDEX IF NOT EXISTS approval_work_item_idx
    ON governance.approval_requests (work_item_id, status, created_at);

CREATE INDEX IF NOT EXISTS capa_exception_idx
    ON governance.capas (exception_id, status, due_at);

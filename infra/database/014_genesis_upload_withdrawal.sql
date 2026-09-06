-- A mistaken source can be withdrawn before it becomes a canonical Document
-- Center DRAFT. The stored binary and extracted text are erased; audit events
-- remain append-only.

ALTER TABLE genesis.document_uploads
    DROP CONSTRAINT document_uploads_status_check;

ALTER TABLE genesis.document_uploads
    ADD CONSTRAINT document_uploads_status_check
    CHECK (status IN ('SOURCE_RECEIVED', 'DRAFT_CREATED', 'WITHDRAWAL_PENDING', 'WITHDRAWN'));

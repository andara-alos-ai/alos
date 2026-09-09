-- A Director can explicitly promote one fully extracted Genesis upload into
-- one canonical Document Center DRAFT. Neither promotion nor later document
-- approval changes the original uploaded binary.

ALTER TABLE documents.records
    ADD COLUMN genesis_upload_id uuid UNIQUE REFERENCES genesis.document_uploads;

ALTER TABLE genesis.document_uploads
    ADD COLUMN canonical_document_id uuid UNIQUE REFERENCES documents.records;

ALTER TABLE genesis.document_uploads
    DROP CONSTRAINT document_uploads_status_check;

ALTER TABLE genesis.document_uploads
    ADD CONSTRAINT document_uploads_status_check
    CHECK (status IN ('SOURCE_RECEIVED', 'DRAFT_CREATED'));

CREATE INDEX documents_records_genesis_upload_idx
    ON documents.records (genesis_upload_id)
    WHERE genesis_upload_id IS NOT NULL;

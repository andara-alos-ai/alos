ALTER TABLE platform.documents
    ADD COLUMN IF NOT EXISTS division_id uuid REFERENCES identity.divisions;

ALTER TABLE platform.document_versions
    ADD COLUMN IF NOT EXISTS original_filename text,
    ADD COLUMN IF NOT EXISTS storage_provider text NOT NULL DEFAULT 'EXTERNAL_REFERENCE',
    ADD COLUMN IF NOT EXISTS bucket_name text,
    ADD COLUMN IF NOT EXISTS storage_etag text,
    ADD COLUMN IF NOT EXISTS scan_status text NOT NULL DEFAULT 'NOT_CONFIGURED';

ALTER TABLE platform.document_versions
    DROP CONSTRAINT IF EXISTS document_versions_storage_provider_check;

ALTER TABLE platform.document_versions
    ADD CONSTRAINT document_versions_storage_provider_check
    CHECK (storage_provider IN ('EXTERNAL_REFERENCE', 'FILESYSTEM', 'S3'));

ALTER TABLE platform.document_versions
    DROP CONSTRAINT IF EXISTS document_versions_scan_status_check;

ALTER TABLE platform.document_versions
    ADD CONSTRAINT document_versions_scan_status_check
    CHECK (scan_status IN ('NOT_CONFIGURED', 'PENDING', 'CLEAN', 'REJECTED', 'ERROR'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_storage_object
    ON platform.document_versions (bucket_name, object_key)
    WHERE bucket_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_scope
    ON platform.documents (organization_id, division_id, project_id, classification);

CREATE INDEX IF NOT EXISTS idx_document_versions_document_created
    ON platform.document_versions (document_id, version_number DESC, created_at DESC);

COMMENT ON COLUMN platform.documents.division_id IS
    'Business-owning division. NULL is reserved for organization-wide shared documents.';

COMMENT ON COLUMN platform.document_versions.storage_provider IS
    'Immutable location type. EXTERNAL_REFERENCE identifies legacy metadata-only records.';

COMMENT ON COLUMN platform.document_versions.scan_status IS
    'Malware scan state. Production configuration must not leave scanning disabled.';

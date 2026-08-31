ALTER TABLE sales.interactions
    ADD COLUMN IF NOT EXISTS evidence_document_version_id uuid
        REFERENCES platform.document_versions;

ALTER TABLE sales.reservations
    ADD COLUMN IF NOT EXISTS evidence_document_version_id uuid
        REFERENCES platform.document_versions;

CREATE INDEX IF NOT EXISTS sales_interactions_evidence_idx
    ON sales.interactions (evidence_document_version_id)
    WHERE evidence_document_version_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS sales_reservations_evidence_idx
    ON sales.reservations (evidence_document_version_id)
    WHERE evidence_document_version_id IS NOT NULL;

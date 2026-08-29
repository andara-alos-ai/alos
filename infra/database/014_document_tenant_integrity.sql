CREATE UNIQUE INDEX IF NOT EXISTS uq_divisions_id_organization
    ON identity.divisions (division_id, organization_id);

ALTER TABLE platform.documents
    DROP CONSTRAINT IF EXISTS documents_division_organization_fk;

ALTER TABLE platform.documents
    ADD CONSTRAINT documents_division_organization_fk
    FOREIGN KEY (division_id, organization_id)
    REFERENCES identity.divisions (division_id, organization_id);

COMMENT ON CONSTRAINT documents_division_organization_fk ON platform.documents IS
    'Prevents a document from referencing a division owned by another organization.';

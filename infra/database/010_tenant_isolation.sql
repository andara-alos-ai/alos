ALTER TABLE identity.users
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

UPDATE identity.users u
SET organization_id = source.organization_id
FROM (
    SELECT DISTINCT ra.user_id, d.organization_id
    FROM identity.role_assignments ra
    JOIN identity.divisions d ON d.division_id = ra.division_id
) source
WHERE u.user_id = source.user_id
  AND u.organization_id IS NULL;

UPDATE identity.users
SET organization_id = (
    SELECT organization_id FROM identity.organizations
    ORDER BY organization_id::text
    LIMIT 1
)
WHERE organization_id IS NULL
  AND (SELECT count(*) FROM identity.organizations) = 1;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM identity.users WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot backfill organization_id for all identity.users';
    END IF;
END $$;

ALTER TABLE identity.users
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE governance.exceptions
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

UPDATE governance.exceptions e
SET organization_id = wi.organization_id
FROM platform.work_items wi
WHERE e.work_item_id = wi.work_item_id
  AND e.organization_id IS NULL;

UPDATE governance.exceptions e
SET organization_id = u.organization_id
FROM identity.users u
WHERE e.owner_user_id = u.user_id
  AND e.organization_id IS NULL;

UPDATE governance.exceptions
SET organization_id = (
    SELECT organization_id FROM identity.organizations
    ORDER BY organization_id::text
    LIMIT 1
)
WHERE organization_id IS NULL
  AND (SELECT count(*) FROM identity.organizations) = 1;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM governance.exceptions WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot backfill organization_id for all governance.exceptions';
    END IF;
END $$;

ALTER TABLE governance.exceptions
    ALTER COLUMN organization_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS users_organization_idx
    ON identity.users (organization_id, status);

CREATE INDEX IF NOT EXISTS exceptions_organization_idx
    ON governance.exceptions (organization_id, status, severity, due_at);

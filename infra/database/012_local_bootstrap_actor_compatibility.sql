ALTER TABLE identity.project_assignments
    ALTER COLUMN created_by DROP NOT NULL;

COMMENT ON COLUMN identity.project_assignments.created_by IS
    'Nullable only for local bootstrap; released environments validate the actor identity.';

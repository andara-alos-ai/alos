ALTER TABLE identity.role_assignments
    ADD COLUMN IF NOT EXISTS reason text,
    ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES identity.users;

UPDATE identity.role_assignments
SET reason = 'Migrasi penugasan akses sebelum IAM v1'
WHERE reason IS NULL;

ALTER TABLE identity.role_assignments
    ALTER COLUMN reason SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS active_role_assignment_unique_idx
    ON identity.role_assignments (
        user_id,
        role_code,
        COALESCE(division_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE valid_until IS NULL;

CREATE INDEX IF NOT EXISTS role_assignments_active_idx
    ON identity.role_assignments (user_id, valid_from, valid_until);

CREATE TABLE IF NOT EXISTS identity.project_assignments (
    assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES identity.users,
    project_id uuid NOT NULL REFERENCES platform.projects,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    reason text NOT NULL,
    created_by uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS active_project_assignment_unique_idx
    ON identity.project_assignments (user_id, project_id)
    WHERE valid_until IS NULL;

CREATE INDEX IF NOT EXISTS project_assignments_active_idx
    ON identity.project_assignments (user_id, valid_from, valid_until);

-- H5: retain maker and approver identity for version-bound permission policies.
-- Existing policies remain readable; all policies created by the API set both fields.

ALTER TABLE governance.permission_policies
    ADD COLUMN created_by_user_id uuid REFERENCES identity.users,
    ADD COLUMN approved_by_user_id uuid REFERENCES identity.users;

CREATE INDEX permission_policies_approval_idx
    ON governance.permission_policies (organization_id, lifecycle_status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_id_organization
    ON identity.users (user_id, organization_id);

ALTER TABLE platform.work_items
    ADD COLUMN IF NOT EXISTS claimed_at timestamptz,
    ADD COLUMN IF NOT EXISTS completed_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_reminded_at timestamptz,
    ADD COLUMN IF NOT EXISTS escalated_at timestamptz,
    ADD COLUMN IF NOT EXISTS escalation_level integer NOT NULL DEFAULT 0;

ALTER TABLE platform.work_items
    DROP CONSTRAINT IF EXISTS work_items_escalation_level_check;

ALTER TABLE platform.work_items
    ADD CONSTRAINT work_items_escalation_level_check
    CHECK (escalation_level BETWEEN 0 AND 10);

ALTER TABLE platform.work_items
    DROP CONSTRAINT IF EXISTS work_items_division_organization_fk;

ALTER TABLE platform.work_items
    ADD CONSTRAINT work_items_division_organization_fk
    FOREIGN KEY (division_id, organization_id)
    REFERENCES identity.divisions (division_id, organization_id);

ALTER TABLE platform.work_items
    DROP CONSTRAINT IF EXISTS work_items_owner_organization_fk;

ALTER TABLE platform.work_items
    ADD CONSTRAINT work_items_owner_organization_fk
    FOREIGN KEY (owner_user_id, organization_id)
    REFERENCES identity.users (user_id, organization_id);

CREATE TABLE IF NOT EXISTS platform.work_item_assignments (
    work_item_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    work_item_id uuid NOT NULL REFERENCES platform.work_items,
    from_user_id uuid REFERENCES identity.users,
    to_user_id uuid REFERENCES identity.users,
    action text NOT NULL CHECK (action IN ('CLAIM', 'ASSIGN', 'DELEGATE', 'RELEASE')),
    reason text NOT NULL,
    assigned_by_user_id uuid REFERENCES identity.users,
    assigned_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS work_item_assignments_history_idx
    ON platform.work_item_assignments (work_item_id, assigned_at DESC);

CREATE TABLE IF NOT EXISTS platform.reminders (
    reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    work_item_id uuid REFERENCES platform.work_items,
    approval_request_id uuid REFERENCES governance.approval_requests,
    recipient_user_id uuid REFERENCES identity.users,
    division_id uuid REFERENCES identity.divisions,
    reminder_type text NOT NULL CHECK (
        reminder_type IN ('DUE_SOON', 'OVERDUE', 'ESCALATION')
    ),
    escalation_level integer NOT NULL DEFAULT 0 CHECK (escalation_level BETWEEN 0 AND 10),
    status text NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'DELIVERED', 'ACKNOWLEDGED', 'CANCELLED')
    ),
    scheduled_for timestamptz NOT NULL,
    delivered_at timestamptz,
    acknowledged_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (work_item_id IS NOT NULL OR approval_request_id IS NOT NULL),
    CHECK (recipient_user_id IS NOT NULL OR division_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS pending_work_item_reminder_unique_idx
    ON platform.reminders (work_item_id, reminder_type, escalation_level)
    WHERE status = 'PENDING' AND work_item_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS pending_approval_reminder_unique_idx
    ON platform.reminders (approval_request_id, reminder_type, escalation_level)
    WHERE status = 'PENDING' AND approval_request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS reminders_inbox_idx
    ON platform.reminders (
        organization_id, status, recipient_user_id, division_id, scheduled_for
    );

ALTER TABLE governance.approval_requests
    ADD COLUMN IF NOT EXISTS assigned_approver_user_id uuid REFERENCES identity.users,
    ADD COLUMN IF NOT EXISTS claimed_at timestamptz,
    ADD COLUMN IF NOT EXISTS due_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_reminded_at timestamptz,
    ADD COLUMN IF NOT EXISTS escalated_at timestamptz,
    ADD COLUMN IF NOT EXISTS escalation_level integer NOT NULL DEFAULT 0;

ALTER TABLE governance.approval_requests
    DROP CONSTRAINT IF EXISTS approval_requests_escalation_level_check;

ALTER TABLE governance.approval_requests
    ADD CONSTRAINT approval_requests_escalation_level_check
    CHECK (escalation_level BETWEEN 0 AND 10);

ALTER TABLE governance.exceptions
    ADD COLUMN IF NOT EXISTS resolution_reason text,
    ADD COLUMN IF NOT EXISTS resolution_document_version_id uuid
        REFERENCES platform.document_versions,
    ADD COLUMN IF NOT EXISTS resolved_at timestamptz,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE governance.capas
    ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES identity.users,
    ADD COLUMN IF NOT EXISTS verification_notes text,
    ADD COLUMN IF NOT EXISTS evidence_document_version_id uuid
        REFERENCES platform.document_versions,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS work_items_personal_inbox_idx
    ON platform.work_items (
        organization_id, owner_user_id, status, due_at, priority
    );

CREATE INDEX IF NOT EXISTS approvals_operational_inbox_idx
    ON governance.approval_requests (
        status, assigned_approver_user_id, due_at, created_at
    );

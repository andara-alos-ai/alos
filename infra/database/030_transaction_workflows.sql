CREATE TABLE IF NOT EXISTS platform.command_receipts (
    command_receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    operation text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash char(64) NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    response_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, operation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS command_receipts_entity_idx
    ON platform.command_receipts (organization_id, entity_type, entity_id, created_at);

ALTER TABLE platform.reminders
    DROP CONSTRAINT IF EXISTS reminders_reminder_type_check;

ALTER TABLE platform.reminders
    ADD CONSTRAINT reminders_reminder_type_check CHECK (
        reminder_type IN ('DUE_SOON', 'OVERDUE', 'ESCALATION', 'FOLLOW_UP')
    );

ALTER TABLE sales.leads
    ADD COLUMN IF NOT EXISTS pipeline_stage text NOT NULL DEFAULT 'NEW',
    ADD COLUMN IF NOT EXISTS qualification_result text,
    ADD COLUMN IF NOT EXISTS qualification_notes text,
    ADD COLUMN IF NOT EXISTS lost_reason text,
    ADD COLUMN IF NOT EXISTS converted_at timestamptz,
    ADD COLUMN IF NOT EXISTS lost_at timestamptz;

ALTER TABLE sales.leads
    DROP CONSTRAINT IF EXISTS leads_status_check;

ALTER TABLE sales.leads
    ADD CONSTRAINT leads_status_check CHECK (
        status IN ('RECEIVED', 'VALIDATED', 'ASSIGNED', 'FOLLOW_UP', 'QUALIFIED',
                   'RESERVED', 'DISQUALIFIED', 'LOST', 'EXCEPTION')
    );

ALTER TABLE sales.leads
    ADD CONSTRAINT leads_pipeline_stage_check CHECK (
        pipeline_stage IN ('NEW', 'QUALIFICATION', 'FOLLOW_UP', 'QUALIFIED',
                           'RESERVATION', 'CONVERTED', 'LOST', 'EXCEPTION')
    );

ALTER TABLE sales.leads
    ADD CONSTRAINT leads_qualification_result_check CHECK (
        qualification_result IS NULL
        OR qualification_result IN ('HOT', 'WARM', 'COLD', 'NOT_QUALIFIED')
    );

ALTER TABLE sales.follow_up_tasks
    ADD COLUMN IF NOT EXISTS reminder_id uuid REFERENCES platform.reminders,
    ADD COLUMN IF NOT EXISTS objective text,
    ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS follow_up_tasks_idempotency_idx
    ON sales.follow_up_tasks (workflow_run_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE sales.interactions
    ADD COLUMN IF NOT EXISTS qualification_result text,
    ADD COLUMN IF NOT EXISTS lost_reason text,
    ADD COLUMN IF NOT EXISTS next_follow_up_at timestamptz,
    ADD COLUMN IF NOT EXISTS idempotency_key text;

ALTER TABLE sales.interactions
    DROP CONSTRAINT IF EXISTS interactions_outcome_check;

ALTER TABLE sales.interactions
    ADD CONSTRAINT interactions_outcome_check CHECK (
        outcome IN ('qualified', 'reserved', 'follow_up', 'lost', 'exception')
    );

ALTER TABLE sales.interactions
    ADD CONSTRAINT interactions_qualification_result_check CHECK (
        qualification_result IS NULL
        OR qualification_result IN ('HOT', 'WARM', 'COLD', 'NOT_QUALIFIED')
    );

CREATE UNIQUE INDEX IF NOT EXISTS sales_interactions_idempotency_idx
    ON sales.interactions (workflow_run_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE sales.reservations
    ADD COLUMN IF NOT EXISTS reservation_date date NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS notes text,
    ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS sales_reservations_idempotency_idx
    ON sales.reservations (workflow_run_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE governance.approval_requests
    DROP CONSTRAINT IF EXISTS approval_requests_status_check;

ALTER TABLE governance.approval_requests
    ADD CONSTRAINT approval_requests_status_check CHECK (
        status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED',
                   'CANCELLED', 'EXPIRED')
    );

ALTER TABLE governance.approval_requests
    ADD COLUMN IF NOT EXISTS required_role_code text,
    ADD COLUMN IF NOT EXISTS required_division_code text,
    ADD COLUMN IF NOT EXISTS routing_rule text;

ALTER TABLE finance.payment_requests
    ADD COLUMN IF NOT EXISTS category_code text NOT NULL DEFAULT 'GENERAL',
    ADD COLUMN IF NOT EXISTS vendor_reference text,
    ADD COLUMN IF NOT EXISTS evidence_complete boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS approval_route text,
    ADD COLUMN IF NOT EXISTS revision_number integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cancelled_by_user_id uuid REFERENCES identity.users,
    ADD COLUMN IF NOT EXISTS cancelled_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancellation_reason text;

ALTER TABLE finance.payment_requests
    DROP CONSTRAINT IF EXISTS payment_requests_status_check;

ALTER TABLE finance.payment_requests
    ADD CONSTRAINT payment_requests_status_check CHECK (
        status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED',
                   'PAID', 'RECONCILED', 'EXCEPTION', 'CANCELLED')
    );

ALTER TABLE finance.payment_requests
    ADD CONSTRAINT payment_requests_revision_number_check CHECK (revision_number >= 0);

CREATE TABLE IF NOT EXISTS finance.payment_checks (
    payment_check_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_request_id uuid NOT NULL REFERENCES finance.payment_requests,
    revision_number integer NOT NULL DEFAULT 0 CHECK (revision_number >= 0),
    check_type text NOT NULL CHECK (
        check_type IN ('DOCUMENT', 'EVIDENCE', 'BUDGET', 'APPROVAL_ROUTE')
    ),
    agent_id text NOT NULL,
    agent_run_id uuid REFERENCES agents.agent_runs,
    status text NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'NEEDS_REVIEW')),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    checked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_request_id, revision_number, check_type)
);

CREATE INDEX IF NOT EXISTS payment_checks_request_idx
    ON finance.payment_checks (payment_request_id, revision_number, checked_at);

ALTER TABLE finance.payment_records
    ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS payment_records_idempotency_idx
    ON finance.payment_records (payment_request_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE finance.reconciliations
    ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS reconciliations_idempotency_idx
    ON finance.reconciliations (payment_request_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_requests_due_queue_idx
    ON finance.payment_requests (
        organization_id, project_id, status, requested_payment_date, category_code
    );

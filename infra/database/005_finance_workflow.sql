CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE IF NOT EXISTS finance.budgets (
    budget_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    code text NOT NULL,
    name text NOT NULL,
    currency char(3) NOT NULL,
    allocated_amount numeric(18,2) NOT NULL CHECK (allocated_amount > 0),
    committed_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (committed_amount >= 0),
    spent_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (spent_amount >= 0),
    status text NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES identity.users,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    UNIQUE (project_id, code),
    CHECK (committed_amount + spent_amount <= allocated_amount)
);

CREATE TABLE IF NOT EXISTS finance.payment_requests (
    payment_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    project_id uuid NOT NULL REFERENCES platform.projects,
    budget_id uuid NOT NULL REFERENCES finance.budgets,
    work_item_id uuid NOT NULL UNIQUE REFERENCES platform.work_items,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    approval_request_id uuid UNIQUE REFERENCES governance.approval_requests,
    document_version_id uuid NOT NULL REFERENCES platform.document_versions,
    requester_user_id uuid NOT NULL REFERENCES identity.users,
    payee_name text NOT NULL,
    purpose text NOT NULL,
    amount numeric(18,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL,
    requested_payment_date date NOT NULL,
    status text NOT NULL CHECK (
        status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED',
                   'PAID', 'RECONCILED', 'EXCEPTION')
    ),
    budget_available boolean NOT NULL,
    material_fingerprint char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS finance.payment_records (
    payment_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_request_id uuid NOT NULL UNIQUE REFERENCES finance.payment_requests,
    payment_reference text NOT NULL UNIQUE,
    amount numeric(18,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL,
    paid_at timestamptz NOT NULL,
    evidence_document_version_id uuid NOT NULL REFERENCES platform.document_versions,
    recorded_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance.reconciliations (
    reconciliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_request_id uuid NOT NULL UNIQUE REFERENCES finance.payment_requests,
    payment_record_id uuid NOT NULL UNIQUE REFERENCES finance.payment_records,
    transaction_reference text NOT NULL,
    transaction_amount numeric(18,2) NOT NULL CHECK (transaction_amount > 0),
    currency char(3) NOT NULL,
    status text NOT NULL CHECK (status IN ('MATCHED', 'MISMATCH')),
    difference_amount numeric(18,2) NOT NULL,
    created_by_agent_run_id uuid REFERENCES agents.agent_runs,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS budgets_project_idx
    ON finance.budgets (organization_id, project_id, status);
CREATE INDEX IF NOT EXISTS payment_requests_queue_idx
    ON finance.payment_requests (organization_id, project_id, status, requested_payment_date);

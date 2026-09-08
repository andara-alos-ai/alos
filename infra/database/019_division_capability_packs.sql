-- Extensible canonical records for six business capability packs.
-- No company business data is seeded by this migration.

CREATE SCHEMA IF NOT EXISTS business;

CREATE TABLE business.records (
    business_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    division_id uuid NOT NULL REFERENCES identity.divisions,
    project_id uuid REFERENCES portfolio.projects ON DELETE RESTRICT,
    domain text NOT NULL CHECK (domain IN (
        'FINANCE', 'SALES_MARKETING', 'PROPERTY', 'HR', 'LEGAL', 'IT'
    )),
    record_type text NOT NULL CHECK (record_type IN (
        'BUDGET', 'INVOICE', 'RECEIVABLE', 'PAYABLE', 'CASHFLOW', 'PAYMENT_REQUEST',
        'LEAD', 'OPPORTUNITY', 'CAMPAIGN', 'PIPELINE_SNAPSHOT',
        'MILESTONE', 'PERMIT', 'RISK',
        'EMPLOYEE_DIRECTORY', 'ATTENDANCE_SUMMARY', 'TRAINING', 'PERFORMANCE_CYCLE',
        'OPEN_POSITION', 'CONTRACT', 'LICENSE', 'COMPLIANCE_REVIEW',
        'SYSTEM', 'INTEGRATION', 'INCIDENT', 'RELEASE_CONTROL'
    )),
    record_key text NOT NULL CHECK (char_length(btrim(record_key)) BETWEEN 2 AND 100),
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 2 AND 200),
    status text NOT NULL DEFAULT 'DRAFT',
    classification text NOT NULL DEFAULT 'INTERNAL'
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    effective_date date,
    expires_at timestamptz,
    owner_user_id uuid NOT NULL REFERENCES identity.users,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, domain, record_type, record_key),
    CHECK (
        (domain = 'FINANCE' AND record_type IN (
            'BUDGET', 'INVOICE', 'RECEIVABLE', 'PAYABLE', 'CASHFLOW', 'PAYMENT_REQUEST'
        )) OR
        (domain = 'SALES_MARKETING' AND record_type IN (
            'LEAD', 'OPPORTUNITY', 'CAMPAIGN', 'PIPELINE_SNAPSHOT'
        )) OR
        (domain = 'PROPERTY' AND record_type IN ('MILESTONE', 'PERMIT', 'RISK')) OR
        (domain = 'HR' AND record_type IN (
            'EMPLOYEE_DIRECTORY', 'ATTENDANCE_SUMMARY', 'TRAINING',
            'PERFORMANCE_CYCLE', 'OPEN_POSITION'
        )) OR
        (domain = 'LEGAL' AND record_type IN (
            'CONTRACT', 'PERMIT', 'LICENSE', 'COMPLIANCE_REVIEW'
        )) OR
        (domain = 'IT' AND record_type IN (
            'SYSTEM', 'INTEGRATION', 'INCIDENT', 'RELEASE_CONTROL'
        ))
    )
);

CREATE INDEX business_records_scope_idx
    ON business.records (organization_id, workspace_id, division_id, domain, record_type, status);
CREATE INDEX business_records_project_idx
    ON business.records (project_id, record_type) WHERE project_id IS NOT NULL;
CREATE INDEX business_records_expiry_idx
    ON business.records (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX business_records_search_idx
    ON business.records USING gin (to_tsvector('simple', title || ' ' || record_key));

CREATE VIEW business.finance_records AS
    SELECT * FROM business.records WHERE domain = 'FINANCE';
CREATE VIEW business.sales_marketing_records AS
    SELECT * FROM business.records WHERE domain = 'SALES_MARKETING';
CREATE VIEW business.property_records AS
    SELECT * FROM business.records WHERE domain = 'PROPERTY';
CREATE VIEW business.hr_records AS
    SELECT * FROM business.records WHERE domain = 'HR';
CREATE VIEW business.legal_records AS
    SELECT * FROM business.records WHERE domain = 'LEGAL';
CREATE VIEW business.it_records AS
    SELECT * FROM business.records WHERE domain = 'IT';


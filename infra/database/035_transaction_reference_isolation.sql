-- Business references belong to an organization. Keeping them globally unique lets one
-- tenant cause collisions in another tenant even though row reads remain isolated.
ALTER TABLE sales.reservations
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

UPDATE sales.reservations AS reservation
SET organization_id = lead.organization_id
FROM sales.leads AS lead
WHERE lead.lead_id = reservation.lead_id
  AND reservation.organization_id IS NULL;

ALTER TABLE sales.reservations
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE sales.reservations
    DROP CONSTRAINT IF EXISTS reservations_reservation_reference_key;

ALTER TABLE sales.reservations
    ADD CONSTRAINT reservations_organization_reference_key
    UNIQUE (organization_id, reservation_reference);

ALTER TABLE finance.payment_records
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

UPDATE finance.payment_records AS payment_record
SET organization_id = payment_request.organization_id
FROM finance.payment_requests AS payment_request
WHERE payment_request.payment_request_id = payment_record.payment_request_id
  AND payment_record.organization_id IS NULL;

ALTER TABLE finance.payment_records
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE finance.payment_records
    DROP CONSTRAINT IF EXISTS payment_records_payment_reference_key;

ALTER TABLE finance.payment_records
    ADD CONSTRAINT payment_records_organization_reference_key
    UNIQUE (organization_id, payment_reference);

ALTER TABLE finance.reconciliations
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations;

UPDATE finance.reconciliations AS reconciliation
SET organization_id = payment_request.organization_id
FROM finance.payment_requests AS payment_request
WHERE payment_request.payment_request_id = reconciliation.payment_request_id
  AND reconciliation.organization_id IS NULL;

ALTER TABLE finance.reconciliations
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE finance.reconciliations
    ADD CONSTRAINT reconciliations_organization_reference_key
    UNIQUE (organization_id, transaction_reference);

UPDATE sales.leads
SET qualification_result = NULL
WHERE qualification_result = 'NOT_QUALIFIED';

ALTER TABLE sales.leads
    DROP CONSTRAINT IF EXISTS leads_qualification_result_check;

ALTER TABLE sales.leads
    ADD CONSTRAINT leads_qualification_result_check CHECK (
        qualification_result IS NULL
        OR qualification_result IN ('HOT', 'WARM', 'COLD')
    );

ALTER TABLE finance.payment_requests
    ALTER COLUMN approval_route SET NOT NULL;

ALTER TABLE finance.payment_requests
    DROP CONSTRAINT IF EXISTS payment_requests_approval_route_check;

ALTER TABLE finance.payment_requests
    ADD CONSTRAINT payment_requests_approval_route_check CHECK (
        approval_route IN ('FINANCE_REVIEWER', 'FINANCE_HEAD', 'DIRECTOR')
    );

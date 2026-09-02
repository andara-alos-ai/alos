-- Stage 0 remediation: correct unsafe legacy backfill assumptions, make the
-- audit ledger append-only, and enforce tenant ownership through composite FKs.

-- Migration 033 could not prove document/evidence checks for legacy payments.
-- Keep the immutable migration history and compensate only rows it generated.
UPDATE finance.payment_checks AS payment_check
SET status = CASE payment_check.check_type
        WHEN 'DOCUMENT' THEN 'NEEDS_REVIEW'
        WHEN 'EVIDENCE' THEN 'NEEDS_REVIEW'
        WHEN 'BUDGET' THEN
            CASE WHEN payment.budget_available THEN 'PASSED' ELSE 'FAILED' END
        WHEN 'APPROVAL_ROUTE' THEN
            CASE
                WHEN payment.approval_route = CASE
                    WHEN payment.amount <= 25000000 THEN 'FINANCE_REVIEWER'
                    WHEN payment.amount <= 250000000 THEN 'FINANCE_HEAD'
                    ELSE 'DIRECTOR'
                END THEN 'PASSED'
                ELSE 'FAILED'
            END
    END,
    details = payment_check.details || jsonb_build_object(
        'integrity_remediation', 'migration-036',
        'legacy_assumption_revoked', payment_check.check_type IN ('DOCUMENT', 'EVIDENCE')
    ),
    checked_at = now()
FROM finance.payment_requests AS payment
WHERE payment.payment_request_id = payment_check.payment_request_id
  AND payment.revision_number = payment_check.revision_number
  AND payment_check.details->>'source' = 'migration-033';

UPDATE finance.payment_requests AS payment
SET evidence_complete = false,
    updated_at = now()
WHERE payment.evidence_complete = true
  AND EXISTS (
      SELECT 1
      FROM finance.payment_checks AS evidence_check
      WHERE evidence_check.payment_request_id = payment.payment_request_id
        AND evidence_check.revision_number = payment.revision_number
        AND evidence_check.check_type = 'EVIDENCE'
        AND evidence_check.details->>'source' = 'migration-033'
        AND evidence_check.status = 'NEEDS_REVIEW'
  );

-- Parent keys used by tenant-consistent composite foreign keys.
ALTER TABLE sales.leads
    ADD CONSTRAINT leads_organization_id_key
    UNIQUE (organization_id, lead_id);

ALTER TABLE finance.payment_requests
    ADD CONSTRAINT payment_requests_organization_id_key
    UNIQUE (organization_id, payment_request_id);

ALTER TABLE finance.payment_records
    ADD CONSTRAINT payment_records_organization_id_key
    UNIQUE (organization_id, payment_record_id);

ALTER TABLE sales.reservations
    DROP CONSTRAINT IF EXISTS reservations_lead_id_fkey;

ALTER TABLE sales.reservations
    ADD CONSTRAINT reservations_organization_lead_fkey
    FOREIGN KEY (organization_id, lead_id)
    REFERENCES sales.leads (organization_id, lead_id);

ALTER TABLE finance.payment_records
    DROP CONSTRAINT IF EXISTS payment_records_payment_request_id_fkey;

ALTER TABLE finance.payment_records
    ADD CONSTRAINT payment_records_organization_request_fkey
    FOREIGN KEY (organization_id, payment_request_id)
    REFERENCES finance.payment_requests (organization_id, payment_request_id);

ALTER TABLE finance.reconciliations
    DROP CONSTRAINT IF EXISTS reconciliations_payment_request_id_fkey;

ALTER TABLE finance.reconciliations
    DROP CONSTRAINT IF EXISTS reconciliations_payment_record_id_fkey;

ALTER TABLE finance.reconciliations
    ADD CONSTRAINT reconciliations_organization_request_fkey
    FOREIGN KEY (organization_id, payment_request_id)
    REFERENCES finance.payment_requests (organization_id, payment_request_id);

ALTER TABLE finance.reconciliations
    ADD CONSTRAINT reconciliations_organization_record_fkey
    FOREIGN KEY (organization_id, payment_record_id)
    REFERENCES finance.payment_records (organization_id, payment_record_id);

-- Audit entries are an append-only ledger. Corrections must be new entries.
UPDATE audit.entries AS entry
SET organization_id = organization.organization_id
FROM (
    SELECT (array_agg(organization_id))[1] AS organization_id
    FROM identity.organizations
    HAVING count(*) = 1
) AS organization
WHERE entry.organization_id IS NULL;

CREATE TABLE IF NOT EXISTS audit.chain_anchors (
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    anchored_hash char(64) NOT NULL,
    reason text NOT NULL,
    anchored_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, anchored_hash)
);

INSERT INTO audit.chain_anchors (organization_id, anchored_hash, reason)
SELECT DISTINCT entry.organization_id, entry.previous_hash,
       'LEGACY_GAP_REGISTERED_DURING_STAGE_ZERO_HARDENING'
FROM audit.entries AS entry
WHERE entry.organization_id IS NOT NULL
  AND entry.previous_hash IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM audit.entries AS predecessor
      WHERE predecessor.organization_id = entry.organization_id
        AND predecessor.entry_hash = entry.previous_hash
  )
ON CONFLICT (organization_id, anchored_hash) DO NOTHING;

CREATE OR REPLACE FUNCTION audit.reject_entry_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit.entries bersifat append-only; tulis entri koreksi baru'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS audit_entries_append_only ON audit.entries;

CREATE TRIGGER audit_entries_append_only
BEFORE UPDATE OR DELETE ON audit.entries
FOR EACH ROW
EXECUTE FUNCTION audit.reject_entry_mutation();

DROP TRIGGER IF EXISTS audit_chain_anchors_append_only ON audit.chain_anchors;

CREATE TRIGGER audit_chain_anchors_append_only
BEFORE UPDATE OR DELETE ON audit.chain_anchors
FOR EACH ROW
EXECUTE FUNCTION audit.reject_entry_mutation();

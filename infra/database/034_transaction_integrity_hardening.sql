ALTER TABLE finance.payment_requests
    DROP CONSTRAINT IF EXISTS payment_requests_category_code_check;

ALTER TABLE finance.payment_requests
    ADD CONSTRAINT payment_requests_category_code_check CHECK (
        category_code IN ('GENERAL', 'MATERIAL', 'OPERATIONS', 'CONTRACTOR', 'TAX')
    );

-- Normalize legacy qualification rows before enforcing the current outcome contract.
UPDATE sales.interactions
SET qualification_result = 'WARM'
WHERE outcome = 'qualified'
  AND (
      qualification_result IS NULL
      OR qualification_result NOT IN ('HOT', 'WARM', 'COLD')
  );

UPDATE sales.interactions
SET qualification_result = NULL
WHERE outcome <> 'qualified'
  AND qualification_result IS NOT NULL;

ALTER TABLE sales.interactions
    DROP CONSTRAINT IF EXISTS interactions_qualification_result_check;

ALTER TABLE sales.interactions
    ADD CONSTRAINT interactions_qualification_result_check CHECK (
        qualification_result IS NULL
        OR qualification_result IN ('HOT', 'WARM', 'COLD')
    );

ALTER TABLE sales.interactions
    DROP CONSTRAINT IF EXISTS interactions_outcome_qualification_check;

ALTER TABLE sales.interactions
    ADD CONSTRAINT interactions_outcome_qualification_check CHECK (
        (outcome = 'qualified' AND qualification_result IS NOT NULL)
        OR (outcome <> 'qualified' AND qualification_result IS NULL)
    );

-- Migration 033 preserved existing Stage 3 checks with ON CONFLICT. Restore the
-- payment aggregate from that authoritative current-revision evidence check.
UPDATE finance.payment_requests AS payment
SET evidence_complete = (evidence_check.status = 'PASSED'),
    updated_at = now()
FROM finance.payment_checks AS evidence_check
WHERE evidence_check.payment_request_id = payment.payment_request_id
  AND evidence_check.revision_number = payment.revision_number
  AND evidence_check.check_type = 'EVIDENCE'
  AND payment.evidence_complete IS DISTINCT FROM (evidence_check.status = 'PASSED');

UPDATE finance.payment_checks AS payment_check
SET status = CASE payment_check.check_type
        WHEN 'DOCUMENT' THEN 'PASSED'
        WHEN 'EVIDENCE' THEN
            CASE WHEN payment.evidence_complete THEN 'PASSED' ELSE 'FAILED' END
        WHEN 'BUDGET' THEN
            CASE WHEN payment.budget_available THEN 'PASSED' ELSE 'FAILED' END
        WHEN 'APPROVAL_ROUTE' THEN
            CASE
                WHEN payment.evidence_complete AND payment.budget_available
                    THEN 'PASSED'
                ELSE 'FAILED'
            END
    END,
    details = payment_check.details || jsonb_build_object(
        'budget_available', payment.budget_available,
        'evidence_complete', payment.evidence_complete,
        'approval_route', payment.approval_route,
        'integrity_hardening', 'migration-034'
    )
FROM finance.payment_requests AS payment
WHERE payment.payment_request_id = payment_check.payment_request_id
  AND payment.revision_number = payment_check.revision_number;

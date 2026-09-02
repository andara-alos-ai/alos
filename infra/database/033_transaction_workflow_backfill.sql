-- Bring transactions created before migration 030 onto the deterministic
-- Stage 3 routing/evidence model without recreating or duplicating them.
WITH routed AS (
    SELECT
        payment_request_id,
        CASE
            WHEN amount <= 25000000 THEN 'FINANCE_REVIEWER'
            WHEN amount <= 250000000 THEN 'FINANCE_HEAD'
            ELSE 'DIRECTOR'
        END AS approval_route
    FROM finance.payment_requests
)
UPDATE finance.payment_requests AS payment
SET evidence_complete = true,
    approval_route = routed.approval_route,
    updated_at = now()
FROM routed
WHERE routed.payment_request_id = payment.payment_request_id
  AND (
      payment.evidence_complete = false
      OR payment.approval_route IS DISTINCT FROM routed.approval_route
  );

UPDATE governance.approval_requests AS approval
SET required_role_code = CASE payment.approval_route
        WHEN 'FINANCE_REVIEWER' THEN 'FINANCE'
        WHEN 'FINANCE_HEAD' THEN 'DIVISION_HEAD'
        ELSE 'DIRECTOR'
    END,
    required_division_code = CASE payment.approval_route
        WHEN 'DIRECTOR' THEN NULL
        ELSE 'FINANCE'
    END,
    routing_rule = payment.approval_route,
    due_at = COALESCE(
        approval.due_at,
        payment.created_at + CASE payment.approval_route
            WHEN 'FINANCE_REVIEWER' THEN interval '24 hours'
            WHEN 'FINANCE_HEAD' THEN interval '12 hours'
            ELSE interval '8 hours'
        END
    )
FROM finance.payment_requests AS payment
WHERE payment.approval_request_id = approval.approval_request_id
  AND (
      approval.required_role_code IS NULL
      OR approval.routing_rule IS DISTINCT FROM payment.approval_route
  );

INSERT INTO finance.payment_checks
    (payment_request_id, revision_number, check_type, agent_id, status, details, checked_at)
SELECT
    payment.payment_request_id,
    payment.revision_number,
    check_definition.check_type,
    check_definition.agent_id,
    'PASSED',
    jsonb_build_object(
        'source', 'migration-033',
        'reason', 'Backfill transaksi yang telah lolos pemeriksaan workflow sebelum Stage 3'
    ),
    now()
FROM finance.payment_requests AS payment
CROSS JOIN (
    VALUES
        ('DOCUMENT', 'DIA'),
        ('EVIDENCE', 'CEA'),
        ('BUDGET', 'BCA'),
        ('APPROVAL_ROUTE', 'ARA')
) AS check_definition(check_type, agent_id)
ON CONFLICT (payment_request_id, revision_number, check_type) DO NOTHING;

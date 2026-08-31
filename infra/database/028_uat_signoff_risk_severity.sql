ALTER TABLE uat.signoffs
    ADD COLUMN IF NOT EXISTS risk_severity text;

ALTER TABLE uat.signoffs
    ADD CONSTRAINT uat_signoffs_risk_severity_check
    CHECK (
        (decision = 'ACCEPTED_WITH_RISK' AND risk_severity IN ('LOW', 'MEDIUM'))
        OR (decision <> 'ACCEPTED_WITH_RISK' AND risk_severity IS NULL)
    );

COMMENT ON COLUMN uat.signoffs.risk_severity IS
    'Only LOW or MEDIUM residual risk may be accepted through controlled-pilot sign-off.';

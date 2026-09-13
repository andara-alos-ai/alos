-- Persistent, distributed Agent Run cancellation state and controls.
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'runtime.agent_runs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%status%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE runtime.agent_runs DROP CONSTRAINT %I', constraint_name);
    END IF;
END
$$;

ALTER TABLE runtime.agent_runs
    ADD COLUMN cancel_requested_at timestamptz,
    ADD COLUMN cancelled_at timestamptz;

ALTER TABLE runtime.agent_runs
    ADD CONSTRAINT agent_runs_status_check CHECK (
        status IN (
            'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED',
            'SUSPENDED', 'KILLED', 'CANCEL_REQUESTED', 'CANCELLED'
        )
    );

CREATE INDEX agent_runs_cancel_requested_idx
    ON runtime.agent_runs (cancel_requested_at)
    WHERE cancel_requested_at IS NOT NULL;

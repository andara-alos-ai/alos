CREATE SCHEMA IF NOT EXISTS integration;
CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE IF NOT EXISTS integration.outbox_events (
    outbox_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    topic text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    destination text NOT NULL CHECK (
        destination IN ('INTERNAL_NOTIFICATION', 'N8N_WEBHOOK')
    ),
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (
        status IN (
            'PENDING', 'PROCESSING', 'RETRY', 'DELIVERED',
            'DEAD_LETTER', 'CANCELLED'
        )
    ),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    locked_by text,
    last_error text,
    response_status integer,
    delivered_at timestamptz,
    correlation_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, destination, idempotency_key),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS outbox_dispatch_idx
    ON integration.outbox_events (status, available_at, created_at)
    WHERE status IN ('PENDING', 'RETRY', 'PROCESSING');

CREATE INDEX IF NOT EXISTS outbox_organization_status_idx
    ON integration.outbox_events (organization_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS observability.worker_runs (
    worker_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name text NOT NULL,
    instance_id text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')
    ),
    organizations_evaluated integer NOT NULL DEFAULT 0 CHECK (
        organizations_evaluated >= 0
    ),
    reminders_enqueued integer NOT NULL DEFAULT 0 CHECK (reminders_enqueued >= 0),
    events_claimed integer NOT NULL DEFAULT 0 CHECK (events_claimed >= 0),
    events_delivered integer NOT NULL DEFAULT 0 CHECK (events_delivered >= 0),
    events_retried integer NOT NULL DEFAULT 0 CHECK (events_retried >= 0),
    events_dead_lettered integer NOT NULL DEFAULT 0 CHECK (
        events_dead_lettered >= 0
    ),
    error_summary text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (
        (status = 'RUNNING' AND completed_at IS NULL)
        OR (status <> 'RUNNING' AND completed_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS worker_runs_latest_idx
    ON observability.worker_runs (worker_name, started_at DESC);

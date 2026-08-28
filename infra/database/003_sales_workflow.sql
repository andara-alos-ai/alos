CREATE TABLE IF NOT EXISTS workflow.transition_events (
    transition_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id uuid NOT NULL REFERENCES workflow.workflow_runs,
    from_step text NOT NULL,
    outcome text NOT NULL,
    to_step text NOT NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('HUMAN', 'AGENT', 'SYSTEM')),
    actor_id text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS transition_events_run_idx
    ON workflow.transition_events (workflow_run_id, occurred_at);

CREATE TABLE IF NOT EXISTS sales.follow_up_tasks (
    follow_up_task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES sales.leads,
    workflow_run_id uuid NOT NULL REFERENCES workflow.workflow_runs,
    assigned_user_id uuid NOT NULL REFERENCES identity.users,
    due_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('OPEN', 'COMPLETED', 'CANCELLED')),
    sequence_number integer NOT NULL CHECK (sequence_number > 0),
    created_by_agent_run_id uuid REFERENCES agents.agent_runs,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (workflow_run_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS follow_up_tasks_queue_idx
    ON sales.follow_up_tasks (assigned_user_id, status, due_at);

CREATE TABLE IF NOT EXISTS sales.interactions (
    interaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES sales.leads,
    workflow_run_id uuid NOT NULL REFERENCES workflow.workflow_runs,
    actor_user_id uuid NOT NULL REFERENCES identity.users,
    channel text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('qualified', 'reserved', 'follow_up', 'exception')),
    notes text NOT NULL,
    evidence_reference text,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS interactions_lead_idx
    ON sales.interactions (lead_id, occurred_at);

CREATE TABLE IF NOT EXISTS sales.reservations (
    reservation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL UNIQUE REFERENCES sales.leads,
    workflow_run_id uuid NOT NULL UNIQUE REFERENCES workflow.workflow_runs,
    reservation_reference text NOT NULL UNIQUE,
    recorded_by_user_id uuid NOT NULL REFERENCES identity.users,
    status text NOT NULL CHECK (status IN ('RECORDED', 'CANCELLED')),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

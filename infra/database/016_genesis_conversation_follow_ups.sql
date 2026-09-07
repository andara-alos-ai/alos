-- Idempotent, source-bound model runs for two-way Genesis conversations.
-- Follow-up runs are accounting records only: they never advance document_workflows.
CREATE TABLE genesis.follow_up_runs (
    follow_up_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    workflow_id uuid NOT NULL REFERENCES genesis.document_workflows,
    conversation_id uuid NOT NULL REFERENCES genesis.conversations,
    source_document_id uuid NOT NULL REFERENCES documents.records,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    correlation_id uuid NOT NULL,
    source_version_number integer NOT NULL CHECK (source_version_number > 0),
    source_content_sha256 char(64) NOT NULL,
    prompt_sha256 char(64) NOT NULL,
    data_classification text NOT NULL CHECK (data_classification = 'INTERNAL'),
    status text NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'BLOCKED', 'FAILED')),
    requested_output_tokens integer NOT NULL CHECK (requested_output_tokens > 0),
    reserved_cost_usd numeric(18, 6) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    provider text,
    model text,
    input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
    latency_milliseconds integer CHECK (
        latency_milliseconds IS NULL OR latency_milliseconds >= 0
    ),
    estimated_cost_usd numeric(18, 6) CHECK (
        estimated_cost_usd IS NULL OR estimated_cost_usd >= 0
    ),
    estimated_context_tokens integer NOT NULL CHECK (estimated_context_tokens >= 0),
    history_turns_included integer NOT NULL DEFAULT 0 CHECK (history_turns_included >= 0),
    human_message_id uuid UNIQUE REFERENCES genesis.messages,
    genesis_message_id uuid UNIQUE REFERENCES genesis.messages,
    failure_code text,
    failure_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (organization_id, correlation_id),
    CHECK (status <> 'SUCCEEDED' OR (
        human_message_id IS NOT NULL AND genesis_message_id IS NOT NULL
    )),
    CHECK (genesis_message_id IS NULL OR status = 'SUCCEEDED')
);

CREATE INDEX genesis_follow_up_runs_budget_idx
    ON genesis.follow_up_runs (organization_id, workspace_id, status, created_at);
CREATE INDEX genesis_follow_up_runs_conversation_idx
    ON genesis.follow_up_runs (conversation_id, created_at DESC);

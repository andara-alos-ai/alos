-- General GENESIS conversations and document-to-agent governance linkage.

ALTER TABLE genesis.messages
    ADD COLUMN correlation_id uuid,
    ADD COLUMN status text NOT NULL DEFAULT 'COMPLETED'
        CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    ADD COLUMN structured_content jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(structured_content) = 'object'),
    ADD COLUMN citations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(citations) = 'array'),
    ADD COLUMN tool_activity jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(tool_activity) = 'array');

CREATE INDEX genesis_conversations_actor_updated_idx
    ON genesis.conversations (organization_id, created_by_user_id, updated_at DESC);
CREATE INDEX genesis_messages_conversation_created_idx
    ON genesis.messages (conversation_id, created_at, message_id);

CREATE TABLE observability.model_calls (
    model_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    conversation_id uuid REFERENCES genesis.conversations ON DELETE SET NULL,
    correlation_id uuid NOT NULL,
    purpose text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    latency_ms integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    estimated_cost_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX observability_model_calls_scope_idx
    ON observability.model_calls (organization_id, workspace_id, created_at DESC);

ALTER TABLE integrations.external_research_runs
    DROP CONSTRAINT IF EXISTS external_research_runs_status_check;
ALTER TABLE integrations.external_research_runs
    ADD CONSTRAINT external_research_runs_status_check CHECK (status IN (
        'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'UNAVAILABLE',
        'EXTERNAL_RESEARCH_NOT_CONFIGURED'
    ));

ALTER TABLE genesis.document_workflows
    ADD COLUMN agent_contract_id uuid REFERENCES agents.contracts,
    ADD COLUMN release_change_request_id uuid REFERENCES genesis.change_requests,
    ADD COLUMN governance_handoff_artifact_id uuid REFERENCES genesis.artifacts;

UPDATE genesis.document_workflows
SET status = 'AGENT_PROPOSAL_DRAFT'
WHERE status = 'READY_FOR_H4';

ALTER TABLE genesis.document_workflows
    DROP CONSTRAINT IF EXISTS document_workflows_status_check;
ALTER TABLE genesis.document_workflows
    ADD CONSTRAINT document_workflows_status_check CHECK (status IN (
        'ANALYSIS_DRAFT', 'RND_DRAFT', 'CHECKLIST_DRAFT', 'COMPLETION_DRAFT',
        'AGENT_PROPOSAL_DRAFT', 'READY_FOR_GOVERNANCE'
    ));

CREATE UNIQUE INDEX genesis_document_workflow_agent_contract_idx
    ON genesis.document_workflows (agent_contract_id)
    WHERE agent_contract_id IS NOT NULL;

CREATE TABLE jobs.service_heartbeats (
    service_name text PRIMARY KEY CHECK (service_name IN ('WORKER', 'SCHEDULER')),
    instance_id text NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

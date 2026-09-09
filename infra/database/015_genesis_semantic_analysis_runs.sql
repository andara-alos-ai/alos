-- Governed accounting for the one-document Genesis semantic analysis boundary.
-- This is intentionally separate from runtime.agent_runs: Genesis must not
-- create or activate an Agent Contract simply to answer a document question.

CREATE TABLE genesis.semantic_analysis_runs (
    semantic_analysis_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    source_document_id uuid NOT NULL REFERENCES documents.records,
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    correlation_id uuid NOT NULL,
    source_version_number integer NOT NULL CHECK (source_version_number > 0),
    source_content_sha256 text NOT NULL,
    prompt_sha256 text NOT NULL,
    data_classification text NOT NULL CHECK (data_classification = 'INTERNAL'),
    status text NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'BLOCKED', 'FAILED')),
    requested_output_tokens integer NOT NULL CHECK (requested_output_tokens > 0),
    reserved_cost_usd numeric(18, 6) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    provider text,
    model text,
    input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
    estimated_cost_usd numeric(18, 6) CHECK (
        estimated_cost_usd IS NULL OR estimated_cost_usd >= 0
    ),
    analysis_artifact_id uuid REFERENCES genesis.artifacts,
    failure_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE UNIQUE INDEX genesis_semantic_analysis_runs_correlation_idx
    ON genesis.semantic_analysis_runs (organization_id, correlation_id);

CREATE INDEX genesis_semantic_analysis_runs_budget_idx
    ON genesis.semantic_analysis_runs (organization_id, workspace_id, status, created_at);

-- Actual Pydantic Evals execution evidence, bound to runtime and governance lineage.
CREATE TABLE governance.agent_eval_evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    test_run_id uuid NOT NULL UNIQUE REFERENCES governance.test_runs ON DELETE RESTRICT,
    test_case_id uuid NOT NULL REFERENCES governance.test_cases ON DELETE RESTRICT,
    factory_test_id uuid REFERENCES genesis.factory_generated_tests ON DELETE RESTRICT,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    tenant_id uuid,
    agent_version_id uuid NOT NULL REFERENCES agents.versions ON DELETE RESTRICT,
    agent_run_id uuid REFERENCES runtime.agent_runs ON DELETE RESTRICT,
    category text NOT NULL CHECK (category IN (
        'POSITIVE', 'NEGATIVE', 'REGRESSION', 'SECURITY', 'RECOVERY',
        'PERMISSION', 'TENANT_ISOLATION', 'TOOL_DENIAL', 'BUDGET',
        'SOURCE_VALIDATION', 'EVIDENCE'
    )),
    input_reference jsonb NOT NULL CHECK (jsonb_typeof(input_reference) = 'object'),
    expected jsonb NOT NULL CHECK (jsonb_typeof(expected) = 'object'),
    actual jsonb NOT NULL CHECK (jsonb_typeof(actual) = 'object'),
    status text NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'BLOCKED', 'ERROR')),
    evaluator text NOT NULL,
    score numeric(7, 6) CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    error_code text,
    block_reason text,
    evidence_digest char(64) NOT NULL UNIQUE,
    correlation_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (completed_at >= started_at)
);

CREATE INDEX governance_agent_eval_scope_idx
    ON governance.agent_eval_evidence (
        organization_id, workspace_id, tenant_id, agent_version_id, created_at DESC
    );
CREATE INDEX governance_agent_eval_factory_idx
    ON governance.agent_eval_evidence (factory_test_id, created_at DESC)
    WHERE factory_test_id IS NOT NULL;

CREATE TRIGGER governance_test_runs_no_update
BEFORE UPDATE ON governance.test_runs
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER governance_test_runs_no_delete
BEFORE DELETE ON governance.test_runs
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER governance_agent_eval_evidence_no_update
BEFORE UPDATE ON governance.agent_eval_evidence
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER governance_agent_eval_evidence_no_delete
BEFORE DELETE ON governance.agent_eval_evidence
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

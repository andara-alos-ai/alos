-- Domain-neutral R&D lifecycle, immutable artifacts, and human decision evidence.
ALTER TABLE research.projects
    ADD COLUMN requested_by_user_id uuid REFERENCES identity.users,
    ADD COLUMN idempotency_key text,
    ADD COLUMN correlation_id uuid,
    ADD COLUMN completed_at timestamptz,
    ADD CONSTRAINT research_projects_status_check CHECK (status IN (
        'REQUEST', 'SCOPING', 'RESEARCH', 'EVIDENCE_COLLECTION', 'ANALYSIS',
        'FINDINGS', 'RECOMMENDATION', 'EXPERIMENT', 'EVALUATION', 'REVIEW',
        'DECISION', 'CLOSED'
    ));

CREATE UNIQUE INDEX research_projects_idempotency_idx
    ON research.projects (organization_id, requested_by_user_id, idempotency_key)
    WHERE requested_by_user_id IS NOT NULL AND idempotency_key IS NOT NULL;

CREATE TABLE research.artifacts (
    research_artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id uuid NOT NULL REFERENCES research.projects ON DELETE RESTRICT,
    artifact_type text NOT NULL CHECK (artifact_type IN (
        'QUESTION', 'METHOD', 'SOURCE', 'EVIDENCE', 'FINDING', 'ASSUMPTION',
        'LIMITATION', 'ALTERNATIVE', 'RISK', 'IMPACT', 'COST', 'RECOMMENDATION',
        'EXPERIMENT_PLAN', 'EVALUATION_PLAN'
    )),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    source_reference text,
    confidence numeric(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE research.decisions (
    decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id uuid NOT NULL UNIQUE REFERENCES research.projects ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('APPROVE_HANDOFF', 'CONTINUE', 'REJECT')),
    rationale text NOT NULL CHECK (char_length(btrim(rationale)) BETWEEN 3 AND 10000),
    decided_by_user_id uuid NOT NULL REFERENCES identity.users,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX research_artifacts_project_type_idx
    ON research.artifacts (research_id, artifact_type, created_at);

CREATE TRIGGER research_artifacts_no_update
BEFORE UPDATE ON research.artifacts
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER research_artifacts_no_delete
BEFORE DELETE ON research.artifacts
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER research_decisions_no_update
BEFORE UPDATE ON research.decisions
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

CREATE TRIGGER research_decisions_no_delete
BEFORE DELETE ON research.decisions
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

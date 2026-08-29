ALTER TABLE agents.agent_runs
    ADD COLUMN IF NOT EXISTS capability text,
    ADD COLUMN IF NOT EXISTS execution_mode text,
    ADD COLUMN IF NOT EXISTS approved_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS workflow_step_id text,
    ADD COLUMN IF NOT EXISTS contract_digest char(64);

ALTER TABLE agents.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_execution_mode_check;

ALTER TABLE agents.agent_runs
    ADD CONSTRAINT agent_runs_execution_mode_check
    CHECK (execution_mode IS NULL OR execution_mode IN ('DETERMINISTIC', 'AI_ASSISTED'));

CREATE OR REPLACE FUNCTION workflow.prevent_workflow_release_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.workflow_id IS DISTINCT FROM OLD.workflow_id
       OR NEW.version IS DISTINCT FROM OLD.version THEN
        RAISE EXCEPTION 'workflow release identity is immutable';
    END IF;

    IF OLD.definition ? 'definition_digest'
       AND NEW.definition IS DISTINCT FROM OLD.definition THEN
        RAISE EXCEPTION 'workflow release definition is immutable';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workflow_release_immutable_trigger
    ON workflow.workflow_releases;

CREATE TRIGGER workflow_release_immutable_trigger
BEFORE UPDATE ON workflow.workflow_releases
FOR EACH ROW
EXECUTE FUNCTION workflow.prevent_workflow_release_mutation();

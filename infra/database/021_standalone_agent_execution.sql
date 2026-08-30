ALTER TABLE agents.agent_runs
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES identity.organizations,
    ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES platform.projects;

UPDATE agents.agent_runs ar
SET organization_id = wi.organization_id,
    project_id = wi.project_id
FROM workflow.workflow_runs wr
LEFT JOIN platform.work_items wi ON wi.work_item_id = wr.work_item_id
WHERE ar.workflow_run_id = wr.workflow_run_id
  AND ar.organization_id IS NULL;

CREATE INDEX IF NOT EXISTS agent_runs_organization_idx
    ON agents.agent_runs (organization_id, started_at DESC);

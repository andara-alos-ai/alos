CREATE UNIQUE INDEX IF NOT EXISTS uq_uat_open_run_per_project
    ON uat.runs (project_id)
    WHERE status IN ('DRAFT', 'IN_PROGRESS', 'READY_FOR_SIGNOFF');

COMMENT ON INDEX uat.uq_uat_open_run_per_project IS
    'Prevents parallel open UAT cycles from producing conflicting acceptance records.';

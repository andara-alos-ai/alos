#!/usr/bin/env bash
# Reset Governance and Agent Control data for one staging organization.
# Identity, credentials, roles, memberships, business data, capability catalog,
# GENESIS conversations, and the immutable audit trail are preserved.

set -euo pipefail

readonly CONFIRMATION="${1:-}"
readonly ENV_FILE="${2:-/etc/alos/alos.staging.env}"
readonly COMPOSE_FILE="${3:-infra/compose/compose.staging.yaml}"
readonly ORGANIZATION_CODE="${4:-ALOS}"
readonly BACKUP_DIR="${ALOS_RESET_BACKUP_DIR:-/opt/alos/backups}"

if [[ "${CONFIRMATION}" != "--confirm-reset-governance-agent-control" ]]; then
  echo "Refusing destructive reset."
  echo "Usage: sudo bash scripts/database/reset-governance-agent-control.sh --confirm-reset-governance-agent-control [env-file] [compose-file] [organization-code]"
  exit 64
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script through sudo so Docker and ${BACKUP_DIR} are controlled."
  exit 77
fi

if [[ ! "${ORGANIZATION_CODE}" =~ ^[A-Z][A-Z0-9_]{1,39}$ ]]; then
  echo "Invalid organization code. Reset cancelled."
  exit 65
fi

if [[ ! -r "${ENV_FILE}" || ! -r "${COMPOSE_FILE}" ]]; then
  echo "Environment file or Compose file cannot be read. Reset cancelled."
  exit 66
fi

compose=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="alos-before-governance-reset-${timestamp}.dump"
backup_path="${BACKUP_DIR}/${backup_name}"
container_backup="/tmp/${backup_name}"

mkdir -p "${BACKUP_DIR}"

restart_writers() {
  "${compose[@]}" up --detach platform worker scheduler >/dev/null || true
}
trap restart_writers EXIT

echo "Stopping API, worker, and scheduler to prevent concurrent governance writes…"
"${compose[@]}" stop platform worker scheduler >/dev/null

echo "Creating recoverable PostgreSQL backup: ${backup_path}"
"${compose[@]}" exec -T postgres pg_dump -U alos -d alos \
  --format=custom --no-owner --no-privileges --file="${container_backup}"
"${compose[@]}" cp "postgres:${container_backup}" "${backup_path}"
"${compose[@]}" exec -T postgres rm -f "${container_backup}"
sha256sum "${backup_path}" > "${backup_path}.sha256"

echo "Protected identity records before reset:"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 -c "
    SELECT organization.code,
           count(DISTINCT users.user_id) AS users,
           count(DISTINCT credentials.user_id) AS credentials
    FROM identity.organizations AS organization
    LEFT JOIN identity.users AS users USING (organization_id)
    LEFT JOIN identity.user_credentials AS credentials USING (user_id)
    WHERE organization.code = '${ORGANIZATION_CODE}'
    GROUP BY organization.code;
  "

echo "Deleting Governance and Agent Control records for ${ORGANIZATION_CODE}…"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 <<SQL
BEGIN;

CREATE TEMP TABLE reset_organizations ON COMMIT DROP AS
SELECT organization_id
FROM identity.organizations
WHERE code = '${ORGANIZATION_CODE}';

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM reset_organizations) THEN
    RAISE EXCEPTION 'organization was not found';
  END IF;
END \$\$;

CREATE TEMP TABLE reset_agent_contracts ON COMMIT DROP AS
SELECT contract.agent_contract_id
FROM agents.contracts AS contract
JOIN reset_organizations AS organization USING (organization_id);

CREATE TEMP TABLE reset_agent_versions ON COMMIT DROP AS
SELECT version.agent_version_id
FROM agents.versions AS version
JOIN reset_agent_contracts AS contract USING (agent_contract_id);

CREATE TEMP TABLE reset_change_requests ON COMMIT DROP AS
SELECT request.change_request_id
FROM governance.agent_change_requests AS request
JOIN reset_agent_contracts AS contract USING (agent_contract_id);

CREATE TEMP TABLE reset_agent_runs ON COMMIT DROP AS
SELECT run.agent_run_id
FROM runtime.agent_runs AS run
JOIN reset_agent_versions AS version USING (agent_version_id);

CREATE TEMP TABLE reset_agent_tasks ON COMMIT DROP AS
SELECT task.task_id
FROM operational.tasks AS task
JOIN reset_agent_versions AS version
  ON version.agent_version_id = task.created_by_agent_version_id;

CREATE TEMP TABLE reset_agent_evidence ON COMMIT DROP AS
SELECT evidence.evidence_id
FROM operational.evidence AS evidence
JOIN reset_agent_tasks AS task USING (task_id);

CREATE TEMP TABLE reset_agent_findings ON COMMIT DROP AS
SELECT finding.finding_id
FROM operational.findings AS finding
WHERE finding.generated_by_agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions)
   OR finding.source_kind = 'AGENT'
   OR finding.source_id IN (SELECT task_id FROM reset_agent_tasks)
   OR finding.source_id IN (SELECT evidence_id FROM reset_agent_evidence);

CREATE TEMP TABLE reset_agent_actions ON COMMIT DROP AS
SELECT action.proposed_action_id
FROM operational.proposed_actions AS action
WHERE action.requested_by_agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);

DELETE FROM jobs.queue
WHERE organization_id IN (SELECT organization_id FROM reset_organizations)
  AND job_type = 'AGENT_RUN';

DELETE FROM operational.approval_requests
WHERE organization_id IN (SELECT organization_id FROM reset_organizations)
  AND (
    approval_kind = 'AGENT'
    OR requested_by_agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions)
    OR subject_id IN (SELECT task_id FROM reset_agent_tasks)
    OR subject_id IN (SELECT evidence_id FROM reset_agent_evidence)
    OR subject_id IN (SELECT finding_id FROM reset_agent_findings)
    OR subject_id IN (SELECT proposed_action_id FROM reset_agent_actions)
  );
DELETE FROM operational.findings
WHERE finding_id IN (SELECT finding_id FROM reset_agent_findings);
DELETE FROM operational.evidence
WHERE evidence_id IN (SELECT evidence_id FROM reset_agent_evidence);
DELETE FROM operational.tasks
WHERE task_id IN (SELECT task_id FROM reset_agent_tasks);
DELETE FROM operational.proposed_actions
WHERE proposed_action_id IN (SELECT proposed_action_id FROM reset_agent_actions);

UPDATE genesis.document_workflows
SET agent_contract_id = NULL,
    release_change_request_id = NULL,
    governance_handoff_artifact_id = NULL,
    status = CASE
      WHEN status IN ('AGENT_PROPOSAL_DRAFT', 'READY_FOR_GOVERNANCE') THEN 'ANALYSIS_DRAFT'
      ELSE status
    END,
    updated_at = now()
WHERE agent_contract_id IN (SELECT agent_contract_id FROM reset_agent_contracts)
   OR release_change_request_id IN (SELECT change_request_id FROM reset_change_requests);

DELETE FROM runtime.citations
WHERE agent_run_id IN (SELECT agent_run_id FROM reset_agent_runs);
DELETE FROM runtime.run_steps
WHERE agent_run_id IN (SELECT agent_run_id FROM reset_agent_runs);
DELETE FROM runtime.tool_calls
WHERE agent_run_id IN (SELECT agent_run_id FROM reset_agent_runs);
DELETE FROM runtime.budget_reservations
WHERE agent_run_id IN (SELECT agent_run_id FROM reset_agent_runs);
DELETE FROM runtime.agent_runs
WHERE agent_run_id IN (SELECT agent_run_id FROM reset_agent_runs);

DELETE FROM governance.agent_lifecycle_events
WHERE change_request_id IN (SELECT change_request_id FROM reset_change_requests);
DELETE FROM governance.reviews
WHERE change_request_id IN (SELECT change_request_id FROM reset_change_requests);
DELETE FROM governance.release_proposals
WHERE change_request_id IN (SELECT change_request_id FROM reset_change_requests)
   OR agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);
DELETE FROM governance.rollback_records
WHERE agent_contract_id IN (SELECT agent_contract_id FROM reset_agent_contracts);
DELETE FROM governance.kill_switches
WHERE organization_id IN (SELECT organization_id FROM reset_organizations);
DELETE FROM governance.test_runs
WHERE agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);
DELETE FROM governance.test_cases
WHERE agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);
DELETE FROM governance.permission_policies
WHERE agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);
DELETE FROM governance.agent_change_requests
WHERE change_request_id IN (SELECT change_request_id FROM reset_change_requests);
DELETE FROM governance.cost_limits
WHERE organization_id IN (SELECT organization_id FROM reset_organizations);

DELETE FROM agents.registry
WHERE agent_contract_id IN (SELECT agent_contract_id FROM reset_agent_contracts);
DELETE FROM agents.versions
WHERE agent_version_id IN (SELECT agent_version_id FROM reset_agent_versions);
DELETE FROM agents.contracts
WHERE agent_contract_id IN (SELECT agent_contract_id FROM reset_agent_contracts);
DELETE FROM agents.tool_definitions
WHERE organization_id IN (SELECT organization_id FROM reset_organizations);
DELETE FROM genesis.change_requests
WHERE change_request_id IN (SELECT change_request_id FROM reset_change_requests);

COMMIT;
SQL

echo "Verifying Governance/Agent Control is empty and accounts are intact…"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 -c "
    SELECT
      (SELECT count(*) FROM identity.users AS users
       JOIN identity.organizations AS organization USING (organization_id)
       WHERE organization.code = '${ORGANIZATION_CODE}') AS users_retained,
      (SELECT count(*) FROM agents.contracts AS contract
       JOIN identity.organizations AS organization USING (organization_id)
       WHERE organization.code = '${ORGANIZATION_CODE}') AS agents_remaining,
      (SELECT count(*) FROM governance.cost_limits AS limits
       JOIN identity.organizations AS organization USING (organization_id)
       WHERE organization.code = '${ORGANIZATION_CODE}') AS cost_limits_remaining,
      (SELECT count(*) FROM governance.kill_switches AS switches
       JOIN identity.organizations AS organization USING (organization_id)
       WHERE organization.code = '${ORGANIZATION_CODE}') AS kill_switches_remaining;
  "

echo "Governance/Agent Control reset complete."
echo "Immutable audit history was preserved."
echo "Backup: ${backup_path}"
echo "Checksum: ${backup_path}.sha256"

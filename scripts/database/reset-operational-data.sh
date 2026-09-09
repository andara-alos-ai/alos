#!/usr/bin/env bash
# Reset ALOS staging/pilot business data while preserving the account boundary.
#
# Preserved: organization, divisions, users, credentials, roles, duties,
# workspaces, memberships, schema migrations, and capability catalog.
# Removed: documents/uploads, GENESIS history, agents/governance state,
# operational/portfolio/reporting records, audit/usage history, and jobs.

set -euo pipefail

readonly CONFIRMATION="${1:-}"
readonly ENV_FILE="${2:-/etc/alos/alos.staging.env}"
readonly COMPOSE_FILE="${3:-infra/compose/compose.staging.yaml}"
readonly BACKUP_DIR="${ALOS_RESET_BACKUP_DIR:-/opt/alos/backups}"

if [[ "${CONFIRMATION}" != "--confirm-reset-operational-data" ]]; then
  echo "Refusing destructive reset."
  echo "Usage: sudo bash scripts/database/reset-operational-data.sh --confirm-reset-operational-data [env-file] [compose-file]"
  exit 64
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script through sudo so Docker and ${BACKUP_DIR} are controlled."
  exit 77
fi

if [[ ! -r "${ENV_FILE}" || ! -r "${COMPOSE_FILE}" ]]; then
  echo "Environment file or Compose file cannot be read. Reset cancelled."
  exit 66
fi

storage_provider="$({ grep -E '^ALOS_OBJECT_STORAGE_PROVIDER=' "${ENV_FILE}" || true; } | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
if [[ "${storage_provider}" != "filesystem" ]]; then
  echo "Reset cancelled: object storage provider must be filesystem so uploaded objects can be removed safely."
  echo "Configured provider: ${storage_provider:-unset}"
  exit 65
fi

compose=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="alos-before-reset-${timestamp}.dump"
backup_path="${BACKUP_DIR}/${backup_name}"
container_backup="/tmp/${backup_name}"

mkdir -p "${BACKUP_DIR}"

restart_writers() {
  "${compose[@]}" up --detach platform worker scheduler >/dev/null || true
}
trap restart_writers EXIT

echo "Stopping API worker and scheduler to prevent writes during reset…"
"${compose[@]}" stop platform worker scheduler >/dev/null

echo "Creating PostgreSQL backup: ${backup_path}"
"${compose[@]}" exec -T postgres pg_dump -U alos -d alos --format=custom --no-owner --no-privileges --file="${container_backup}"
"${compose[@]}" cp "postgres:${container_backup}" "${backup_path}"
"${compose[@]}" exec -T postgres rm -f "${container_backup}"
sha256sum "${backup_path}" > "${backup_path}.sha256"

echo "Account records that will be retained:"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 -c "
  SELECT
    (SELECT count(*) FROM identity.users) AS users,
    (SELECT count(*) FROM identity.user_credentials) AS credentials,
    (SELECT count(*) FROM identity.role_assignments) AS role_assignments,
    (SELECT count(*) FROM workspace.workspaces) AS workspaces,
    (SELECT count(*) FROM workspace.memberships) AS memberships;
"

echo "Deleting operational, GENESIS, agent, governance, audit, and demo records…"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 -c "
  TRUNCATE TABLE
    audit.events,
    observability.model_calls,
    observability.usage_ledger,
    runtime.citations,
    runtime.run_steps,
    runtime.tool_calls,
    runtime.budget_reservations,
    runtime.agent_runs,
    governance.rollback_records,
    governance.kill_switches,
    governance.release_proposals,
    governance.reviews,
    governance.agent_lifecycle_events,
    governance.agent_change_requests,
    governance.test_runs,
    governance.test_cases,
    governance.permission_policies,
    governance.cost_limits,
    agents.registry,
    agents.versions,
    agents.contracts,
    agents.tool_definitions,
    genesis.follow_up_runs,
    genesis.semantic_analysis_runs,
    genesis.document_workflows,
    genesis.document_uploads,
    genesis.conversation_context,
    genesis.artifacts,
    genesis.messages,
    genesis.change_requests,
    genesis.conversations,
    sources.content_chunks,
    sources.versions,
    sources.vault_policies,
    sources.sources,
    documents.comparisons,
    documents.review_requests,
    documents.checklist_items,
    documents.versions,
    documents.records,
    business.records,
    operational.approval_requests,
    operational.proposed_actions,
    operational.evidence,
    operational.findings,
    operational.tasks,
    reporting.reports,
    reporting.schedules,
    reporting.definitions,
    jobs.queue,
    jobs.service_heartbeats,
    notifications.inbox,
    kpi.definitions,
    portfolio.project_progress_history,
    portfolio.project_milestones,
    portfolio.division_issues,
    portfolio.projects,
    integrations.external_research_runs,
    integrations.configurations,
    software_factory.change_requests,
    compliance.release_decisions
  RESTART IDENTITY CASCADE;
"

echo "Deleting filesystem objects stored by uploads/evidence…"
# `platform` is intentionally stopped while the database is reset. Start one
# dependency-free, short-lived container with the same object volume instead
# of bringing the API back up before its metadata and files agree.
"${compose[@]}" run --rm --no-deps --entrypoint sh platform -c 'find /var/lib/alos-objects -xdev -mindepth 1 -delete'

echo "Verifying protected account records and empty operational tables…"
"${compose[@]}" exec -T postgres psql -U alos -d alos -v ON_ERROR_STOP=1 -c "
  SELECT
    (SELECT count(*) FROM identity.users) AS users_retained,
    (SELECT count(*) FROM workspace.memberships) AS memberships_retained,
    (SELECT count(*) FROM operational.tasks) AS tasks_remaining,
    (SELECT count(*) FROM documents.records) AS documents_remaining,
    (SELECT count(*) FROM genesis.conversations) AS conversations_remaining,
    (SELECT count(*) FROM agents.contracts) AS agents_remaining,
    (SELECT count(*) FROM audit.events) AS audit_events_remaining;
"

echo "Reset complete. Backup: ${backup_path}"
echo "Checksum: ${backup_path}.sha256"

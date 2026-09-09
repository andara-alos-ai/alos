"""Transactional PostgreSQL job queue with retries and idempotency."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.authorization import can_govern_agents, require_tenant, require_workspace
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext

JobType = Literal[
    "DOCUMENT_EXTRACTION",
    "DOCUMENT_INDEXING",
    "EXTERNAL_RESEARCH",
    "AGENT_RUN",
    "SCHEDULED_REPORT",
    "RECURRING_MONITOR",
    "NOTIFICATION",
    "CONNECTOR_SYNC",
]
JobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]


class JobQueueError(RuntimeError):
    pass


class JobEnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    workspace_id: UUID | None = None
    job_type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID
    owner_user_id: UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=300)
    max_attempts: int = Field(default=3, ge=1, le=20)
    next_retry_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobRecord(BaseModel):
    job_id: UUID
    organization_id: UUID
    workspace_id: UUID | None
    job_type: JobType
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    next_retry_at: datetime
    correlation_id: UUID
    owner_user_id: UUID | None
    idempotency_key: str
    locked_by: str | None
    locked_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    safe_error_code: str | None
    created_at: datetime


class AgentScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    division_id: UUID | None = None
    project_id: UUID | None = None
    tenant_id: UUID | None = None
    schedule_expression: str = Field(min_length=3, max_length=120)
    timezone: str = Field(min_length=1, max_length=100)
    input: dict[str, Any] = Field(default_factory=dict)
    requested_tool_keys: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = True


class AgentScheduleRecord(BaseModel):
    agent_schedule_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    project_id: UUID | None
    tenant_id: UUID | None
    agent_contract_id: UUID
    agent_key: str
    owner_user_id: UUID
    schedule_expression: str
    timezone: str
    input: dict[str, Any]
    requested_tool_keys: list[str]
    enabled: bool
    confirmed_by_user_id: UUID | None
    next_run_at: datetime
    last_run_at: datetime | None
    correlation_id: UUID


class AgentJobContext(BaseModel):
    agent_schedule_id: UUID
    agent_key: str
    agent_version_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    project_id: UUID | None
    tenant_id: UUID | None
    owner_user_id: UUID
    input: dict[str, Any]
    requested_tool_keys: list[str]


class JobQueueRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def enqueue(self, request: JobEnqueueRequest) -> JobRecord:
        with self._transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO jobs.queue (
                    organization_id, workspace_id, job_type, payload, correlation_id,
                    owner_user_id, idempotency_key, max_attempts, next_retry_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (organization_id, job_type, idempotency_key)
                DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING *
                """,
                (
                    request.organization_id,
                    request.workspace_id,
                    request.job_type,
                    Jsonb(request.payload),
                    request.correlation_id,
                    request.owner_user_id,
                    request.idempotency_key,
                    request.max_attempts,
                    request.next_retry_at,
                ),
            ).fetchone()
            if row is None:
                raise JobQueueError("job could not be enqueued")
            self._audit(
                connection,
                request.organization_id,
                "JOB_ENQUEUED",
                row["job_id"],
                request.correlation_id,
                {"job_type": request.job_type},
            )
            return JobRecord(**row)

    def configure_agent_schedule(
        self,
        request: AgentScheduleRequest,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> AgentScheduleRecord:
        """Configure a human-confirmed schedule for the currently active Agent contract."""
        require_workspace(actor, request.workspace_id)
        require_tenant(actor, request.tenant_id)
        if not can_govern_agents(actor):
            raise JobQueueError("Agent schedule governance permission is required")
        next_run_at = next_schedule_at(
            request.schedule_expression,
            datetime.now(UTC),
            request.timezone,
        )
        with self._transaction() as connection:
            workspace = connection.execute(
                """
                SELECT 1 FROM workspace.workspaces
                WHERE workspace_id = %s AND organization_id = %s AND status = 'ACTIVE'
                """,
                (request.workspace_id, actor.organization_id),
            ).fetchone()
            if workspace is None:
                raise JobQueueError("active workspace is outside the organization scope")
            agent = connection.execute(
                """
                SELECT contract.agent_contract_id, registry.active_version_id,
                       version.contract_snapshot
                FROM agents.contracts AS contract
                JOIN agents.registry AS registry
                  ON registry.agent_contract_id = contract.agent_contract_id
                JOIN agents.versions AS version
                  ON version.agent_version_id = registry.active_version_id
                WHERE contract.organization_id = %s AND contract.workspace_id = %s
                  AND contract.agent_key = %s AND version.lifecycle_status = 'ACTIVE'
                  AND EXISTS (
                      SELECT 1 FROM governance.agent_change_requests AS change
                      WHERE change.agent_version_id = version.agent_version_id
                        AND change.state = 'ACTIVE'
                  )
                """,
                (actor.organization_id, request.workspace_id, request.agent_key),
            ).fetchone()
            if agent is None:
                raise JobQueueError("only a governed ACTIVE Agent can be scheduled")
            if agent["contract_snapshot"].get("schedule_policy", {}).get("enabled") is not True:
                raise JobQueueError("Agent Contract does not enable scheduled execution")
            contract_tools = set(agent["contract_snapshot"].get("tool_keys", []))
            if not set(request.requested_tool_keys).issubset(contract_tools):
                raise JobQueueError("schedule requested tools outside the Agent Contract")
            self._require_optional_scope(
                connection,
                actor.organization_id,
                request.workspace_id,
                request.division_id,
                request.project_id,
            )
            row = connection.execute(
                """
                INSERT INTO jobs.agent_schedules (
                    organization_id, workspace_id, division_id, project_id, tenant_id,
                    agent_contract_id, owner_user_id, schedule_expression, timezone,
                    input_fixture, requested_tool_keys, enabled, confirmed_by_user_id,
                    next_run_at, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (agent_contract_id, workspace_id, tenant_id)
                DO UPDATE SET division_id = EXCLUDED.division_id,
                    project_id = EXCLUDED.project_id,
                    owner_user_id = EXCLUDED.owner_user_id,
                    schedule_expression = EXCLUDED.schedule_expression,
                    timezone = EXCLUDED.timezone,
                    input_fixture = EXCLUDED.input_fixture,
                    requested_tool_keys = EXCLUDED.requested_tool_keys,
                    enabled = EXCLUDED.enabled,
                    confirmed_by_user_id = EXCLUDED.confirmed_by_user_id,
                    next_run_at = EXCLUDED.next_run_at,
                    correlation_id = EXCLUDED.correlation_id,
                    updated_at = now()
                RETURNING *
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    request.division_id,
                    request.project_id,
                    request.tenant_id,
                    agent["agent_contract_id"],
                    actor.user_id,
                    request.schedule_expression,
                    request.timezone,
                    Jsonb(request.input),
                    Jsonb(request.requested_tool_keys),
                    request.enabled,
                    actor.user_id,
                    next_run_at,
                    correlation_id,
                ),
            ).fetchone()
            if row is None:
                raise JobQueueError("Agent schedule could not be persisted")
            self._audit_schedule(
                connection,
                actor.organization_id,
                "AGENT_SCHEDULE_CONFIGURED",
                row["agent_schedule_id"],
                correlation_id,
                "Human confirmed a governed Agent schedule",
                {"agent_key": request.agent_key, "enabled": request.enabled},
                actor_user_id=actor.user_id,
            )
            return AgentScheduleRecord(
                agent_key=request.agent_key,
                input=row.pop("input_fixture"),
                requested_tool_keys=row.pop("requested_tool_keys"),
                **row,
            )

    def list_agent_schedules(self, actor: ActorContext) -> list[AgentScheduleRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT schedule.*, contract.agent_key
                FROM jobs.agent_schedules AS schedule
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = schedule.agent_contract_id
                WHERE schedule.organization_id = %s
                  AND schedule.workspace_id = ANY(%s)
                  AND (
                      schedule.tenant_id IS NULL
                      OR schedule.tenant_id = ANY(%s)
                  )
                ORDER BY schedule.updated_at DESC, schedule.agent_schedule_id DESC
                """,
                (actor.organization_id, actor.workspace_ids, actor.tenant_ids),
            ).fetchall()
        return [self._schedule_record(row) for row in rows]

    def set_agent_schedule_enabled(
        self,
        schedule_id: UUID,
        actor: ActorContext,
        *,
        enabled: bool,
        correlation_id: UUID,
    ) -> AgentScheduleRecord:
        if not can_govern_agents(actor):
            raise JobQueueError("Agent schedule governance permission is required")
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE jobs.agent_schedules AS schedule
                SET enabled = %s, correlation_id = %s, updated_at = now()
                FROM agents.contracts AS contract
                WHERE schedule.agent_schedule_id = %s
                  AND contract.agent_contract_id = schedule.agent_contract_id
                  AND schedule.organization_id = %s
                  AND schedule.workspace_id = ANY(%s)
                  AND (
                      schedule.tenant_id IS NULL
                      OR schedule.tenant_id = ANY(%s)
                  )
                RETURNING schedule.*, contract.agent_key
                """,
                (
                    enabled,
                    correlation_id,
                    schedule_id,
                    actor.organization_id,
                    actor.workspace_ids,
                    actor.tenant_ids,
                ),
            ).fetchone()
            if row is None:
                raise JobQueueError("Agent schedule was not found in authenticated scope")
            self._audit_schedule(
                connection,
                actor.organization_id,
                "AGENT_SCHEDULE_ENABLED" if enabled else "AGENT_SCHEDULE_DISABLED",
                schedule_id,
                correlation_id,
                "Human changed the governed Agent schedule state",
                {"enabled": enabled, "agent_key": row["agent_key"]},
                actor_user_id=actor.user_id,
            )
            return self._schedule_record(row)

    def claim(
        self, worker_id: str, *, job_types: list[JobType] | None = None
    ) -> JobRecord | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs.queue
                WHERE status IN ('QUEUED', 'FAILED') AND next_retry_at <= now()
                  AND attempts < max_attempts
                  AND (%s::text[] IS NULL OR job_type = ANY(%s))
                ORDER BY next_retry_at, created_at, job_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (job_types, job_types),
            ).fetchone()
            if row is None:
                return None
            claimed = connection.execute(
                """
                UPDATE jobs.queue
                SET status = 'RUNNING', attempts = attempts + 1, locked_by = %s,
                    locked_at = now(), started_at = coalesce(started_at, now()),
                    safe_error_code = NULL
                WHERE job_id = %s
                RETURNING *
                """,
                (worker_id, row["job_id"]),
            ).fetchone()
            if claimed is None:
                raise JobQueueError("job claim was lost")
            return JobRecord(**claimed)

    def succeed(self, job: JobRecord, *, result: dict[str, Any] | None = None) -> JobRecord:
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE jobs.queue
                SET status = 'SUCCEEDED', completed_at = now(), locked_by = NULL,
                    locked_at = NULL, payload = payload || %s
                WHERE job_id = %s AND status = 'RUNNING' AND locked_by = %s
                RETURNING *
                """,
                (Jsonb({"result": result or {}}), job.job_id, job.locked_by),
            ).fetchone()
            if row is None:
                raise JobQueueError("running job could not be completed")
            self._audit(
                connection,
                job.organization_id,
                "JOB_SUCCEEDED",
                job.job_id,
                job.correlation_id,
                {"job_type": job.job_type, "attempts": job.attempts},
            )
            return JobRecord(**row)

    def fail(self, job: JobRecord, safe_error_code: str) -> JobRecord:
        retry_at = datetime.now(UTC) + timedelta(
            seconds=min(15 * (2 ** max(job.attempts - 1, 0)), 900)
        )
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE jobs.queue
                SET status = 'FAILED', completed_at = CASE
                        WHEN attempts >= max_attempts THEN now() ELSE NULL END,
                    next_retry_at = %s, safe_error_code = %s,
                    locked_by = NULL, locked_at = NULL
                WHERE job_id = %s AND status = 'RUNNING' AND locked_by = %s
                RETURNING *
                """,
                (retry_at, safe_error_code[:120], job.job_id, job.locked_by),
            ).fetchone()
            if row is None:
                raise JobQueueError("running job failure could not be recorded")
            self._audit(
                connection,
                job.organization_id,
                "JOB_FAILED",
                job.job_id,
                job.correlation_id,
                {
                    "job_type": job.job_type,
                    "attempts": job.attempts,
                    "safe_error_code": safe_error_code[:120],
                    "will_retry": job.attempts < job.max_attempts,
                },
            )
            return JobRecord(**row)

    def cancel(self, job_id: UUID, organization_id: UUID) -> JobRecord:
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE jobs.queue
                SET status = 'CANCELLED', completed_at = now(), locked_by = NULL,
                    locked_at = NULL
                WHERE job_id = %s AND organization_id = %s
                  AND status IN ('QUEUED', 'FAILED')
                RETURNING *
                """,
                (job_id, organization_id),
            ).fetchone()
            if row is None:
                raise JobQueueError("queued job was not found or is already running")
            return JobRecord(**row)

    def list_jobs(
        self,
        organization_id: UUID,
        workspace_ids: list[UUID],
        *,
        limit: int = 100,
    ) -> list[JobRecord]:
        if not workspace_ids:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs.queue
                WHERE organization_id = %s
                  AND (workspace_id IS NULL OR workspace_id = ANY(%s))
                ORDER BY created_at DESC LIMIT %s
                """,
                (organization_id, workspace_ids, min(limit, 200)),
            ).fetchall()
        return [JobRecord(**row) for row in rows]

    def schedule_due_reports(self, scheduler_id: str, *, limit: int = 100) -> list[JobRecord]:
        enqueued: list[JobRecord] = []
        with self._transaction() as connection:
            schedules = connection.execute(
                """
                SELECT schedule.report_schedule_id, schedule.report_definition_id,
                       schedule.timezone, schedule.schedule_expression, schedule.next_run_at,
                       definition.organization_id, definition.workspace_id,
                       definition.owner_user_id, definition.recipient_user_ids
                FROM reporting.schedules AS schedule
                JOIN reporting.definitions AS definition
                  ON definition.report_definition_id = schedule.report_definition_id
                WHERE schedule.active AND schedule.confirmed_by_user_id IS NOT NULL
                  AND definition.status = 'ACTIVE' AND schedule.next_run_at <= now()
                ORDER BY schedule.next_run_at
                FOR UPDATE OF schedule SKIP LOCKED
                LIMIT %s
                """,
                (min(limit, 500),),
            ).fetchall()
            for schedule in schedules:
                idempotency_key = (
                    f"report:{schedule['report_definition_id']}:"
                    f"{schedule['next_run_at'].isoformat()}"
                )
                row = connection.execute(
                    """
                    INSERT INTO jobs.queue (
                        organization_id, workspace_id, job_type, payload, correlation_id,
                        owner_user_id, idempotency_key
                    ) VALUES (%s, %s, 'SCHEDULED_REPORT', %s, gen_random_uuid(), %s, %s)
                    ON CONFLICT (organization_id, job_type, idempotency_key)
                    DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                    RETURNING *
                    """,
                    (
                        schedule["organization_id"],
                        schedule["workspace_id"],
                        Jsonb(
                            {
                                "report_definition_id": str(
                                    schedule["report_definition_id"]
                                ),
                                "scheduled_for": schedule["next_run_at"].isoformat(),
                                "recipient_user_ids": [
                                    str(item) for item in schedule["recipient_user_ids"]
                                ],
                            }
                        ),
                        schedule["owner_user_id"],
                        idempotency_key,
                    ),
                ).fetchone()
                if row is not None:
                    enqueued.append(JobRecord(**row))
                connection.execute(
                    """
                    UPDATE reporting.schedules
                    SET last_run_at = next_run_at,
                        next_run_at = %s
                    WHERE report_schedule_id = %s
                    """,
                    (
                        next_schedule_at(
                            schedule["schedule_expression"],
                            schedule["next_run_at"],
                            schedule["timezone"],
                        ),
                        schedule["report_schedule_id"],
                    ),
                )
            self._heartbeat(connection, "SCHEDULER", scheduler_id)
        return enqueued

    def schedule_due_agents(self, scheduler_id: str, *, limit: int = 100) -> list[JobRecord]:
        """Convert due, revalidated Agent schedules into durable AGENT_RUN jobs."""
        enqueued: list[JobRecord] = []
        with self._transaction() as connection:
            schedules = connection.execute(
                """
                SELECT schedule.*, contract.agent_key
                FROM jobs.agent_schedules AS schedule
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = schedule.agent_contract_id
                WHERE schedule.enabled AND schedule.confirmed_by_user_id IS NOT NULL
                  AND schedule.next_run_at <= now()
                ORDER BY schedule.next_run_at, schedule.agent_schedule_id
                FOR UPDATE OF schedule SKIP LOCKED
                LIMIT %s
                """,
                (min(limit, 500),),
            ).fetchall()
            for schedule in schedules:
                scheduled_for = schedule["next_run_at"]
                correlation_id = uuid4()
                version_id, block_reason = self._agent_schedule_guard(connection, schedule)
                if block_reason is not None or version_id is None:
                    status: Literal["SKIPPED", "BLOCKED"] = (
                        "SKIPPED" if block_reason == "SCHEDULE_DISABLED" else "BLOCKED"
                    )
                    self._record_agent_dispatch(
                        connection,
                        schedule,
                        version_id,
                        None,
                        status,
                        block_reason or "AGENT_VERSION_UNAVAILABLE",
                        correlation_id,
                    )
                else:
                    idempotency_key = (
                        f"agent:{schedule['agent_schedule_id']}:{scheduled_for.isoformat()}"
                    )
                    job = connection.execute(
                        """
                        INSERT INTO jobs.queue (
                            organization_id, workspace_id, job_type, payload, correlation_id,
                            owner_user_id, idempotency_key
                        ) VALUES (%s, %s, 'AGENT_RUN', %s, %s, %s, %s)
                        ON CONFLICT (organization_id, job_type, idempotency_key)
                        DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                        RETURNING *
                        """,
                        (
                            schedule["organization_id"],
                            schedule["workspace_id"],
                            Jsonb(
                                {
                                    "agent_schedule_id": str(schedule["agent_schedule_id"]),
                                    "agent_version_id": str(version_id),
                                    "scheduled_for": scheduled_for.isoformat(),
                                }
                            ),
                            correlation_id,
                            schedule["owner_user_id"],
                            idempotency_key,
                        ),
                    ).fetchone()
                    if job is not None:
                        enqueued.append(JobRecord(**job))
                        self._record_agent_dispatch(
                            connection,
                            schedule,
                            version_id,
                            job["job_id"],
                            "ENQUEUED",
                            "All schedule safety controls passed",
                            correlation_id,
                        )
                connection.execute(
                    """
                    UPDATE jobs.agent_schedules
                    SET last_run_at = next_run_at, next_run_at = %s, updated_at = now()
                    WHERE agent_schedule_id = %s
                    """,
                    (
                        next_schedule_at(
                            schedule["schedule_expression"],
                            scheduled_for,
                            schedule["timezone"],
                        ),
                        schedule["agent_schedule_id"],
                    ),
                )
            self._heartbeat(connection, "SCHEDULER", scheduler_id)
        return enqueued

    def authorize_agent_job(self, job: JobRecord) -> AgentJobContext:
        """Reload schedule authority and recheck it immediately before worker execution."""
        if job.job_type != "AGENT_RUN" or job.workspace_id is None or job.owner_user_id is None:
            raise JobQueueError("Agent job context is invalid")
        try:
            schedule_id = UUID(str(job.payload["agent_schedule_id"]))
            expected_version_id = UUID(str(job.payload["agent_version_id"]))
        except (KeyError, ValueError) as error:
            raise JobQueueError("Agent job payload is invalid") from error
        with self._connection() as connection:
            schedule = connection.execute(
                """
                SELECT schedule.*, contract.agent_key
                FROM jobs.agent_schedules AS schedule
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = schedule.agent_contract_id
                WHERE schedule.agent_schedule_id = %s
                  AND schedule.organization_id = %s AND schedule.workspace_id = %s
                  AND schedule.owner_user_id = %s
                """,
                (schedule_id, job.organization_id, job.workspace_id, job.owner_user_id),
            ).fetchone()
            if schedule is None:
                raise JobQueueError("Agent schedule authority was not found")
            active_version_id, block_reason = self._agent_schedule_guard(connection, schedule)
            if block_reason is not None or active_version_id != expected_version_id:
                raise JobQueueError(block_reason or "scheduled Agent version changed")
            return AgentJobContext(
                agent_schedule_id=schedule_id,
                agent_key=schedule["agent_key"],
                agent_version_id=expected_version_id,
                organization_id=job.organization_id,
                workspace_id=job.workspace_id,
                division_id=schedule["division_id"],
                project_id=schedule["project_id"],
                tenant_id=schedule["tenant_id"],
                owner_user_id=job.owner_user_id,
                input=schedule["input_fixture"],
                requested_tool_keys=schedule["requested_tool_keys"],
            )

    @staticmethod
    def _agent_schedule_guard(
        connection: psycopg.Connection[Any], schedule: dict[str, Any]
    ) -> tuple[UUID | None, str | None]:
        if not schedule["enabled"] or schedule["confirmed_by_user_id"] is None:
            return None, "SCHEDULE_DISABLED"
        active = connection.execute(
            """
            SELECT registry.active_version_id, version.contract_snapshot
            FROM agents.registry AS registry
            JOIN agents.versions AS version
              ON version.agent_version_id = registry.active_version_id
            WHERE registry.agent_contract_id = %s AND version.lifecycle_status = 'ACTIVE'
              AND EXISTS (
                  SELECT 1 FROM governance.agent_change_requests AS change
                  WHERE change.agent_version_id = version.agent_version_id
                    AND change.state = 'ACTIVE'
              )
            """,
            (schedule["agent_contract_id"],),
        ).fetchone()
        if active is None:
            return None, "AGENT_NOT_ACTIVE_OR_SUSPENDED"
        workspace = connection.execute(
            """
            SELECT 1 FROM workspace.workspaces
            WHERE workspace_id = %s AND organization_id = %s AND status = 'ACTIVE'
            """,
            (schedule["workspace_id"], schedule["organization_id"]),
        ).fetchone()
        if workspace is None:
            return active["active_version_id"], "WORKSPACE_INACTIVE"
        owner = connection.execute(
            """
            SELECT 1 FROM identity.users AS user_account
            JOIN workspace.memberships AS membership
              ON membership.user_id = user_account.user_id
             AND membership.workspace_id = %s
            WHERE user_account.user_id = %s AND user_account.organization_id = %s
              AND user_account.status = 'ACTIVE'
            """,
            (
                schedule["workspace_id"],
                schedule["owner_user_id"],
                schedule["organization_id"],
            ),
        ).fetchone()
        if owner is None:
            return active["active_version_id"], "SCHEDULE_OWNER_INACTIVE"
        killed = connection.execute(
            """
            SELECT 1 FROM governance.kill_switches
            WHERE organization_id = %s AND agent_contract_id = %s AND active
            """,
            (schedule["organization_id"], schedule["agent_contract_id"]),
        ).fetchone()
        if killed is not None:
            return active["active_version_id"], "KILL_SWITCH_ACTIVE"
        snapshot = active["contract_snapshot"]
        if snapshot.get("schedule_policy", {}).get("enabled") is not True:
            return active["active_version_id"], "CONTRACT_SCHEDULE_DISABLED"
        configured_tools = JobQueueRepository._configured_tools(
            connection, list(dict.fromkeys(snapshot.get("tool_keys", [])))
        )
        if set(snapshot.get("tool_keys", [])).difference(configured_tools):
            return active["active_version_id"], "TOOL_DEPENDENCY_UNAVAILABLE"
        if not set(schedule["requested_tool_keys"]).issubset(configured_tools):
            return active["active_version_id"], "SCHEDULE_TOOL_SCOPE_INVALID"
        permission_keys = list(dict.fromkeys(snapshot.get("permission_keys", [])))
        if permission_keys:
            permission_rows = connection.execute(
                """
                SELECT permission_key FROM governance.permission_policies
                WHERE agent_version_id = %s AND permission_key = ANY(%s)
                  AND effect = 'ALLOW' AND lifecycle_status = 'APPROVED'
                """,
                (active["active_version_id"], permission_keys),
            ).fetchall()
            approved_permissions = {row["permission_key"] for row in permission_rows}
            if set(permission_keys).difference(approved_permissions):
                return active["active_version_id"], "PERMISSION_DEPENDENCY_UNAVAILABLE"
        budget = connection.execute(
            """
            SELECT daily_request_limit,
                   (SELECT count(*) FROM runtime.agent_runs AS run
                    WHERE run.organization_id = limits.organization_id
                      AND run.workspace_id = limits.workspace_id
                      AND run.created_at >= date_trunc('day', now())) AS request_count
            FROM governance.cost_limits AS limits
            WHERE limits.organization_id = %s AND limits.workspace_id = %s AND limits.active
            """,
            (schedule["organization_id"], schedule["workspace_id"]),
        ).fetchone()
        if budget is None or budget["request_count"] >= budget["daily_request_limit"]:
            return active["active_version_id"], "BUDGET_UNAVAILABLE"
        return active["active_version_id"], None

    @staticmethod
    def _configured_tools(
        connection: psycopg.Connection[Any], tool_keys: list[str]
    ) -> set[str]:
        if not tool_keys:
            return set()
        rows = connection.execute(
            """
            SELECT tool.tool_key
            FROM capabilities.tools AS tool
            JOIN capabilities.definitions AS definition
              ON definition.capability_key = tool.capability_key
            WHERE tool.tool_key = ANY(%s) AND tool.lifecycle_status = 'APPROVED'
              AND definition.availability = 'AVAILABLE'
              AND definition.configuration_status = 'CONFIGURED'
            UNION
            SELECT tool_key FROM agents.tool_definitions
            WHERE tool_key = ANY(%s) AND lifecycle_status = 'APPROVED'
            """,
            (tool_keys, tool_keys),
        ).fetchall()
        return {row["tool_key"] for row in rows}

    @staticmethod
    def _schedule_record(row: dict[str, Any]) -> AgentScheduleRecord:
        data = dict(row)
        data["input"] = data.pop("input_fixture")
        return AgentScheduleRecord(**data)

    @staticmethod
    def _record_agent_dispatch(
        connection: psycopg.Connection[Any],
        schedule: dict[str, Any],
        agent_version_id: UUID | None,
        job_id: UUID | None,
        status: Literal["ENQUEUED", "SKIPPED", "BLOCKED"],
        reason: str,
        correlation_id: UUID,
    ) -> None:
        connection.execute(
            """
            INSERT INTO jobs.agent_schedule_dispatches (
                agent_schedule_id, agent_version_id, job_id, status, reason,
                scheduled_for, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                schedule["agent_schedule_id"],
                agent_version_id,
                job_id,
                status,
                reason,
                schedule["next_run_at"],
                correlation_id,
            ),
        )
        JobQueueRepository._audit_schedule(
            connection,
            schedule["organization_id"],
            f"AGENT_SCHEDULE_{status}",
            schedule["agent_schedule_id"],
            correlation_id,
            reason,
            {"agent_key": schedule["agent_key"], "status": status},
        )

    def heartbeat(self, service_name: Literal["WORKER", "SCHEDULER"], instance_id: str) -> None:
        with self._transaction() as connection:
            self._heartbeat(connection, service_name, instance_id)

    @staticmethod
    def _require_optional_scope(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        division_id: UUID | None,
        project_id: UUID | None,
    ) -> None:
        if division_id is not None:
            division = connection.execute(
                """
                SELECT 1 FROM identity.divisions
                WHERE division_id = %s AND organization_id = %s
                """,
                (division_id, organization_id),
            ).fetchone()
            if division is None:
                raise JobQueueError("schedule division is outside the organization scope")
        if project_id is not None:
            project = connection.execute(
                """
                SELECT 1 FROM portfolio.projects
                WHERE project_id = %s AND organization_id = %s AND workspace_id = %s
                """,
                (project_id, organization_id, workspace_id),
            ).fetchone()
            if project is None:
                raise JobQueueError("schedule project is outside the workspace scope")

    @staticmethod
    def _heartbeat(
        connection: psycopg.Connection[Any], service_name: str, instance_id: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO jobs.service_heartbeats (service_name, instance_id)
            VALUES (%s, %s)
            ON CONFLICT (service_name) DO UPDATE
            SET instance_id = EXCLUDED.instance_id, last_seen_at = now()
            """,
            (service_name, instance_id),
        )

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        action: str,
        job_id: UUID,
        correlation_id: UUID,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, system_actor, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'SYSTEM', 'GENESIS', %s, 'BACKGROUND_JOB', %s, %s, %s, %s)
            """,
            (
                organization_id,
                action,
                job_id,
                correlation_id,
                "Durable background job state changed",
                Jsonb(metadata),
            ),
        )

    @staticmethod
    def _audit_schedule(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        action: str,
        schedule_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
        *,
        actor_user_id: UUID | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, system_actor, action,
                entity_type, entity_id, correlation_id, reason, metadata
            ) VALUES (
                %s, CASE WHEN %s::uuid IS NULL THEN 'SYSTEM' ELSE 'HUMAN' END,
                %s, CASE WHEN %s::uuid IS NULL THEN 'GENESIS' ELSE NULL END,
                %s, 'AGENT_SCHEDULE', %s, %s, %s, %s
            )
            """,
            (
                organization_id,
                actor_user_id,
                actor_user_id,
                actor_user_id,
                action,
                schedule_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def next_schedule_at(expression: str, previous: datetime, timezone: str) -> datetime:
    parts = expression.strip().split()
    if len(parts) == 2 and parts[0].upper() == "DAILY":
        hour_text, minute_text = parts[1].replace(".", ":").split(":", 1)
    elif len(parts) == 5 and parts[2:] == ["*", "*", "*"]:
        minute_text, hour_text = parts[0], parts[1]
    else:
        raise JobQueueError(
            "schedule expression must be 'DAILY HH:MM' or a daily five-field cron"
        )
    try:
        hour, minute = int(hour_text), int(minute_text)
        zone = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise JobQueueError("schedule time or timezone is invalid") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise JobQueueError("schedule hour or minute is invalid")
    local_previous = previous.astimezone(zone)
    candidate = local_previous.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_previous:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)

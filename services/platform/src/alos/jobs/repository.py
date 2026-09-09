"""Transactional PostgreSQL job queue with retries and idempotency."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.persistence.database import psycopg_url

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

    def heartbeat(self, service_name: Literal["WORKER", "SCHEDULER"], instance_id: str) -> None:
        with self._transaction() as connection:
            self._heartbeat(connection, service_name, instance_id)

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

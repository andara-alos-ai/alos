"""Durable job worker process; safe to run as multiple replicas."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from alos.config import Settings, get_settings
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.jobs.repository import JobEnqueueRequest, JobQueueError, JobQueueRepository, JobRecord
from alos.model_gateway import GuardedModelGateway, RetryingModelGateway, UsageBudget
from alos.model_gateway_factory import create_model_gateway
from alos.operational.models import ReportGenerateRequest
from alos.operational.repository import OperationalRepository
from alos.persistence.database import psycopg_url
from alos.runtime.service import AgentRunRequest, AgentRuntime, AgentRuntimeRepository
from alos.security.tokens import ActorContext


class JobHandlerError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DurableWorker:
    def __init__(
        self,
        database_url: str,
        worker_id: str | None = None,
        *,
        runtime_factory: Callable[[], AgentRuntime] | None = None,
    ) -> None:
        self._database_url = psycopg_url(database_url)
        self._queue = JobQueueRepository(database_url)
        self._operations = OperationalRepository(database_url)
        self._worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._runtime_factory = runtime_factory or _build_agent_runtime
        self._handlers: dict[str, Callable[[JobRecord], dict[str, Any]]] = {
            "AGENT_RUN": self._run_agent,
            "SCHEDULED_REPORT": self._generate_report,
            "NOTIFICATION": self._deliver_notification,
        }

    def run_once(self) -> JobRecord | None:
        job = self._queue.claim(self._worker_id)
        if job is None:
            self._queue.heartbeat("WORKER", self._worker_id)
            return None
        try:
            handler = self._handlers.get(job.job_type)
            if handler is None:
                raise JobHandlerError("HANDLER_NOT_CONFIGURED")
            result = handler(job)
            return self._queue.succeed(job, result=result)
        except JobHandlerError as error:
            return self._queue.fail(job, error.code)
        except Exception:
            return self._queue.fail(job, "SAFE_HANDLER_FAILURE")
        finally:
            # A busy worker must remain observable just like an idle worker.
            self._queue.heartbeat("WORKER", self._worker_id)

    def run_forever(self, poll_seconds: float = 2.0) -> None:
        while True:
            processed = self.run_once()
            if processed is None:
                time.sleep(max(0.2, min(poll_seconds, 30)))

    def _generate_report(self, job: JobRecord) -> dict[str, Any]:
        if job.owner_user_id is None or job.workspace_id is None:
            raise JobHandlerError("REPORT_JOB_CONTEXT_INVALID")
        try:
            definition_id = UUID(str(job.payload["report_definition_id"]))
        except (KeyError, ValueError) as error:
            raise JobHandlerError("REPORT_JOB_PAYLOAD_INVALID") from error
        actor = self._actor(job.owner_user_id, job.organization_id)
        report = self._operations.generate_report(
            actor,
            definition_id,
            ReportGenerateRequest(idempotency_key=job.idempotency_key),
            correlation_id=job.correlation_id,
        )
        for recipient in job.payload.get("recipient_user_ids", []):
            recipient_id = UUID(str(recipient))
            self._queue.enqueue(
                JobEnqueueRequest(
                    organization_id=job.organization_id,
                    workspace_id=job.workspace_id,
                    job_type="NOTIFICATION",
                    payload={
                        "recipient_user_id": str(recipient_id),
                        "notification_type": "REPORT_READY",
                        "title": "Laporan siap ditinjau",
                        "body": "Laporan terjadwal telah dibuat dari data ALOS yang berizin.",
                        "entity_type": "REPORT",
                        "entity_id": str(report.report_id),
                    },
                    correlation_id=job.correlation_id,
                    owner_user_id=recipient_id,
                    idempotency_key=f"notification:{report.report_id}:{recipient_id}",
                )
            )
        return {"report_id": str(report.report_id), "report_status": report.status}

    def _deliver_notification(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        try:
            recipient_user_id = UUID(str(payload["recipient_user_id"]))
            entity_id = UUID(str(payload["entity_id"]))
        except (KeyError, ValueError) as error:
            raise JobHandlerError("NOTIFICATION_PAYLOAD_INVALID") from error
        with self._transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO notifications.inbox (
                    organization_id, workspace_id, recipient_user_id, notification_type,
                    title, body, entity_type, entity_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING notification_id
                """,
                (
                    job.organization_id,
                    job.workspace_id,
                    recipient_user_id,
                    str(payload.get("notification_type", "REPORT_READY")),
                    str(payload.get("title", "ALOS notification"))[:200],
                    str(payload.get("body", ""))[:5_000],
                    str(payload.get("entity_type", "REPORT"))[:80],
                    entity_id,
                ),
            ).fetchone()
            if row is None:
                raise JobHandlerError("NOTIFICATION_PERSIST_FAILED")
        return {"notification_id": str(row["notification_id"])}

    def _run_agent(self, job: JobRecord) -> dict[str, Any]:
        try:
            context = self._queue.authorize_agent_job(job)
        except JobQueueError as error:
            raise JobHandlerError("AGENT_SCHEDULE_AUTHORITY_INVALID") from error
        actor = self._actor(
            context.owner_user_id,
            context.organization_id,
            tenant_id=context.tenant_id,
        )
        result = self._runtime_factory().execute(
            context.agent_key,
            AgentRunRequest(
                workspace_id=context.workspace_id,
                division_id=context.division_id,
                project_id=context.project_id,
                tenant_id=context.tenant_id,
                input=context.input,
                requested_tool_keys=context.requested_tool_keys,
                testing=False,
            ),
            organization_id=context.organization_id,
            actor_user_id=context.owner_user_id,
            correlation_id=job.correlation_id,
            actor=actor,
            allow_draft=False,
            target_agent_version_id=context.agent_version_id,
        )
        if result.status != "SUCCEEDED":
            raise JobHandlerError(result.error_code or f"AGENT_RUN_{result.status}")
        return {
            "agent_run_id": str(result.agent_run_id),
            "agent_version_id": str(context.agent_version_id),
            "status": result.status,
            "total_model_calls": result.total_model_calls,
            "total_tool_calls": result.total_tool_calls,
            "total_tokens": result.total_tokens,
        }

    def _actor(
        self, user_id: UUID, organization_id: UUID, *, tenant_id: UUID | None = None
    ) -> ActorContext:
        with self._connection() as connection:
            user = connection.execute(
                """
                SELECT default_data_scope FROM identity.users
                WHERE user_id = %s AND organization_id = %s AND status = 'ACTIVE'
                """,
                (user_id, organization_id),
            ).fetchone()
            if user is None:
                raise JobHandlerError("JOB_OWNER_INACTIVE")
            role_rows = connection.execute(
                """
                SELECT role_code FROM identity.role_assignments
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            ).fetchall()
            division_rows = connection.execute(
                """
                SELECT DISTINCT division.code
                FROM identity.role_assignments AS assignment
                JOIN identity.divisions AS division
                  ON division.division_id = assignment.division_id
                WHERE assignment.user_id = %s AND assignment.revoked_at IS NULL
                  AND division.organization_id = %s
                """,
                (user_id, organization_id),
            ).fetchall()
            workspace_rows = connection.execute(
                """
                SELECT membership.workspace_id
                FROM workspace.memberships AS membership
                JOIN workspace.workspaces AS workspace
                  ON workspace.workspace_id = membership.workspace_id
                WHERE membership.user_id = %s AND workspace.organization_id = %s
                  AND workspace.status = 'ACTIVE'
                """,
                (user_id, organization_id),
            ).fetchall()
        now = datetime.now(UTC)
        return ActorContext(
            user_id=user_id,
            organization_id=organization_id,
            roles=[HumanRole(row["role_code"]) for row in role_rows],
            division_codes=[DivisionCode(row["code"]) for row in division_rows],
            workspace_ids=[row["workspace_id"] for row in workspace_rows],
            tenant_ids=[tenant_id] if tenant_id is not None else [],
            data_scope=DataScope(user["default_data_scope"]),
            permissions=[],
            issued_at=now,
            expires_at=now + timedelta(hours=1),
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


def _build_agent_runtime() -> AgentRuntime:
    settings: Settings = get_settings()
    delegate, close_gateway = create_model_gateway(settings)
    gateway = GuardedModelGateway(
        RetryingModelGateway(delegate, settings.llm_max_retries),
        settings,
        UsageBudget(
            request_limit=settings.agentic_max_model_steps,
            output_token_limit=settings.llm_max_output_tokens * settings.agentic_max_model_steps,
        ),
    )
    return AgentRuntime(
        AgentRuntimeRepository(settings.database_url, settings),
        gateway,
        settings,
        close_gateway=close_gateway,
    )


def main() -> None:
    DurableWorker(get_settings().database_url).run_forever()


if __name__ == "__main__":
    main()

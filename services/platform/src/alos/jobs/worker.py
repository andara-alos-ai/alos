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

from alos.config import get_settings
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.jobs.repository import JobEnqueueRequest, JobQueueRepository, JobRecord
from alos.operational.models import ReportGenerateRequest
from alos.operational.repository import OperationalRepository
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class JobHandlerError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DurableWorker:
    def __init__(self, database_url: str, worker_id: str | None = None) -> None:
        self._database_url = psycopg_url(database_url)
        self._queue = JobQueueRepository(database_url)
        self._operations = OperationalRepository(database_url)
        self._worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._handlers: dict[str, Callable[[JobRecord], dict[str, Any]]] = {
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

    def _actor(self, user_id: UUID, organization_id: UUID) -> ActorContext:
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


def main() -> None:
    DurableWorker(get_settings().database_url).run_forever()


if __name__ == "__main__":
    main()

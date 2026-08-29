from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.persistence.database import PostgresOperationalStore
from alos.platform.dispatch.models import (
    OperationsHealth,
    OutboxDestination,
    OutboxEvent,
    WorkerRunSummary,
)
from alos.security import Principal


class PostgresDispatchRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def organization_ids(self) -> tuple[UUID, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("SELECT organization_id FROM identity.organizations ORDER BY organization_id")
            ).scalars()
            return tuple(rows)

    def enqueue_pending_reminders(
        self,
        destinations: tuple[OutboxDestination, ...],
        max_attempts: int,
    ) -> int:
        if not destinations:
            return 0
        inserted = 0
        with self._engine.begin() as connection:
            for destination in destinations:
                result = connection.execute(
                    text(
                        """
                        INSERT INTO integration.outbox_events
                            (organization_id, topic, aggregate_type, aggregate_id,
                             destination, payload, status, max_attempts, available_at,
                             correlation_id, idempotency_key, created_at, updated_at)
                        SELECT r.organization_id, 'reminder.delivery', 'reminder',
                               r.reminder_id, :destination,
                               jsonb_build_object(
                                   'reminder_id', r.reminder_id,
                                   'work_item_id', COALESCE(r.work_item_id, ar.work_item_id),
                                   'approval_request_id', r.approval_request_id,
                                   'recipient_user_id', r.recipient_user_id,
                                   'division_code', d.code,
                                   'reminder_type', r.reminder_type,
                                   'escalation_level', r.escalation_level,
                                   'scheduled_for', r.scheduled_for
                               ),
                               'PENDING', :max_attempts, now(),
                               COALESCE(wi.correlation_id, gen_random_uuid()),
                               'reminder:' || r.reminder_id::text,
                               now(), now()
                        FROM platform.reminders r
                        LEFT JOIN identity.divisions d ON d.division_id = r.division_id
                        LEFT JOIN governance.approval_requests ar
                          ON ar.approval_request_id = r.approval_request_id
                        LEFT JOIN platform.work_items wi
                          ON wi.work_item_id = COALESCE(r.work_item_id, ar.work_item_id)
                        WHERE r.status = 'PENDING'
                        ON CONFLICT (organization_id, destination, idempotency_key)
                        DO NOTHING
                        RETURNING outbox_event_id
                        """
                    ),
                    {
                        "destination": destination.value,
                        "max_attempts": max_attempts,
                    },
                )
                inserted += len(result.fetchall())
        return inserted

    def start_worker_run(self, worker_name: str, instance_id: str) -> UUID:
        worker_run_id = uuid4()
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO observability.worker_runs
                        (worker_run_id, worker_name, instance_id, status, started_at)
                    VALUES (:worker_run_id, :worker_name, :instance_id, 'RUNNING', now())
                    """
                ),
                {
                    "worker_run_id": worker_run_id,
                    "worker_name": worker_name,
                    "instance_id": instance_id,
                },
            )
        return worker_run_id

    def finish_worker_run(
        self,
        worker_run_id: UUID,
        *,
        status: str,
        organizations_evaluated: int,
        reminders_enqueued: int,
        events_claimed: int,
        events_delivered: int,
        events_retried: int,
        events_dead_lettered: int,
        error_summary: str | None,
    ) -> WorkerRunSummary:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        UPDATE observability.worker_runs
                        SET status = :status,
                            organizations_evaluated = :organizations_evaluated,
                            reminders_enqueued = :reminders_enqueued,
                            events_claimed = :events_claimed,
                            events_delivered = :events_delivered,
                            events_retried = :events_retried,
                            events_dead_lettered = :events_dead_lettered,
                            error_summary = :error_summary,
                            completed_at = now()
                        WHERE worker_run_id = :worker_run_id AND status = 'RUNNING'
                        RETURNING *
                        """
                    ),
                    {
                        "worker_run_id": worker_run_id,
                        "status": status,
                        "organizations_evaluated": organizations_evaluated,
                        "reminders_enqueued": reminders_enqueued,
                        "events_claimed": events_claimed,
                        "events_delivered": events_delivered,
                        "events_retried": events_retried,
                        "events_dead_lettered": events_dead_lettered,
                        "error_summary": error_summary,
                    },
                )
                .mappings()
                .one()
            )
        return WorkerRunSummary.model_validate(dict(row))

    def claim_events(
        self,
        *,
        instance_id: str,
        batch_size: int,
        lease_seconds: int,
        destinations: tuple[OutboxDestination, ...],
    ) -> tuple[OutboxEvent, ...]:
        if not destinations:
            return ()
        stale_before = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE integration.outbox_events
                    SET status = 'RETRY', locked_at = NULL, locked_by = NULL,
                        available_at = now(), updated_at = now(),
                        last_error = 'Worker lease expired before completion'
                    WHERE status = 'PROCESSING' AND locked_at < :stale_before
                    """
                ),
                {"stale_before": stale_before},
            )
            rows = connection.execute(
                text(
                    """
                    WITH candidates AS (
                        SELECT outbox_event_id
                        FROM integration.outbox_events
                        WHERE status IN ('PENDING', 'RETRY')
                          AND available_at <= now()
                          AND destination = ANY(CAST(:destinations AS text[]))
                        ORDER BY available_at, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT :batch_size
                    )
                    UPDATE integration.outbox_events event
                    SET status = 'PROCESSING', locked_at = now(), locked_by = :instance_id,
                        attempt_count = attempt_count + 1, updated_at = now()
                    FROM candidates
                    WHERE event.outbox_event_id = candidates.outbox_event_id
                    RETURNING event.*
                    """
                ),
                {
                    "instance_id": instance_id,
                    "batch_size": batch_size,
                    "destinations": [item.value for item in destinations],
                },
            ).mappings()
            return tuple(OutboxEvent.model_validate(dict(row)) for row in rows)

    def mark_delivered(self, event: OutboxEvent, response_status: int | None = None) -> None:
        with self._engine.begin() as connection:
            if event.destination == OutboxDestination.INTERNAL_NOTIFICATION:
                connection.execute(
                    text(
                        """
                        UPDATE platform.reminders
                        SET status = 'DELIVERED', delivered_at = now()
                        WHERE reminder_id = :reminder_id AND status = 'PENDING'
                        """
                    ),
                    {"reminder_id": event.aggregate_id},
                )
            connection.execute(
                text(
                    """
                    UPDATE integration.outbox_events
                    SET status = 'DELIVERED', delivered_at = now(),
                        response_status = :response_status,
                        locked_at = NULL, locked_by = NULL,
                        last_error = NULL, updated_at = now()
                    WHERE outbox_event_id = :outbox_event_id AND status = 'PROCESSING'
                    """
                ),
                {
                    "outbox_event_id": event.outbox_event_id,
                    "response_status": response_status,
                },
            )

    def mark_failed(self, event: OutboxEvent, error: str, retry_seconds: int) -> str:
        terminal = event.attempt_count >= event.max_attempts
        next_status = "DEAD_LETTER" if terminal else "RETRY"
        sanitized_error = error.replace("\r", " ").replace("\n", " ")[:500]
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE integration.outbox_events
                    SET status = :status,
                        available_at = CASE
                            WHEN :status = 'RETRY'
                            THEN now() + (:retry_seconds * interval '1 second')
                            ELSE available_at
                        END,
                        locked_at = NULL, locked_by = NULL,
                        last_error = :last_error, updated_at = now()
                    WHERE outbox_event_id = :outbox_event_id AND status = 'PROCESSING'
                    """
                ),
                {
                    "status": next_status,
                    "retry_seconds": retry_seconds,
                    "last_error": sanitized_error,
                    "outbox_event_id": event.outbox_event_id,
                },
            )
        return next_status

    def operations_health(self, organization_id: UUID) -> OperationsHealth:
        with self._engine.connect() as connection:
            counts = (
                connection.execute(
                    text(
                        """
                    SELECT
                      count(*) FILTER (WHERE status = 'PENDING') AS pending_events,
                      count(*) FILTER (WHERE status = 'RETRY') AS retry_events,
                      count(*) FILTER (WHERE status = 'PROCESSING') AS processing_events,
                      count(*) FILTER (WHERE status = 'DEAD_LETTER') AS dead_letter_events,
                      min(created_at) FILTER (
                        WHERE status IN ('PENDING', 'RETRY', 'PROCESSING')
                      ) AS oldest_pending_at
                    FROM integration.outbox_events
                    WHERE organization_id = :organization_id
                    """
                    ),
                    {"organization_id": organization_id},
                )
                .mappings()
                .one()
            )
            latest = (
                connection.execute(
                    text(
                        """
                    SELECT status, started_at, completed_at
                    FROM observability.worker_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                    )
                )
                .mappings()
                .one_or_none()
            )
        return OperationsHealth(
            **dict(counts),
            last_worker_status=latest["status"] if latest else None,
            last_worker_started_at=latest["started_at"] if latest else None,
            last_worker_completed_at=latest["completed_at"] if latest else None,
        )

    def requeue_dead_letter(
        self,
        outbox_event_id: UUID,
        reason: str,
        principal: Principal,
    ) -> OutboxEvent:
        with self._engine.begin() as connection:
            before = (
                connection.execute(
                    text(
                        """
                        SELECT * FROM integration.outbox_events
                        WHERE outbox_event_id = :outbox_event_id
                          AND organization_id = :organization_id
                        FOR UPDATE
                        """
                    ),
                    {
                        "outbox_event_id": outbox_event_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if before is None:
                raise KeyError("Outbox event tidak ditemukan")
            if before["status"] != "DEAD_LETTER":
                raise ValueError("Hanya dead-letter event yang dapat dimasukkan ulang")
            row = (
                connection.execute(
                    text(
                        """
                        UPDATE integration.outbox_events
                        SET status = 'RETRY', attempt_count = 0, available_at = now(),
                            locked_at = NULL, locked_by = NULL, last_error = NULL,
                            response_status = NULL, updated_at = now()
                        WHERE outbox_event_id = :outbox_event_id
                        RETURNING *
                        """
                    ),
                    {"outbox_event_id": outbox_event_id},
                )
                .mappings()
                .one()
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "outbox.dead_letter_requeued",
                "outbox_event",
                outbox_event_id,
                uuid4(),
                dict(before),
                {"status": "RETRY", "reason": reason},
                reason,
            )
        return OutboxEvent.model_validate(dict(row))

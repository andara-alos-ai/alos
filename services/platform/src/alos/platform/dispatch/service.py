from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from alos.integrations.webhooks import WebhookClient
from alos.platform.dispatch.models import OutboxDestination, OutboxEvent, WorkerRunSummary
from alos.platform.dispatch.repository import PostgresDispatchRepository
from alos.platform.operations import DeadlineEvaluation, OperationalWorkService
from alos.security import Principal, Role


@dataclass(slots=True)
class _RunCounters:
    organizations_evaluated: int = 0
    reminders_enqueued: int = 0
    events_claimed: int = 0
    events_delivered: int = 0
    events_retried: int = 0
    events_dead_lettered: int = 0


class WorkerRuntime:
    """Restart-safe scheduler and outbox dispatcher for the shared platform."""

    def __init__(
        self,
        repository: PostgresDispatchRepository,
        operations: OperationalWorkService,
        *,
        worker_name: str,
        instance_id: str,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
        deadline_horizon_minutes: int,
        escalation_interval_minutes: int,
        n8n_client: WebhookClient | None,
    ) -> None:
        self._repository = repository
        self._operations = operations
        self._worker_name = worker_name
        self._instance_id = instance_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._deadline_horizon_minutes = deadline_horizon_minutes
        self._escalation_interval_minutes = escalation_interval_minutes
        self._n8n_client = n8n_client

    def run_once(self) -> WorkerRunSummary:
        worker_run_id = self._repository.start_worker_run(self._worker_name, self._instance_id)
        counters = _RunCounters()
        errors: list[str] = []
        try:
            self._evaluate_deadlines(counters, errors)
            destinations = [OutboxDestination.INTERNAL_NOTIFICATION]
            if self._n8n_client is not None:
                destinations.append(OutboxDestination.N8N_WEBHOOK)
            counters.reminders_enqueued = self._repository.enqueue_pending_reminders(
                tuple(destinations), self._max_attempts
            )
            events = self._repository.claim_events(
                instance_id=self._instance_id,
                batch_size=self._batch_size,
                lease_seconds=self._lease_seconds,
                destinations=tuple(destinations),
            )
            counters.events_claimed = len(events)
            for event in events:
                self._dispatch_event(event, counters, errors)
            status = "PARTIAL" if errors else "COMPLETED"
            return self._finish(worker_run_id, status, counters, errors)
        except Exception as exc:
            errors.append(f"worker:{type(exc).__name__}")
            return self._finish(worker_run_id, "FAILED", counters, errors)

    def _evaluate_deadlines(self, counters: _RunCounters, errors: list[str]) -> None:
        command = DeadlineEvaluation(
            horizon_minutes=self._deadline_horizon_minutes,
            escalation_interval_minutes=self._escalation_interval_minutes,
        )
        for organization_id in self._repository.organization_ids():
            try:
                self._operations.evaluate_deadlines(
                    command, self._system_principal(organization_id)
                )
                counters.organizations_evaluated += 1
            except Exception as exc:
                errors.append(f"deadline:{organization_id}:{type(exc).__name__}")

    def _dispatch_event(
        self,
        event: OutboxEvent,
        counters: _RunCounters,
        errors: list[str],
    ) -> None:
        try:
            if event.destination == OutboxDestination.INTERNAL_NOTIFICATION:
                if event.topic != "reminder.delivery" or event.aggregate_type != "reminder":
                    raise ValueError("unsupported internal notification event")
                self._repository.mark_delivered(event)
            elif event.destination == OutboxDestination.N8N_WEBHOOK:
                if self._n8n_client is None:
                    raise RuntimeError("n8n adapter disabled")
                response = self._n8n_client.send(event)
                self._repository.mark_delivered(event, response.status_code)
            else:
                raise ValueError("unsupported outbox destination")
            counters.events_delivered += 1
        except Exception as exc:
            retry_seconds = min(30 * (2 ** max(event.attempt_count - 1, 0)), 3600)
            result = self._repository.mark_failed(
                event,
                f"{type(exc).__name__}: delivery failed",
                retry_seconds,
            )
            if result == "DEAD_LETTER":
                counters.events_dead_lettered += 1
            else:
                counters.events_retried += 1
            errors.append(f"delivery:{event.outbox_event_id}:{type(exc).__name__}")

    def _finish(
        self,
        worker_run_id: UUID,
        status: str,
        counters: _RunCounters,
        errors: list[str],
    ) -> WorkerRunSummary:
        return self._repository.finish_worker_run(
            worker_run_id,
            status=status,
            organizations_evaluated=counters.organizations_evaluated,
            reminders_enqueued=counters.reminders_enqueued,
            events_claimed=counters.events_claimed,
            events_delivered=counters.events_delivered,
            events_retried=counters.events_retried,
            events_dead_lettered=counters.events_dead_lettered,
            error_summary="; ".join(errors)[:1000] or None,
        )

    @staticmethod
    def _system_principal(organization_id: UUID) -> Principal:
        return Principal(
            user_id=uuid5(NAMESPACE_URL, f"alos-worker:{organization_id}"),
            organization_id=organization_id,
            roles=frozenset({Role.IT_ADMIN}),
            division_codes=frozenset({"IT"}),
        )

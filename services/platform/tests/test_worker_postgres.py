import os
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.integrations.webhooks import WebhookDeliveryError, WebhookResponse
from alos.main import app
from alos.persistence import Database
from alos.persistence.migrations import psycopg_url
from alos.platform.dispatch import PostgresDispatchRepository
from alos.platform.dispatch.service import WorkerRuntime
from alos.security import Principal, Role

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


class _NoopOperations:
    def __init__(self) -> None:
        self.organizations: list[UUID] = []

    def evaluate_deadlines(self, _command: object, principal: Principal) -> None:
        self.organizations.append(principal.organization_id)


class _SuccessfulWebhook:
    def __init__(self) -> None:
        self.event_ids: list[UUID] = []

    def send(self, event: Any) -> WebhookResponse:
        self.event_ids.append(event.outbox_event_id)
        return WebhookResponse(status_code=202)


class _FailingWebhook:
    def send(self, _event: Any) -> WebhookResponse:
        raise WebhookDeliveryError("synthetic delivery failure")


def test_worker_dispatch_is_idempotent_and_dead_letter_is_recoverable() -> None:
    settings = get_settings()
    database_url = psycopg_url(settings.database_url)
    database = Database(settings.database_url)
    repository = PostgresDispatchRepository(database.engine)
    organization_id = uuid4()
    division_id = uuid4()
    work_item_id = uuid4()
    reminder_id = uuid4()
    worker_run_ids: list[UUID] = []
    outbox_ids: list[UUID] = []

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO identity.organizations (organization_id, code, name) VALUES (%s, %s, %s)",
            (organization_id, f"WORKER-{organization_id.hex[:8]}", "Worker Test Tenant"),
        )
        connection.execute(
            """
            INSERT INTO identity.divisions (division_id, organization_id, code, name)
            VALUES (%s, %s, 'IT', 'Information Technology')
            """,
            (division_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO platform.work_items
                (work_item_id, organization_id, division_id, title, work_type,
                 priority, status, correlation_id, created_at, updated_at)
            VALUES (%s, %s, %s, 'Synthetic worker test', 'WORKER_TEST',
                    'NORMAL', 'OPEN', %s, now(), now())
            """,
            (work_item_id, organization_id, division_id, uuid4()),
        )
        connection.execute(
            """
            INSERT INTO platform.reminders
                (reminder_id, organization_id, work_item_id, division_id,
                 reminder_type, escalation_level, status, scheduled_for, created_at)
            VALUES (%s, %s, %s, %s, 'DUE_SOON', 0, 'PENDING', now(), now())
            """,
            (reminder_id, organization_id, work_item_id, division_id),
        )
    baseline_dead_letters = repository.operations_health(organization_id).dead_letter_events

    try:
        operations = _NoopOperations()
        successful_webhook = _SuccessfulWebhook()
        worker = WorkerRuntime(
            repository,
            operations,  # type: ignore[arg-type]
            worker_name="worker-integration-test",
            instance_id="worker-test-success",
            batch_size=10,
            lease_seconds=60,
            max_attempts=3,
            deadline_horizon_minutes=60,
            escalation_interval_minutes=15,
            n8n_client=successful_webhook,
            organization_ids=(organization_id,),
        )
        first = worker.run_once()
        worker_run_ids.append(first.worker_run_id)
        assert first.status == "COMPLETED", first.error_summary
        assert first.reminders_enqueued == 2
        assert first.events_claimed == 2
        assert first.events_delivered == 2
        assert len(successful_webhook.event_ids) == 1

        second = worker.run_once()
        worker_run_ids.append(second.worker_run_id)
        assert second.status == "COMPLETED"
        assert second.reminders_enqueued == 0
        assert second.events_claimed == 0

        with psycopg.connect(database_url) as connection:
            reminder_status = connection.execute(
                "SELECT status FROM platform.reminders WHERE reminder_id = %s",
                (reminder_id,),
            ).fetchone()[0]
            assert reminder_status == "DELIVERED"
            delivered = connection.execute(
                "SELECT outbox_event_id FROM integration.outbox_events "
                "WHERE aggregate_id = %s AND status = 'DELIVERED'",
                (reminder_id,),
            ).fetchall()
            assert len(delivered) == 2
            outbox_ids.extend(row[0] for row in delivered)

        failing_reminder_id = uuid4()
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO platform.reminders
                    (reminder_id, organization_id, work_item_id, division_id,
                     reminder_type, escalation_level, status, scheduled_for, created_at)
                VALUES (%s, %s, %s, %s, 'ESCALATION', 1, 'PENDING', now(), now())
                """,
                (failing_reminder_id, organization_id, work_item_id, division_id),
            )
        failing_worker = WorkerRuntime(
            repository,
            operations,  # type: ignore[arg-type]
            worker_name="worker-integration-test",
            instance_id="worker-test-failure",
            batch_size=10,
            lease_seconds=60,
            max_attempts=1,
            deadline_horizon_minutes=60,
            escalation_interval_minutes=15,
            n8n_client=_FailingWebhook(),
            organization_ids=(organization_id,),
        )
        failed = failing_worker.run_once()
        worker_run_ids.append(failed.worker_run_id)
        assert failed.status == "PARTIAL"
        assert failed.events_dead_lettered == 1
        with psycopg.connect(database_url) as connection:
            dead_letter_id = connection.execute(
                "SELECT outbox_event_id FROM integration.outbox_events "
                "WHERE aggregate_id = %s AND destination = 'N8N_WEBHOOK' "
                "AND status = 'DEAD_LETTER'",
                (failing_reminder_id,),
            ).fetchone()[0]
            all_events = connection.execute(
                "SELECT outbox_event_id FROM integration.outbox_events WHERE aggregate_id = %s",
                (failing_reminder_id,),
            ).fetchall()
            outbox_ids.extend(row[0] for row in all_events)

        principal = Principal(
            user_id=uuid4(),
            organization_id=organization_id,
            roles=frozenset({Role.IT_ADMIN}),
            division_codes=frozenset({"IT"}),
        )
        requeued = repository.requeue_dead_letter(
            dead_letter_id,
            "Mengulang delivery setelah koneksi dipulihkan",
            principal,
        )
        assert requeued.status == "RETRY"
        paused_worker = WorkerRuntime(
            repository,
            operations,  # type: ignore[arg-type]
            worker_name="worker-integration-test",
            instance_id="worker-test-n8n-disabled",
            batch_size=10,
            lease_seconds=60,
            max_attempts=3,
            deadline_horizon_minutes=60,
            escalation_interval_minutes=15,
            n8n_client=None,
            organization_ids=(organization_id,),
        )
        paused = paused_worker.run_once()
        worker_run_ids.append(paused.worker_run_id)
        assert paused.status == "COMPLETED"
        assert paused.events_claimed == 0
        recovery_worker = WorkerRuntime(
            repository,
            operations,  # type: ignore[arg-type]
            worker_name="worker-integration-test",
            instance_id="worker-test-recovery",
            batch_size=10,
            lease_seconds=60,
            max_attempts=3,
            deadline_horizon_minutes=60,
            escalation_interval_minutes=15,
            n8n_client=_SuccessfulWebhook(),
            organization_ids=(organization_id,),
        )
        recovered = recovery_worker.run_once()
        worker_run_ids.append(recovered.worker_run_id)
        assert recovered.status == "COMPLETED"
        assert recovered.events_delivered == 1

        health = repository.operations_health(organization_id)
        assert health.dead_letter_events == baseline_dead_letters
        assert health.last_worker_status == "COMPLETED"
        assert organization_id in operations.organizations
        client = TestClient(app)
        token = client.post(
            "/api/v1/auth/local-token",
            json={
                "user_id": str(uuid4()),
                "organization_id": str(organization_id),
                "roles": ["IT_ADMIN"],
                "division_codes": ["IT"],
            },
        ).json()["access_token"]
        health_response = client.get(
            "/api/v1/system/operations-health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert health_response.status_code == 200
        assert health_response.json()["last_worker_status"] == "COMPLETED"
    finally:
        with psycopg.connect(database_url) as connection:
            if outbox_ids:
                connection.execute(
                    "DELETE FROM audit.entries WHERE entity_id = ANY(%s::text[])",
                    ([str(item) for item in outbox_ids],),
                )
            connection.execute(
                "DELETE FROM integration.outbox_events WHERE aggregate_id IN "
                "(SELECT reminder_id FROM platform.reminders WHERE work_item_id = %s)",
                (work_item_id,),
            )
            connection.execute(
                "DELETE FROM platform.reminders WHERE work_item_id = %s", (work_item_id,)
            )
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s", (work_item_id,)
            )
            if worker_run_ids:
                connection.execute(
                    "DELETE FROM observability.worker_runs WHERE worker_run_id = ANY(%s::uuid[])",
                    (worker_run_ids,),
                )
            connection.execute(
                "DELETE FROM identity.divisions WHERE division_id = %s", (division_id,)
            )
            connection.execute(
                "DELETE FROM identity.organizations WHERE organization_id = %s",
                (organization_id,),
            )

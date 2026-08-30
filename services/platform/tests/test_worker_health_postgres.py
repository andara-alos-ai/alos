import os
from uuid import uuid4

import psycopg
import pytest

from alos.config import get_settings
from alos.entrypoints.worker_health import worker_is_healthy
from alos.persistence import Database
from alos.persistence.migrations import psycopg_url
from alos.platform.dispatch import PostgresDispatchRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_worker_health_requires_recent_database_heartbeat() -> None:
    settings = get_settings()
    repository = PostgresDispatchRepository(Database(settings.database_url).engine)
    worker_name = f"health-test-{uuid4().hex}"
    worker_run_id = repository.start_worker_run(worker_name, "synthetic-instance")
    try:
        repository.finish_worker_run(
            worker_run_id,
            status="COMPLETED",
            organizations_evaluated=0,
            reminders_enqueued=0,
            events_claimed=0,
            events_delivered=0,
            events_retried=0,
            events_dead_lettered=0,
            error_summary=None,
        )

        assert worker_is_healthy(
            settings.database_url,
            worker_name=worker_name,
            max_age_seconds=60,
        )
        assert not worker_is_healthy(
            settings.database_url,
            worker_name="worker-that-does-not-exist",
            max_age_seconds=60,
        )
    finally:
        with psycopg.connect(psycopg_url(settings.database_url)) as connection:
            connection.execute(
                "DELETE FROM observability.worker_runs WHERE worker_run_id = %s",
                (worker_run_id,),
            )

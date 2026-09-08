from unittest.mock import MagicMock

from alos.jobs.scheduler import DurableScheduler
from alos.jobs.worker import DurableWorker


def test_scheduler_heartbeats_even_when_no_report_is_due() -> None:
    scheduler = DurableScheduler("postgresql+psycopg://ignored")
    queue = MagicMock()
    queue.schedule_due_reports.return_value = []
    scheduler._queue = queue

    assert scheduler.tick() == 0

    queue.heartbeat.assert_called_once_with("SCHEDULER", scheduler._scheduler_id)


def test_worker_heartbeats_after_processing_a_job() -> None:
    worker = DurableWorker("postgresql+psycopg://ignored", worker_id="worker-test")
    queue = MagicMock()
    job = MagicMock(job_type="UNKNOWN")
    queue.claim.return_value = job
    queue.fail.return_value = job
    worker._queue = queue

    assert worker.run_once() is job

    queue.fail.assert_called_once_with(job, "HANDLER_NOT_CONFIGURED")
    queue.heartbeat.assert_called_once_with("WORKER", "worker-test")

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading

from alos.config import Settings, get_settings
from alos.integrations.webhooks import N8nWebhookClient, WebhookClient
from alos.persistence import Database
from alos.platform.dispatch import PostgresDispatchRepository
from alos.platform.dispatch.service import WorkerRuntime
from alos.platform.operations import OperationalWorkService, PostgresOperationsRepository

logger = logging.getLogger(__name__)


def build_worker(settings: Settings, instance_id: str | None = None) -> WorkerRuntime:
    database = Database(settings.database_url)
    dispatch_repository = PostgresDispatchRepository(database.engine)
    operations = OperationalWorkService(PostgresOperationsRepository(database.engine))
    n8n_client: WebhookClient | None = None
    if settings.n8n_enabled:
        webhook_url = settings.n8n_webhook_url
        webhook_secret = settings.n8n_webhook_secret_value
        if webhook_url is None or webhook_secret is None:
            raise ValueError("Konfigurasi n8n belum lengkap")
        n8n_client = N8nWebhookClient(
            webhook_url,
            webhook_secret,
            settings.n8n_timeout_seconds,
        )
    resolved_instance_id = instance_id or f"{socket.gethostname()}-{os.getpid()}"
    return WorkerRuntime(
        dispatch_repository,
        operations,
        worker_name="alos-operational-worker",
        instance_id=resolved_instance_id[:160],
        batch_size=settings.worker_batch_size,
        lease_seconds=settings.worker_lease_seconds,
        max_attempts=settings.worker_max_attempts,
        deadline_horizon_minutes=settings.deadline_horizon_minutes,
        escalation_interval_minutes=settings.escalation_interval_minutes,
        n8n_client=n8n_client,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ALOS scheduler dan outbox worker")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="jalankan terus-menerus; default menjalankan satu siklus",
    )
    arguments = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = build_worker(settings)
    if not arguments.loop:
        summary = worker.run_once()
        logger.info("worker cycle completed: %s", summary.model_dump_json())
        if summary.status != "COMPLETED":
            raise SystemExit(1)
        return

    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logger.info("worker loop started")
    while not stop.is_set():
        summary = worker.run_once()
        logger.info("worker cycle completed: %s", summary.model_dump_json())
        stop.wait(settings.worker_poll_seconds)
    logger.info("worker loop stopped")


if __name__ == "__main__":
    main()

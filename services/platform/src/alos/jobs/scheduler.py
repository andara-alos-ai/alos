"""Durable scheduler that converts confirmed PostgreSQL schedules into jobs."""

import os
import socket
import time

from alos.config import get_settings
from alos.jobs.repository import JobQueueRepository


class DurableScheduler:
    def __init__(self, database_url: str, scheduler_id: str | None = None) -> None:
        self._queue = JobQueueRepository(database_url)
        self._scheduler_id = scheduler_id or f"{socket.gethostname()}:{os.getpid()}"

    def tick(self) -> int:
        try:
            reports = self._queue.schedule_due_reports(self._scheduler_id)
            agents = self._queue.schedule_due_agents(self._scheduler_id)
            return len(reports) + len(agents)
        finally:
            # A scheduler with no schedules due is still healthy and should be visible.
            self._queue.heartbeat("SCHEDULER", self._scheduler_id)

    def run_forever(self, poll_seconds: float = 15.0) -> None:
        while True:
            self.tick()
            time.sleep(max(1, min(poll_seconds, 60)))


def main() -> None:
    DurableScheduler(get_settings().database_url).run_forever()


if __name__ == "__main__":
    main()

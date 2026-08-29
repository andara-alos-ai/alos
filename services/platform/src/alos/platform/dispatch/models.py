from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutboxDestination(StrEnum):
    INTERNAL_NOTIFICATION = "INTERNAL_NOTIFICATION"
    N8N_WEBHOOK = "N8N_WEBHOOK"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY = "RETRY"
    DELIVERED = "DELIVERED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


class OutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outbox_event_id: UUID
    organization_id: UUID
    topic: str
    aggregate_type: str
    aggregate_id: UUID
    destination: OutboxDestination
    payload: dict[str, Any]
    status: OutboxStatus
    attempt_count: int
    max_attempts: int
    available_at: datetime
    locked_at: datetime | None
    locked_by: str | None
    last_error: str | None
    response_status: int | None
    delivered_at: datetime | None
    correlation_id: UUID
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class WorkerRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_run_id: UUID
    worker_name: str
    instance_id: str
    status: str
    organizations_evaluated: int
    reminders_enqueued: int
    events_claimed: int
    events_delivered: int
    events_retried: int
    events_dead_lettered: int
    error_summary: str | None
    started_at: datetime
    completed_at: datetime


class OperationsHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_events: int
    retry_events: int
    processing_events: int
    dead_letter_events: int
    oldest_pending_at: datetime | None
    last_worker_status: str | None
    last_worker_started_at: datetime | None
    last_worker_completed_at: datetime | None


class OutboxRequeue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=8, max_length=500)

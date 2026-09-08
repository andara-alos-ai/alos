"""Scoped job queue, notification, worker, and scheduler observability API."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg.rows import dict_row
from pydantic import BaseModel

from alos.config import get_settings
from alos.identity import HumanRole
from alos.jobs.repository import JobQueueError, JobQueueRepository, JobRecord
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1", tags=["jobs-notifications"])


class NotificationRecord(BaseModel):
    notification_id: UUID
    workspace_id: UUID | None
    notification_type: str
    title: str
    body: str
    entity_type: str
    entity_id: UUID
    read_at: datetime | None
    created_at: datetime


class BackgroundServiceStatus(BaseModel):
    worker: str
    scheduler: str
    queued_jobs: int
    failed_jobs: int
    oldest_queued_at: datetime | None


@router.get("/jobs", response_model=list[JobRecord])
def list_jobs(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[JobRecord]:
    return JobQueueRepository(get_settings().database_url).list_jobs(
        actor.organization_id, actor.workspace_ids, limit=limit
    )


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_job(
    job_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> JobRecord:
    repository = JobQueueRepository(get_settings().database_url)
    visible = next(
        (
            item
            for item in repository.list_jobs(actor.organization_id, actor.workspace_ids, limit=200)
            if item.job_id == job_id
        ),
        None,
    )
    privileged = bool(
        {HumanRole.DIRECTOR, HumanRole.IT_ADMIN, HumanRole.AI_ADMIN}.intersection(actor.roles)
    )
    if visible is None or (visible.owner_user_id != actor.user_id and not privileged):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job was not found")
    try:
        return repository.cancel(job_id, actor.organization_id)
    except JobQueueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/notifications", response_model=list[NotificationRecord])
def list_notifications(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    unread_only: bool = False,
) -> list[NotificationRecord]:
    return _StatusRepository(get_settings().database_url).notifications(
        actor, unread_only=unread_only
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationRecord)
def read_notification(
    notification_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> NotificationRecord:
    result = _StatusRepository(get_settings().database_url).mark_read(actor, notification_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="notification was not found"
        )
    return result


@router.get("/system/background-services", response_model=BackgroundServiceStatus)
def background_services(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> BackgroundServiceStatus:
    if not {
        HumanRole.DIRECTOR,
        HumanRole.IT_ADMIN,
        HumanRole.AI_ADMIN,
        HumanRole.IT_LEAD,
    }.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system observability permission required",
        )
    return _StatusRepository(get_settings().database_url).background(actor.organization_id)


class _StatusRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def notifications(
        self, actor: ActorContext, *, unread_only: bool
    ) -> list[NotificationRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT notification_id, workspace_id, notification_type, title, body,
                       entity_type, entity_id, read_at, created_at
                FROM notifications.inbox
                WHERE organization_id = %s AND recipient_user_id = %s
                  AND (workspace_id IS NULL OR workspace_id = ANY(%s))
                  AND (%s = false OR read_at IS NULL)
                ORDER BY created_at DESC LIMIT 100
                """,
                (
                    actor.organization_id,
                    actor.user_id,
                    actor.workspace_ids,
                    unread_only,
                ),
            ).fetchall()
        return [NotificationRecord(**row) for row in rows]

    def mark_read(
        self, actor: ActorContext, notification_id: UUID
    ) -> NotificationRecord | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE notifications.inbox SET read_at = coalesce(read_at, now())
                WHERE notification_id = %s AND organization_id = %s
                  AND recipient_user_id = %s
                  AND (workspace_id IS NULL OR workspace_id = ANY(%s))
                RETURNING notification_id, workspace_id, notification_type, title, body,
                          entity_type, entity_id, read_at, created_at
                """,
                (
                    notification_id,
                    actor.organization_id,
                    actor.user_id,
                    actor.workspace_ids,
                ),
            ).fetchone()
        return NotificationRecord(**row) if row else None

    def background(self, organization_id: UUID) -> BackgroundServiceStatus:
        stale_before = datetime.now(UTC) - timedelta(minutes=2)
        with self._connection() as connection:
            heartbeats = {
                row["service_name"]: row["last_seen_at"]
                for row in connection.execute(
                    "SELECT service_name, last_seen_at FROM jobs.service_heartbeats"
                ).fetchall()
            }
            counts = connection.execute(
                """
                SELECT count(*) FILTER (WHERE status = 'QUEUED') AS queued_jobs,
                       count(*) FILTER (
                           WHERE status = 'FAILED' AND attempts >= max_attempts
                       ) AS failed_jobs,
                       min(created_at) FILTER (WHERE status = 'QUEUED') AS oldest_queued_at
                FROM jobs.queue WHERE organization_id = %s
                """,
                (organization_id,),
            ).fetchone()
        return BackgroundServiceStatus(
            worker=(
                "READY"
                if heartbeats.get("WORKER") and heartbeats["WORKER"] >= stale_before
                else "UNAVAILABLE"
            ),
            scheduler=(
                "READY"
                if heartbeats.get("SCHEDULER") and heartbeats["SCHEDULER"] >= stale_before
                else "UNAVAILABLE"
            ),
            queued_jobs=counts["queued_jobs"] if counts else 0,
            failed_jobs=counts["failed_jobs"] if counts else 0,
            oldest_queued_at=counts["oldest_queued_at"] if counts else None,
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

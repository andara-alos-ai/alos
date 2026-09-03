"""Read-only audit trail queries for authorized ALOS operations users."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from alos.persistence.database import psycopg_url


class AuditEventRecord(BaseModel):
    audit_event_id: UUID
    actor_kind: str
    actor_user_id: UUID | None
    system_actor: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    correlation_id: UUID
    reason: str
    metadata: dict[str, Any]
    occurred_at: datetime


class AuditReader:
    """Append-only evidence is exposed as a read-only, organization-scoped stream."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def list_events(self, organization_id: UUID, *, limit: int = 100) -> list[AuditEventRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("audit listing limit must be between 1 and 500")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT audit_event_id, actor_kind, actor_user_id, system_actor, action, entity_type,
                       entity_id, correlation_id, reason, metadata, occurred_at
                FROM audit.events
                WHERE organization_id = %s
                ORDER BY occurred_at DESC, audit_event_id DESC
                LIMIT %s
                """,
                (organization_id, limit),
            ).fetchall()
        return [AuditEventRecord(**row) for row in rows]

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

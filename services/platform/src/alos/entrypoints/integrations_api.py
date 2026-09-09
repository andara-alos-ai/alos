"""Read-only, scoped integration health. Secrets and configuration writes stay outside the API."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row
from pydantic import BaseModel

from alos.config import get_settings
from alos.identity import HumanRole
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


class IntegrationStatusRecord(BaseModel):
    integration_key: str
    provider: str
    status: Literal["NOT_CONFIGURED", "CONFIGURED", "UNAVAILABLE", "DEGRADED"]
    allowed_hosts: list[str]
    updated_at: datetime


@router.get("/status", response_model=list[IntegrationStatusRecord])
def integration_status(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[IntegrationStatusRecord]:
    observability_roles = {
        HumanRole.DIRECTOR,
        HumanRole.IT_ADMIN,
        HumanRole.AI_ADMIN,
        HumanRole.IT_LEAD,
    }
    if not observability_roles.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="integration observability permission required",
        )
    with _connection(get_settings().database_url) as connection:
        rows = connection.execute(
            """
            SELECT integration_key, provider, status, allowed_hosts, updated_at
            FROM integrations.configurations
            WHERE organization_id = %s
            ORDER BY integration_key
            """,
            (actor.organization_id,),
        ).fetchall()
    return [IntegrationStatusRecord(**row) for row in rows]


@contextmanager
def _connection(database_url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(psycopg_url(database_url), row_factory=dict_row) as connection:
        yield connection

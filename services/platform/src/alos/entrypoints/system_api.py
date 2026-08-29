from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError

from alos.entrypoints.api import PrincipalDependency, SettingsDependency, database_for_url
from alos.platform.dispatch import (
    OperationsHealth,
    OutboxEvent,
    OutboxRequeue,
    PostgresDispatchRepository,
)
from alos.security import Role
from alos.security.authorization import AuthorizationDenied, require_any_role

router = APIRouter()


def dispatch_repository(settings: SettingsDependency) -> PostgresDispatchRepository:
    return PostgresDispatchRepository(database_for_url(settings.database_url).engine)


DispatchRepositoryDependency = Annotated[PostgresDispatchRepository, Depends(dispatch_repository)]


@router.get(
    "/system/operations-health",
    response_model=OperationsHealth,
    tags=["system", "observability"],
)
def operations_health(
    principal: PrincipalDependency,
    repository: DispatchRepositoryDependency,
) -> OperationsHealth:
    try:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return repository.operations_health(principal.organization_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/system/outbox/{outbox_event_id}/requeue",
    response_model=OutboxEvent,
    tags=["system", "observability"],
)
def requeue_dead_letter(
    outbox_event_id: UUID,
    request: OutboxRequeue,
    principal: PrincipalDependency,
    repository: DispatchRepositoryDependency,
) -> OutboxEvent:
    try:
        require_any_role(principal, Role.DIRECTOR, Role.IT_ADMIN)
        return repository.requeue_dead_letter(outbox_event_id, request.reason, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc

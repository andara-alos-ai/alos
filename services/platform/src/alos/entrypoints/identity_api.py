from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.config import Settings, get_settings
from alos.entrypoints.api import current_principal, database_for_url
from alos.platform.identity import IdentityConflict, IdentityService, PostgresIdentityStore
from alos.security import (
    Principal,
    ProjectAssignmentCreate,
    ProjectAssignmentView,
    Role,
    RoleAssignmentCreate,
    RoleAssignmentView,
    UserDirectoryPage,
    UserDirectoryView,
    UserStatus,
    UserStatusUpdate,
)
from alos.security.authorization import AuthorizationDenied

router = APIRouter()


class RevokeAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=8, max_length=500)


def identity_service(settings: Annotated[Settings, Depends(get_settings)]) -> IdentityService:
    engine = database_for_url(settings.database_url).engine
    return IdentityService(PostgresIdentityStore(engine))


PrincipalDependency = Annotated[Principal, Depends(current_principal)]
IdentityServiceDependency = Annotated[IdentityService, Depends(identity_service)]


@router.get("/users", response_model=UserDirectoryPage, tags=["identity"])
def list_users(
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
    role: Role | None = None,
    division_code: Annotated[str | None, Query(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")] = None,
) -> UserDirectoryPage:
    try:
        return service.list_users(
            principal, page, page_size, search, user_status, role, division_code
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get("/users/{user_id}", response_model=UserDirectoryView, tags=["identity"])
def get_user(
    user_id: UUID,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> UserDirectoryView:
    try:
        return service.get_user(user_id, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.patch("/users/{user_id}/status", response_model=UserDirectoryView, tags=["identity"])
def update_user_status(
    user_id: UUID,
    request: UserStatusUpdate,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> UserDirectoryView:
    try:
        return service.update_status(user_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/users/{user_id}/role-assignments",
    response_model=RoleAssignmentView,
    status_code=201,
    tags=["identity"],
)
def add_role_assignment(
    user_id: UUID,
    request: RoleAssignmentCreate,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> RoleAssignmentView:
    try:
        return service.add_role_assignment(user_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Penugasan role aktif sudah ada") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/users/{user_id}/role-assignments/{assignment_id}/revoke",
    status_code=204,
    tags=["identity"],
)
def revoke_role_assignment(
    user_id: UUID,
    assignment_id: UUID,
    request: RevokeAssignmentRequest,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> Response:
    try:
        service.revoke_role_assignment(user_id, assignment_id, request.reason, principal)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/users/{user_id}/project-assignments",
    response_model=ProjectAssignmentView,
    status_code=201,
    tags=["identity"],
)
def add_project_assignment(
    user_id: UUID,
    request: ProjectAssignmentCreate,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> ProjectAssignmentView:
    try:
        return service.add_project_assignment(user_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Penugasan proyek aktif sudah ada") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/users/{user_id}/project-assignments/{assignment_id}/revoke",
    status_code=204,
    tags=["identity"],
)
def revoke_project_assignment(
    user_id: UUID,
    assignment_id: UUID,
    request: RevokeAssignmentRequest,
    principal: PrincipalDependency,
    service: IdentityServiceDependency,
) -> Response:
    try:
        service.revoke_project_assignment(user_id, assignment_id, request.reason, principal)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc

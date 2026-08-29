from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.entrypoints.api import PrincipalDependency, SettingsDependency, database_for_url
from alos.platform.operations import (
    ApprovalClaim,
    ApprovalOperationalView,
    CapaAssignment,
    CapaOperationalView,
    CapaTransition,
    DeadlineEvaluation,
    DeadlineEvaluationResult,
    ExceptionOperationalView,
    ExceptionTransition,
    OperationalWorkService,
    PostgresOperationsRepository,
    ReminderView,
    WorkItemClaim,
    WorkItemDeadlineUpdate,
    WorkItemDelegate,
    WorkItemOperationalView,
    WorkQueueScope,
)
from alos.security.authorization import AuthorizationDenied

router = APIRouter()


def operational_work_service(settings: SettingsDependency) -> OperationalWorkService:
    repository = PostgresOperationsRepository(database_for_url(settings.database_url).engine)
    return OperationalWorkService(repository)


OperationalWorkServiceDependency = Annotated[
    OperationalWorkService, Depends(operational_work_service)
]


def _raise_operational_error(error: Exception) -> NoReturn:
    if isinstance(error, AuthorizationDenied):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, IntegrityError):
        raise HTTPException(status_code=409, detail="Perubahan operasional tidak valid") from error
    if isinstance(error, OperationalError):
        raise HTTPException(status_code=503, detail="Database belum tersedia") from error
    raise error


@router.get(
    "/operational/work-queue",
    response_model=list[WorkItemOperationalView],
    tags=["work-queue"],
)
def list_work_queue(
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
    scope: WorkQueueScope = WorkQueueScope.MINE,
    project_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> tuple[WorkItemOperationalView, ...]:
    try:
        return service.list_work_queue(principal, scope, project_id, limit)
    except (AuthorizationDenied, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/operational/work-items/{work_item_id}/claim",
    response_model=WorkItemOperationalView,
    tags=["work-queue"],
)
def claim_work_item(
    work_item_id: UUID,
    request: WorkItemClaim,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> WorkItemOperationalView:
    try:
        return service.claim_work_item(work_item_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/operational/work-items/{work_item_id}/delegate",
    response_model=WorkItemOperationalView,
    tags=["work-queue"],
)
def delegate_work_item(
    work_item_id: UUID,
    request: WorkItemDelegate,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> WorkItemOperationalView:
    try:
        return service.delegate_work_item(work_item_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/operational/work-items/{work_item_id}/release",
    response_model=WorkItemOperationalView,
    tags=["work-queue"],
)
def release_work_item(
    work_item_id: UUID,
    request: WorkItemClaim,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> WorkItemOperationalView:
    try:
        return service.release_work_item(work_item_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.patch(
    "/operational/work-items/{work_item_id}/deadline",
    response_model=WorkItemOperationalView,
    tags=["work-queue"],
)
def update_work_item_deadline(
    work_item_id: UUID,
    request: WorkItemDeadlineUpdate,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> WorkItemOperationalView:
    try:
        return service.update_deadline(work_item_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/approvals/{approval_request_id}/claim",
    response_model=ApprovalOperationalView,
    tags=["governance", "work-queue"],
)
def claim_approval(
    approval_request_id: UUID,
    request: ApprovalClaim,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> ApprovalOperationalView:
    try:
        return service.claim_approval(approval_request_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/operational/deadlines/evaluate",
    response_model=DeadlineEvaluationResult,
    tags=["work-queue", "governance"],
)
def evaluate_deadlines(
    request: DeadlineEvaluation,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> DeadlineEvaluationResult:
    try:
        return service.evaluate_deadlines(request, principal)
    except (AuthorizationDenied, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.get(
    "/operational/reminders",
    response_model=list[ReminderView],
    tags=["work-queue"],
)
def list_reminders(
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> tuple[ReminderView, ...]:
    try:
        return service.list_reminders(principal, limit)
    except (AuthorizationDenied, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/exceptions/{exception_id}/transition",
    response_model=ExceptionOperationalView,
    tags=["governance"],
)
def transition_exception(
    exception_id: UUID,
    request: ExceptionTransition,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> ExceptionOperationalView:
    try:
        return service.transition_exception(exception_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/capas/{capa_id}/assign",
    response_model=CapaOperationalView,
    tags=["governance"],
)
def assign_capa(
    capa_id: UUID,
    request: CapaAssignment,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> CapaOperationalView:
    try:
        return service.assign_capa(capa_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)


@router.post(
    "/capas/{capa_id}/transition",
    response_model=CapaOperationalView,
    tags=["governance"],
)
def transition_capa(
    capa_id: UUID,
    request: CapaTransition,
    principal: PrincipalDependency,
    service: OperationalWorkServiceDependency,
) -> CapaOperationalView:
    try:
        return service.transition_capa(capa_id, request, principal)
    except (AuthorizationDenied, KeyError, ValueError, IntegrityError, OperationalError) as exc:
        _raise_operational_error(exc)

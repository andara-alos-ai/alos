"""HTTP boundary for capabilities and canonical ALOS operating domains."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from alos.capabilities import (
    CapabilityRecord,
    CapabilityRegistryRepository,
    CapabilityResolution,
    CapabilityResolutionRequest,
    TypedToolRecord,
)
from alos.config import get_settings
from alos.identity import DivisionCode
from alos.operational.models import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalRecord,
    BusinessRecord,
    BusinessRecordRequest,
    EvidenceCreateRequest,
    EvidenceRecord,
    FindingCreateRequest,
    FindingRecord,
    FindingStatusRequest,
    OperationalDashboard,
    ProposedActionCreateRequest,
    ProposedActionExecuteRequest,
    ProposedActionRecord,
    ReportDefinitionRecord,
    ReportDefinitionRequest,
    ReportGenerateRequest,
    ReportRecord,
    ReportScheduleRequest,
    SearchResult,
    TaskCreateRequest,
    TaskList,
    TaskRecord,
    TaskStatusRequest,
)
from alos.operational.repository import (
    OperationalConflict,
    OperationalError,
    OperationalNotFound,
    OperationalRepository,
)
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1", tags=["ALOS operations"])


def get_operational_repository() -> OperationalRepository:
    return OperationalRepository(get_settings().database_url)


def get_capability_repository() -> CapabilityRegistryRepository:
    return CapabilityRegistryRepository(get_settings().database_url)


def correlation_id(
    response: Response,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> UUID:
    try:
        value = UUID(x_correlation_id) if x_correlation_id else uuid4()
    except ValueError:
        value = uuid4()
    response.headers["X-Correlation-ID"] = str(value)
    response.headers["Cache-Control"] = "no-store"
    return value


def operational_http_error(error: OperationalError) -> HTTPException:
    if isinstance(error, OperationalNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, OperationalConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get("/capabilities", response_model=list[CapabilityRecord])
def list_capabilities(
    _: Annotated[ActorContext, Depends(get_current_actor)],
    domain: str | None = None,
    configured_only: bool = False,
) -> list[CapabilityRecord]:
    return get_capability_repository().list_capabilities(
        domain=domain, configured_only=configured_only
    )


@router.post("/capabilities/resolve", response_model=CapabilityResolution)
def resolve_capabilities(
    request: CapabilityResolutionRequest,
    _: Annotated[ActorContext, Depends(get_current_actor)],
) -> CapabilityResolution:
    return get_capability_repository().resolve(request)


@router.get("/tools/catalog", response_model=list[TypedToolRecord])
def list_typed_tools(
    _: Annotated[ActorContext, Depends(get_current_actor)],
    capability_key: str | None = None,
) -> list[TypedToolRecord]:
    return get_capability_repository().list_tools(capability_key=capability_key)


@router.get("/tasks", response_model=TaskList)
def list_tasks(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    task_status: Annotated[str | None, Query(alias="status")] = None,
    project_id: UUID | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TaskList:
    return get_operational_repository().list_tasks(
        actor,
        status=task_status,
        project_id=project_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("/tasks", response_model=TaskRecord, status_code=status.HTTP_201_CREATED)
def create_task(
    request: TaskCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> TaskRecord:
    try:
        return get_operational_repository().create_task(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/tasks/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> TaskRecord:
    try:
        return get_operational_repository().get_task(actor, task_id)
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.patch("/tasks/{task_id}/status", response_model=TaskRecord)
def update_task_status(
    task_id: UUID,
    request: TaskStatusRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> TaskRecord:
    try:
        return get_operational_repository().update_task_status(
            actor, task_id, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/evidence", response_model=list[EvidenceRecord])
def list_evidence(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    task_id: UUID | None = None,
    project_id: UUID | None = None,
) -> list[EvidenceRecord]:
    return get_operational_repository().list_evidence(
        actor, task_id=task_id, project_id=project_id
    )


@router.post("/evidence", response_model=EvidenceRecord, status_code=status.HTTP_201_CREATED)
def create_evidence(
    request: EvidenceCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> EvidenceRecord:
    try:
        return get_operational_repository().create_evidence(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/findings", response_model=list[FindingRecord])
def list_findings(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    finding_status: Annotated[str | None, Query(alias="status")] = None,
    severity: str | None = None,
) -> list[FindingRecord]:
    return get_operational_repository().list_findings(
        actor, status=finding_status, severity=severity
    )


@router.post("/findings", response_model=FindingRecord, status_code=status.HTTP_201_CREATED)
def create_finding(
    request: FindingCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> FindingRecord:
    try:
        return get_operational_repository().create_finding(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.patch("/findings/{finding_id}/status", response_model=FindingRecord)
def update_finding_status(
    finding_id: UUID,
    request: FindingStatusRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> FindingRecord:
    try:
        return get_operational_repository().update_finding_status(
            actor, finding_id, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/proposed-actions", response_model=list[ProposedActionRecord])
def list_proposed_actions(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[ProposedActionRecord]:
    return get_operational_repository().list_proposed_actions(actor)


@router.post(
    "/proposed-actions",
    response_model=ProposedActionRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_proposed_action(
    request: ProposedActionCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ProposedActionRecord:
    try:
        return get_operational_repository().create_proposed_action(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.post(
    "/proposed-actions/{proposed_action_id}/execute",
    response_model=ProposedActionRecord,
)
def execute_proposed_action(
    proposed_action_id: UUID,
    request: ProposedActionExecuteRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ProposedActionRecord:
    try:
        return get_operational_repository().execute_proposed_action(
            actor,
            proposed_action_id,
            request,
            correlation_id=correlation,
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/approvals", response_model=list[ApprovalRecord])
def list_approvals(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    approval_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[ApprovalRecord]:
    return get_operational_repository().list_approvals(actor, status=approval_status)


@router.post("/approvals", response_model=ApprovalRecord, status_code=status.HTTP_201_CREATED)
def create_approval(
    request: ApprovalCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ApprovalRecord:
    try:
        return get_operational_repository().create_approval(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.post("/approvals/{approval_request_id}/decision", response_model=ApprovalRecord)
def decide_approval(
    approval_request_id: UUID,
    request: ApprovalDecisionRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ApprovalRecord:
    try:
        return get_operational_repository().decide_approval(
            actor, approval_request_id, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/report-definitions", response_model=list[ReportDefinitionRecord])
def list_report_definitions(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[ReportDefinitionRecord]:
    return get_operational_repository().list_report_definitions(actor)


@router.post(
    "/report-definitions",
    response_model=ReportDefinitionRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_report_definition(
    request: ReportDefinitionRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ReportDefinitionRecord:
    try:
        return get_operational_repository().create_report_definition(
            actor, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.put(
    "/report-definitions/{report_definition_id}/schedule",
    response_model=ReportDefinitionRecord,
)
def configure_report_schedule(
    report_definition_id: UUID,
    request: ReportScheduleRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ReportDefinitionRecord:
    try:
        return get_operational_repository().configure_report_schedule(
            actor, report_definition_id, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/reports", response_model=list[ReportRecord])
def list_reports(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[ReportRecord]:
    return get_operational_repository().list_reports(actor)


@router.post("/report-definitions/{report_definition_id}/generate", response_model=ReportRecord)
def generate_report(
    report_definition_id: UUID,
    request: ReportGenerateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> ReportRecord:
    try:
        return get_operational_repository().generate_report(
            actor, report_definition_id, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/divisions/{division_code}/records", response_model=list[BusinessRecord])
def list_division_records(
    division_code: DivisionCode,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    record_type: str | None = None,
) -> list[BusinessRecord]:
    return get_operational_repository().list_business_records(
        actor, division_code, record_type=record_type
    )


@router.post(
    "/divisions/{division_code}/records",
    response_model=BusinessRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_division_record(
    division_code: DivisionCode,
    request: BusinessRecordRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> BusinessRecord:
    try:
        return get_operational_repository().create_business_record(
            actor, division_code, request, correlation_id=correlation
        )
    except OperationalError as error:
        raise operational_http_error(error) from error


@router.get("/search", response_model=list[SearchResult])
def global_search(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    query: Annotated[str, Query(alias="q", min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[SearchResult]:
    return get_operational_repository().global_search(actor, query, limit=limit)


@router.get("/dashboard/operational", response_model=OperationalDashboard)
def operational_dashboard(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> OperationalDashboard:
    return get_operational_repository().dashboard(actor)

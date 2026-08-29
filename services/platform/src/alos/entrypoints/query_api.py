from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from alos.config import Settings, get_settings
from alos.entrypoints.api import current_principal, database_for_url
from alos.persistence.query_database import PostgresQueryStore
from alos.platform.query_service import OperationalQueryService
from alos.platform.read_models import (
    AgentRunRead,
    ApprovalRead,
    AuditEntryRead,
    BudgetRead,
    CapaRead,
    DocumentRead,
    EvidenceRead,
    ExceptionRead,
    ExecutiveBriefRead,
    KpiSnapshotRead,
    LeadRead,
    LegalCaseRead,
    Page,
    PageRequest,
    PaymentRequestRead,
    PersonnelChecklistRead,
    RecruitmentRequestRead,
    SalesInteractionRead,
    SiteEvidenceRead,
    SortOrder,
    TransitionEventRead,
    WorkflowRunRead,
    WorkItemRead,
)
from alos.security import Principal
from alos.security.authorization import AuthorizationDenied

router = APIRouter()


def page_request(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
    status: Annotated[str | None, Query(min_length=2, max_length=40)] = None,
    project_id: UUID | None = None,
    sort_by: Annotated[str, Query(min_length=2, max_length=40)] = "created_at",
    sort_order: SortOrder = SortOrder.DESC,
) -> PageRequest:
    return PageRequest(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        project_id=project_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )


PageDependency = Annotated[PageRequest, Depends(page_request)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def query_service(settings: Annotated[Settings, Depends(get_settings)]) -> OperationalQueryService:
    engine = database_for_url(settings.database_url).engine
    return OperationalQueryService(PostgresQueryStore(engine))


QueryServiceDependency = Annotated[OperationalQueryService, Depends(query_service)]


def _list[ReadModelT: BaseModel](
    service: OperationalQueryService,
    resource: str,
    model: type[ReadModelT],
    request: PageRequest,
    principal: Principal,
    extra_conditions: dict[str, object] | None = None,
) -> Page[ReadModelT]:
    try:
        return service.list_records(
            resource, model, request, principal, extra_conditions=extra_conditions
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


def _get[ReadModelT: BaseModel](
    service: OperationalQueryService,
    resource: str,
    model: type[ReadModelT],
    record_id: UUID,
    principal: Principal,
) -> ReadModelT:
    try:
        return service.get_record(resource, model, record_id, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get(
    "/operational/work-items",
    response_model=Page[WorkItemRead],
    tags=["operational-query"],
)
def list_work_items(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[WorkItemRead]:
    return _list(service, "work_items", WorkItemRead, request, principal)


@router.get("/operational/work-items/{work_item_id}", tags=["operational-query"])
def get_work_item(
    work_item_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> WorkItemRead:
    return _get(service, "work_items", WorkItemRead, work_item_id, principal)


@router.get("/leads", response_model=Page[LeadRead], tags=["sales", "operational-query"])
def list_leads(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[LeadRead]:
    return _list(service, "leads", LeadRead, request, principal)


@router.get("/leads/{lead_id}", tags=["sales", "operational-query"])
def get_lead(
    lead_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> LeadRead:
    return _get(service, "leads", LeadRead, lead_id, principal)


@router.get(
    "/leads/{lead_id}/interactions",
    response_model=Page[SalesInteractionRead],
    tags=["sales", "operational-query"],
)
def list_lead_interactions(
    lead_id: UUID,
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[SalesInteractionRead]:
    return _list(
        service,
        "sales_interactions",
        SalesInteractionRead,
        request,
        principal,
        {"lead_id": lead_id},
    )


@router.get(
    "/finance/budgets",
    response_model=Page[BudgetRead],
    tags=["finance", "operational-query"],
)
def list_budgets(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[BudgetRead]:
    return _list(service, "budgets", BudgetRead, request, principal)


@router.get("/finance/budgets/{budget_id}", tags=["finance", "operational-query"])
def get_budget(
    budget_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> BudgetRead:
    return _get(service, "budgets", BudgetRead, budget_id, principal)


@router.get(
    "/finance/payment-requests",
    response_model=Page[PaymentRequestRead],
    tags=["finance", "operational-query"],
)
def list_payment_requests(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[PaymentRequestRead]:
    return _list(service, "payment_requests", PaymentRequestRead, request, principal)


@router.get(
    "/finance/payment-requests/{payment_request_id}",
    tags=["finance", "operational-query"],
)
def get_payment_request(
    payment_request_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> PaymentRequestRead:
    return _get(service, "payment_requests", PaymentRequestRead, payment_request_id, principal)


@router.get(
    "/property/site-evidence",
    response_model=Page[SiteEvidenceRead],
    tags=["property", "operational-query"],
)
def list_site_evidence(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[SiteEvidenceRead]:
    return _list(service, "site_evidence", SiteEvidenceRead, request, principal)


@router.get(
    "/property/site-evidence/{site_evidence_id}",
    tags=["property", "operational-query"],
)
def get_site_evidence(
    site_evidence_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> SiteEvidenceRead:
    return _get(service, "site_evidence", SiteEvidenceRead, site_evidence_id, principal)


@router.get(
    "/kpi-snapshots",
    response_model=Page[KpiSnapshotRead],
    tags=["kpi", "operational-query"],
)
def list_kpi_snapshots(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[KpiSnapshotRead]:
    return _list(service, "kpi_snapshots", KpiSnapshotRead, request, principal)


@router.get("/kpi-snapshots/{snapshot_id}", tags=["kpi", "operational-query"])
def get_kpi_snapshot(
    snapshot_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> KpiSnapshotRead:
    return _get(service, "kpi_snapshots", KpiSnapshotRead, snapshot_id, principal)


@router.get(
    "/legal/cases",
    response_model=Page[LegalCaseRead],
    tags=["legal", "operational-query"],
)
def list_legal_cases(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[LegalCaseRead]:
    return _list(service, "legal_cases", LegalCaseRead, request, principal)


@router.get("/legal/cases/{legal_case_id}", tags=["legal", "operational-query"])
def get_legal_case(
    legal_case_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> LegalCaseRead:
    return _get(service, "legal_cases", LegalCaseRead, legal_case_id, principal)


@router.get(
    "/hr/recruitment-requests",
    response_model=Page[RecruitmentRequestRead],
    tags=["hr", "operational-query"],
)
def list_recruitment_requests(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[RecruitmentRequestRead]:
    return _list(service, "recruitment_requests", RecruitmentRequestRead, request, principal)


@router.get(
    "/hr/recruitment-requests/{recruitment_request_id}",
    tags=["hr", "operational-query"],
)
def get_recruitment_request(
    recruitment_request_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> RecruitmentRequestRead:
    return _get(
        service,
        "recruitment_requests",
        RecruitmentRequestRead,
        recruitment_request_id,
        principal,
    )


@router.get(
    "/hr/recruitment-requests/{recruitment_request_id}/personnel-checklist",
    tags=["hr", "operational-query"],
)
def get_personnel_checklist(
    recruitment_request_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> PersonnelChecklistRead:
    try:
        return service.get_personnel_checklist(recruitment_request_id, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get(
    "/documents", response_model=Page[DocumentRead], tags=["documents", "operational-query"]
)
def list_documents(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[DocumentRead]:
    return _list(service, "documents", DocumentRead, request, principal)


@router.get("/documents/{document_id}", tags=["documents", "operational-query"])
def get_document(
    document_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> DocumentRead:
    return _get(service, "documents", DocumentRead, document_id, principal)


@router.get("/evidence", response_model=Page[EvidenceRead], tags=["evidence", "operational-query"])
def list_evidence(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[EvidenceRead]:
    return _list(service, "evidence", EvidenceRead, request, principal)


@router.get("/evidence/{evidence_id}", tags=["evidence", "operational-query"])
def get_evidence(
    evidence_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> EvidenceRead:
    return _get(service, "evidence", EvidenceRead, evidence_id, principal)


@router.get(
    "/approvals", response_model=Page[ApprovalRead], tags=["governance", "operational-query"]
)
def list_approvals(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[ApprovalRead]:
    return _list(service, "approvals", ApprovalRead, request, principal)


@router.get("/approvals/{approval_id}", tags=["governance", "operational-query"])
def get_approval(
    approval_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> ApprovalRead:
    return _get(service, "approvals", ApprovalRead, approval_id, principal)


@router.get(
    "/exceptions", response_model=Page[ExceptionRead], tags=["governance", "operational-query"]
)
def list_exceptions(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[ExceptionRead]:
    return _list(service, "exceptions", ExceptionRead, request, principal)


@router.get("/exceptions/{exception_id}", tags=["governance", "operational-query"])
def get_exception(
    exception_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> ExceptionRead:
    return _get(service, "exceptions", ExceptionRead, exception_id, principal)


@router.get("/capas", response_model=Page[CapaRead], tags=["governance", "operational-query"])
def list_capas(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[CapaRead]:
    return _list(service, "capas", CapaRead, request, principal)


@router.get("/capas/{capa_id}", tags=["governance", "operational-query"])
def get_capa(
    capa_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> CapaRead:
    return _get(service, "capas", CapaRead, capa_id, principal)


@router.get(
    "/executive/briefs",
    response_model=Page[ExecutiveBriefRead],
    tags=["executive", "operational-query"],
)
def list_executive_briefs(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[ExecutiveBriefRead]:
    return _list(service, "executive_briefs", ExecutiveBriefRead, request, principal)


@router.get("/executive/briefs/{brief_id}", tags=["executive", "operational-query"])
def get_executive_brief(
    brief_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> ExecutiveBriefRead:
    return _get(service, "executive_briefs", ExecutiveBriefRead, brief_id, principal)


@router.get(
    "/workflow-runs",
    response_model=Page[WorkflowRunRead],
    tags=["workflow", "operational-query"],
)
def list_workflow_runs(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[WorkflowRunRead]:
    return _list(service, "workflow_runs", WorkflowRunRead, request, principal)


@router.get("/workflow-runs/{workflow_run_id}", tags=["workflow", "operational-query"])
def get_workflow_run(
    workflow_run_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> WorkflowRunRead:
    return _get(service, "workflow_runs", WorkflowRunRead, workflow_run_id, principal)


@router.get(
    "/workflow-runs/{workflow_run_id}/transitions",
    response_model=Page[TransitionEventRead],
    tags=["workflow", "operational-query"],
)
def list_workflow_transitions(
    workflow_run_id: UUID,
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[TransitionEventRead]:
    return _list(
        service,
        "transition_events",
        TransitionEventRead,
        request,
        principal,
        {"workflow_run_id": workflow_run_id},
    )


@router.get("/agent-runs", response_model=Page[AgentRunRead], tags=["agents", "operational-query"])
def list_agent_runs(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[AgentRunRead]:
    return _list(service, "agent_runs", AgentRunRead, request, principal)


@router.get("/agent-runs/{agent_run_id}", tags=["agents", "operational-query"])
def get_agent_run(
    agent_run_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> AgentRunRead:
    return _get(service, "agent_runs", AgentRunRead, agent_run_id, principal)


@router.get(
    "/audit-entries",
    response_model=Page[AuditEntryRead],
    tags=["audit", "operational-query"],
)
def list_audit_entries(
    request: PageDependency,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> Page[AuditEntryRead]:
    return _list(service, "audit_entries", AuditEntryRead, request, principal)


@router.get("/audit-entries/{audit_entry_id}", tags=["audit", "operational-query"])
def get_audit_entry(
    audit_entry_id: UUID,
    principal: PrincipalDependency,
    service: QueryServiceDependency,
) -> AuditEntryRead:
    return _get(service, "audit_entries", AuditEntryRead, audit_entry_id, principal)

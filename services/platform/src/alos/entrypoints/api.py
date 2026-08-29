from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.agents.contract import AgentDefinition
from alos.agents.registry import AgentRegistry
from alos.agents.runtime import (
    AgentExecutionPlan,
    AgentRunRequest,
    RuntimePolicyViolation,
    SharedAgentRuntime,
)
from alos.config import Settings, get_settings
from alos.persistence import Database, PostgresOperationalStore
from alos.platform import (
    ApprovalDecisionCreate,
    ApprovalRequestCreate,
    ApprovalRequestView,
    BudgetCreate,
    BudgetView,
    CapaCreate,
    CapaView,
    DocumentCreate,
    DocumentView,
    EvidenceCreate,
    EvidenceView,
    ExceptionCreate,
    ExceptionView,
    ExecutiveBriefCreate,
    ExecutiveBriefResult,
    ExecutiveBriefReviewCreate,
    FinanceWorkflowResult,
    LeadIntake,
    LeadIntakeResult,
    LegalReviewCreate,
    LegalSubmissionCreate,
    LegalWorkflowResult,
    PaymentDecisionCreate,
    PaymentRecordCreate,
    PaymentRequestCreate,
    PaymentRequestView,
    ProjectCreate,
    ProjectView,
    PropertyReviewCreate,
    PropertyWorkflowResult,
    ReconciliationCreate,
    RecruitmentDecisionCreate,
    RecruitmentRequestCreate,
    RecruitmentWorkflowResult,
    SalesAssignment,
    SalesInteraction,
    SiteEvidenceCreate,
    WorkflowActionResult,
    WorkItemView,
)
from alos.platform.service import OperationsService
from alos.security import (
    AuthenticationError,
    Principal,
    Role,
    TokenCodec,
    UserCreate,
    UserView,
)
from alos.security.authorization import AuthorizationDenied
from alos.tools import ToolRegistry
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


SettingsDependency = Annotated[Settings, Depends(get_settings)]


@lru_cache(maxsize=4)
def agent_registry_for_root(definitions_root: Path) -> AgentRegistry:
    registry = AgentRegistry(definitions_root)
    registry.load_core()
    return registry


def agent_registry(settings: SettingsDependency) -> AgentRegistry:
    return agent_registry_for_root(settings.definitions_root)


@lru_cache(maxsize=4)
def tool_registry_for_root(definitions_root: Path) -> ToolRegistry:
    registry = ToolRegistry(definitions_root)
    registry.load_all()
    return registry


def tool_registry(settings: SettingsDependency) -> ToolRegistry:
    return tool_registry_for_root(settings.definitions_root)


AgentRegistryDependency = Annotated[AgentRegistry, Depends(agent_registry)]
ToolRegistryDependency = Annotated[ToolRegistry, Depends(tool_registry)]


def workflow_registry(
    settings: SettingsDependency,
    agents: AgentRegistryDependency,
    tools: ToolRegistryDependency,
) -> WorkflowRegistry:
    return WorkflowRegistry(settings.definitions_root, agents, tools)


WorkflowRegistryDependency = Annotated[WorkflowRegistry, Depends(workflow_registry)]


def shared_runtime(
    registry: AgentRegistryDependency, tools: ToolRegistryDependency
) -> SharedAgentRuntime:
    return SharedAgentRuntime(registry, tools)


SharedRuntimeDependency = Annotated[SharedAgentRuntime, Depends(shared_runtime)]


@lru_cache
def database_for_url(url: str) -> Database:
    return Database(url)


def operational_store(settings: SettingsDependency) -> PostgresOperationalStore:
    return PostgresOperationalStore(database_for_url(settings.database_url))


OperationalStoreDependency = Annotated[PostgresOperationalStore, Depends(operational_store)]


def validate_released_principal(principal: Principal, settings: Settings) -> None:
    """Validate non-local token claims against active identity assignments."""
    if settings.environment in {"local", "test"}:
        return
    with database_for_url(settings.database_url).engine.connect() as connection:
        role_rows = connection.execute(
            text(
                """
                SELECT ra.role_code, d.code AS division_code
                FROM identity.users u
                JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                WHERE u.user_id = :user_id
                  AND u.organization_id = :organization_id
                  AND u.status = 'ACTIVE'
                  AND ra.valid_from <= now()
                  AND (ra.valid_until IS NULL OR ra.valid_until > now())
                  AND (d.organization_id IS NULL OR d.organization_id = :organization_id)
                """
            ),
            {
                "user_id": principal.user_id,
                "organization_id": principal.organization_id,
            },
        ).mappings()
        assignments = tuple(role_rows)
        project_rows = connection.execute(
            text(
                """
                SELECT pa.project_id
                FROM identity.project_assignments pa
                JOIN identity.users u ON u.user_id = pa.user_id
                JOIN platform.projects p ON p.project_id = pa.project_id
                WHERE pa.user_id = :user_id
                  AND u.organization_id = :organization_id
                  AND u.status = 'ACTIVE'
                  AND p.organization_id = :organization_id
                  AND pa.valid_from <= now()
                  AND (pa.valid_until IS NULL OR pa.valid_until > now())
                """
            ),
            {
                "user_id": principal.user_id,
                "organization_id": principal.organization_id,
            },
        ).scalars()
        assigned_projects = frozenset(project_rows)
    assigned_roles = {row["role_code"] for row in assignments}
    assigned_divisions = {
        row["division_code"] for row in assignments if row["division_code"] is not None
    }
    if not assignments or not {role.value for role in principal.roles}.issubset(assigned_roles):
        raise AuthenticationError("Akun atau penugasan role tidak aktif")
    if not principal.division_codes.issubset(assigned_divisions):
        raise AuthenticationError("Konteks divisi token tidak valid")
    if not principal.project_ids.issubset(assigned_projects):
        raise AuthenticationError("Konteks proyek token tidak valid")


def current_principal(
    settings: SettingsDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token diperlukan")
    codec = TokenCodec(
        settings.auth_signing_secret.get_secret_value(),
        settings.auth_issuer,
        settings.auth_audience,
    )
    try:
        principal = codec.verify(credentials.credentials)
        validate_released_principal(principal, settings)
        return principal
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Layanan identitas belum tersedia") from exc


PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def operations_service(
    store: OperationalStoreDependency,
    workflows: WorkflowRegistryDependency,
    runtime: SharedRuntimeDependency,
) -> OperationsService:
    return OperationsService(store, workflows, runtime)


OperationsDependency = Annotated[OperationsService, Depends(operations_service)]


class LocalTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    organization_id: UUID
    roles: frozenset[Role] = Field(min_length=1)
    division_codes: frozenset[str] = Field(default_factory=frozenset)
    project_ids: frozenset[UUID] = Field(default_factory=frozenset)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth token type, not a credential.
    expires_in: int


@router.get("/health", tags=["system"])
def health(settings: SettingsDependency) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.application_name,
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
    }


@router.post("/auth/local-token", response_model=TokenResponse, tags=["authentication"])
def issue_local_token(request: LocalTokenRequest, settings: SettingsDependency) -> TokenResponse:
    if settings.environment not in {"local", "test"}:
        raise HTTPException(status_code=404, detail="Endpoint tidak tersedia")
    principal = Principal.model_validate(request.model_dump())
    codec = TokenCodec(
        settings.auth_signing_secret.get_secret_value(),
        settings.auth_issuer,
        settings.auth_audience,
    )
    return TokenResponse(
        access_token=codec.issue(principal, settings.auth_token_ttl_seconds),
        expires_in=settings.auth_token_ttl_seconds,
    )


@router.get("/auth/me", response_model=Principal, tags=["authentication"])
def authenticated_principal(principal: PrincipalDependency) -> Principal:
    """Return the server-validated identity context for the current bearer token."""
    return principal


@router.post("/projects", response_model=ProjectView, status_code=201, tags=["projects"])
def create_project(
    request: ProjectCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> ProjectView:
    try:
        return service.create_project(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Kode proyek sudah digunakan") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/users", response_model=UserView, status_code=201, tags=["identity"])
def create_user(
    request: UserCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> UserView:
    try:
        return service.create_user(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email pengguna sudah digunakan") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get("/projects", response_model=list[ProjectView], tags=["projects"])
def list_projects(
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> tuple[ProjectView, ...]:
    try:
        return service.list_projects(principal)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/finance/budgets", response_model=BudgetView, status_code=201, tags=["finance"])
def create_budget(
    request: BudgetCreate, principal: PrincipalDependency, service: OperationsDependency
) -> BudgetView:
    try:
        return service.create_budget(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Kode budget sudah digunakan") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/finance/payment-requests",
    response_model=PaymentRequestView,
    status_code=201,
    tags=["finance", "workflow"],
)
def create_payment_request(
    request: PaymentRequestCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> PaymentRequestView:
    try:
        return service.create_payment_request(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Payment request duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/finance/payment-requests/{payment_request_id}/decision",
    response_model=FinanceWorkflowResult,
    tags=["finance", "workflow"],
)
def decide_payment(
    payment_request_id: UUID,
    request: PaymentDecisionCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> FinanceWorkflowResult:
    try:
        return service.decide_payment(payment_request_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Keputusan approval duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/finance/payment-requests/{payment_request_id}/payment",
    response_model=FinanceWorkflowResult,
    tags=["finance", "workflow"],
)
def record_payment(
    payment_request_id: UUID,
    request: PaymentRecordCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> FinanceWorkflowResult:
    try:
        return service.record_payment(payment_request_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Pembayaran duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/finance/payment-requests/{payment_request_id}/reconciliation",
    response_model=FinanceWorkflowResult,
    tags=["finance", "workflow"],
)
def reconcile_payment(
    payment_request_id: UUID,
    request: ReconciliationCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
) -> FinanceWorkflowResult:
    try:
        return service.reconcile_payment(payment_request_id, request, principal, idempotency_key)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Rekonsiliasi duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/property/site-evidence",
    response_model=PropertyWorkflowResult,
    status_code=201,
    tags=["property", "workflow"],
)
def submit_site_evidence(
    request: SiteEvidenceCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> PropertyWorkflowResult:
    try:
        return service.submit_site_evidence(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Bukti lapangan duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/property/site-evidence/{site_evidence_id}/review",
    response_model=PropertyWorkflowResult,
    tags=["property", "workflow"],
)
def review_site_evidence(
    site_evidence_id: UUID,
    request: PropertyReviewCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
) -> PropertyWorkflowResult:
    try:
        return service.review_site_evidence(site_evidence_id, request, principal, idempotency_key)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Review bukti lapangan duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/legal/documents",
    response_model=LegalWorkflowResult,
    status_code=201,
    tags=["legal", "workflow"],
)
def submit_legal_document(
    request: LegalSubmissionCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> LegalWorkflowResult:
    try:
        return service.submit_legal_document(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Dokumen Legal duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/legal/documents/{legal_case_id}/review",
    response_model=LegalWorkflowResult,
    tags=["legal", "workflow"],
)
def review_legal_document(
    legal_case_id: UUID,
    request: LegalReviewCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> LegalWorkflowResult:
    try:
        return service.review_legal_document(legal_case_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Review Legal duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/hr/recruitment-requests",
    response_model=RecruitmentWorkflowResult,
    status_code=201,
    tags=["hr", "workflow"],
)
def submit_recruitment_request(
    request: RecruitmentRequestCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> RecruitmentWorkflowResult:
    try:
        return service.submit_recruitment_request(
            request, principal, idempotency_key, correlation_id
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Permintaan rekrutmen duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/hr/recruitment-requests/{recruitment_request_id}/decision",
    response_model=RecruitmentWorkflowResult,
    tags=["hr", "workflow"],
)
def decide_recruitment(
    recruitment_request_id: UUID,
    request: RecruitmentDecisionCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
) -> RecruitmentWorkflowResult:
    try:
        return service.decide_recruitment(
            recruitment_request_id, request, principal, idempotency_key
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Keputusan rekrutmen duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/executive/briefs",
    response_model=ExecutiveBriefResult,
    status_code=201,
    tags=["ai-executive", "workflow"],
)
def generate_executive_brief(
    request: ExecutiveBriefCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> ExecutiveBriefResult:
    try:
        return service.generate_executive_brief(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimePolicyViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Executive Brief duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/executive/briefs/{executive_brief_id}/review",
    response_model=ExecutiveBriefResult,
    tags=["ai-executive", "workflow"],
)
def review_executive_brief(
    executive_brief_id: UUID,
    request: ExecutiveBriefReviewCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> ExecutiveBriefResult:
    try:
        return service.review_executive_brief(executive_brief_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Review Executive Brief duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/documents",
    response_model=DocumentView,
    status_code=201,
    tags=["documents"],
    deprecated=True,
)
def create_document(
    request: DocumentCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
    settings: SettingsDependency,
) -> DocumentView:
    try:
        if settings.environment not in {"local", "test"}:
            raise HTTPException(
                status_code=409,
                detail="Endpoint metadata-only dinonaktifkan; gunakan /documents/upload",
            )
        return service.create_document(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Dokumen atau hash sudah digunakan") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/evidence", response_model=EvidenceView, status_code=201, tags=["evidence"])
def create_evidence(
    request: EvidenceCreate, principal: PrincipalDependency, service: OperationsDependency
) -> EvidenceView:
    try:
        return service.create_evidence(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Evidence duplikat atau tidak valid") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/approvals", response_model=ApprovalRequestView, status_code=201, tags=["governance"])
def request_approval(
    request: ApprovalRequestCreate, principal: PrincipalDependency, service: OperationsDependency
) -> ApprovalRequestView:
    try:
        return service.request_approval(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Approval tidak dapat dibuat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/approvals/{approval_request_id}/decision",
    response_model=ApprovalRequestView,
    tags=["governance"],
)
def decide_approval(
    approval_request_id: UUID,
    request: ApprovalDecisionCreate,
    principal: PrincipalDependency,
    service: OperationsDependency,
) -> ApprovalRequestView:
    try:
        return service.decide_approval(approval_request_id, request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Keputusan approval duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/exceptions", response_model=ExceptionView, status_code=201, tags=["governance"])
def create_exception(
    request: ExceptionCreate, principal: PrincipalDependency, service: OperationsDependency
) -> ExceptionView:
    try:
        return service.create_exception(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/capas", response_model=CapaView, status_code=201, tags=["governance"])
def create_capa(
    request: CapaCreate, principal: PrincipalDependency, service: OperationsDependency
) -> CapaView:
    try:
        return service.create_capa(request, principal)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post("/leads", response_model=LeadIntakeResult, status_code=201, tags=["sales"])
def intake_lead(
    request: LeadIntake,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> LeadIntakeResult:
    try:
        return service.intake_lead(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Permintaan duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get("/work-items", response_model=list[WorkItemView], tags=["work-queue"])
def list_work_items(
    principal: PrincipalDependency,
    service: OperationsDependency,
    project_id: Annotated[UUID | None, Query()] = None,
) -> tuple[WorkItemView, ...]:
    try:
        return service.list_work_items(principal, project_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/workflow-runs/{workflow_run_id}/sales-assignment",
    response_model=WorkflowActionResult,
    tags=["sales", "workflow"],
)
def assign_sales_pic(
    workflow_run_id: UUID,
    request: SalesAssignment,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
) -> WorkflowActionResult:
    try:
        return service.assign_sales_pic(workflow_run_id, request, principal, idempotency_key)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Penugasan duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/workflow-runs/{workflow_run_id}/interactions",
    response_model=WorkflowActionResult,
    tags=["sales", "workflow"],
)
def record_sales_interaction(
    workflow_run_id: UUID,
    request: SalesInteraction,
    principal: PrincipalDependency,
    service: OperationsDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)],
) -> WorkflowActionResult:
    try:
        return service.record_sales_interaction(
            workflow_run_id, request, principal, idempotency_key
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Interaksi duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get("/agents", response_model=list[AgentDefinition], tags=["agent-registry"])
def list_agents(
    principal: PrincipalDependency, registry: AgentRegistryDependency
) -> tuple[AgentDefinition, ...]:
    return registry.load_all()


@router.get("/agents/{agent_id}", response_model=AgentDefinition, tags=["agent-registry"])
def get_agent(
    agent_id: str,
    principal: PrincipalDependency,
    registry: AgentRegistryDependency,
    version: Annotated[str | None, Query(pattern=r"^\d+\.\d+\.\d+$")] = None,
) -> AgentDefinition:
    try:
        return registry.get(agent_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent atau versi tidak ditemukan") from exc


@router.get("/workflows", response_model=list[WorkflowDefinition], tags=["workflow"])
def list_workflows(
    principal: PrincipalDependency,
    registry: WorkflowRegistryDependency,
) -> tuple[WorkflowDefinition, ...]:
    return registry.load_all()


@router.post(
    "/agent-runs/prepare",
    response_model=AgentExecutionPlan,
    status_code=201,
    tags=["shared-agent-runtime"],
)
def prepare_agent_run(
    request: AgentRunRequest,
    principal: PrincipalDependency,
    runtime: SharedRuntimeDependency,
) -> AgentExecutionPlan:
    try:
        if not principal.has_any_role(Role.IT_ADMIN):
            raise AuthorizationDenied("Endpoint runtime diagnostic hanya untuk IT Admin")
        return runtime.prepare(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent atau versi tidak ditemukan") from exc
    except RuntimePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
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
    LeadIntake,
    LeadIntakeResult,
    ProjectCreate,
    ProjectView,
    SalesAssignment,
    SalesInteraction,
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
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def agent_registry(settings: SettingsDependency) -> AgentRegistry:
    return AgentRegistry(settings.definitions_root)


def workflow_registry(settings: SettingsDependency) -> WorkflowRegistry:
    return WorkflowRegistry(settings.definitions_root)


AgentRegistryDependency = Annotated[AgentRegistry, Depends(agent_registry)]
WorkflowRegistryDependency = Annotated[WorkflowRegistry, Depends(workflow_registry)]


def shared_runtime(registry: AgentRegistryDependency) -> SharedAgentRuntime:
    return SharedAgentRuntime(registry)


SharedRuntimeDependency = Annotated[SharedAgentRuntime, Depends(shared_runtime)]


@lru_cache
def database_for_url(url: str) -> Database:
    return Database(url)


def operational_store(settings: SettingsDependency) -> PostgresOperationalStore:
    return PostgresOperationalStore(database_for_url(settings.database_url))


OperationalStoreDependency = Annotated[PostgresOperationalStore, Depends(operational_store)]


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
        return codec.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


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
    token_type: str = "bearer"
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
def list_agents(registry: AgentRegistryDependency) -> tuple[AgentDefinition, ...]:
    return registry.load_all()


@router.get("/agents/{agent_id}", response_model=AgentDefinition, tags=["agent-registry"])
def get_agent(agent_id: str, registry: AgentRegistryDependency) -> AgentDefinition:
    try:
        return registry.get(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Core Agent tidak ditemukan") from exc


@router.get("/workflows", response_model=list[WorkflowDefinition], tags=["workflow"])
def list_workflows(
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
    runtime: SharedRuntimeDependency,
) -> AgentExecutionPlan:
    try:
        return runtime.prepare(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Core Agent tidak ditemukan") from exc
    except RuntimePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

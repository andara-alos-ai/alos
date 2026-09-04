from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from alos.agents.registry import (
    AgentBuilderRequest,
    AgentConflictError,
    AgentDraftBuilder,
    AgentNotFoundError,
    AgentRegistryError,
    AgentRegistryRecord,
    AgentRegistryRepository,
    DeterministicAgentDraftGenerator,
    LocalBootstrapRequest,
)
from alos.audit.reader import AuditEventRecord, AuditReader
from alos.config import get_settings
from alos.genesis.history import (
    GenesisArtifactRecord,
    GenesisConversationRecord,
    GenesisConversationRequest,
    GenesisHistoryError,
    GenesisHistoryRepository,
    GenesisMessageRecord,
    GenesisMessageRequest,
)
from alos.identity import DivisionCode, HumanRole
from alos.identity.authentication import (
    AuthenticationError,
    AuthenticationPrincipal,
    IdentityAuthenticationRepository,
    PasswordLoginRequest,
    WorkspaceSummary,
)
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGatewayPolicyError,
    RetryingModelGateway,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.permissions.registry import (
    PermissionConflictError,
    PermissionNotFoundError,
    PermissionPolicyRecord,
    PermissionPolicyRequest,
    PermissionRegistryError,
    PermissionRegistryRepository,
)
from alos.persistence.database import database_is_ready
from alos.release.governance import (
    AgentTestRunner,
    LifecycleConflictError,
    LocalReleaseTeam,
    ReasonRequest,
    ReleaseGovernanceError,
    ReleaseGovernanceRepository,
    ReleaseRequestDetail,
    ReleaseRequestInput,
    ReleaseRequestRecord,
    ReviewRequest,
    RollbackRequest,
    SegregationOfDutiesError,
    TestCaseRecord,
    TestCaseRequest,
    TestExecutionResult,
)
from alos.runtime.service import (
    AgentRunRequest,
    AgentRunResult,
    AgentRunSummary,
    AgentRuntime,
    AgentRuntimeBlocked,
    AgentRuntimeError,
    AgentRuntimeRepository,
    WorkspaceBudget,
    WorkspaceBudgetRequest,
    WorkspaceUsageSummary,
)
from alos.security.tokens import (
    SESSION_COOKIE_NAME,
    ActorContext,
    LocalTokenRequest,
    get_current_actor,
    issue_access_token,
    issue_local_token,
)
from alos.sources.registry import (
    EvidenceCitation,
    SourceConflictError,
    SourceNotFoundError,
    SourceRegistrationRequest,
    SourceRegistryError,
    SourceRegistryRepository,
    SourceVerificationRequest,
    SourceVersionRecord,
)
from alos.tools.registry import (
    ToolConflictError,
    ToolDefinitionRecord,
    ToolDefinitionRequest,
    ToolNotFoundError,
    ToolRegistryError,
    ToolRegistryRepository,
)

app = FastAPI(title="ALOS", version="0.2.0")


class AgentDesignerRequest(BaseModel):
    """Minimal natural-language entry point; resulting contracts always stay DRAFT."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    requirement: str = Field(min_length=20, max_length=10_000)
    parent_agent_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    conversation_id: UUID | None = None

    def to_builder_request(self) -> AgentBuilderRequest:
        digest = sha256(self.requirement.encode("utf-8")).hexdigest().upper()
        return AgentBuilderRequest(
            workspace_id=self.workspace_id,
            agent_key=self.agent_key or f"GENESIS_{digest[:12]}",
            name=self.name or f"Genesis Draft {digest[:8]}",
            objective=self.requirement,
            parent_agent_key=self.parent_agent_key,
            risk_level="LOW",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            model_policy={
                "provider": get_settings().llm_provider,
                "model_route": "light",
                "usage": "controlled_draft",
            },
            tool_keys=[],
            permission_keys=[],
            approval_required=True,
            forbidden_actions=[
                "Do not write data, contact external parties, spend funds, or change production."
            ],
            kpis=[{"name": "citation_coverage", "target": 1}],
        )


class ModelPolicySummary(BaseModel):
    """Safe server-side model routing information; credentials are never represented here."""

    provider: str
    model_light: str
    model_standard: str
    model_critical: str
    max_output_tokens: int


def get_agent_registry_repository() -> AgentRegistryRepository:
    return AgentRegistryRepository(get_settings().database_url)


def get_identity_authentication_repository() -> IdentityAuthenticationRepository:
    return IdentityAuthenticationRepository(get_settings().database_url)


def get_agent_draft_builder() -> AgentDraftBuilder:
    return AgentDraftBuilder(DeterministicAgentDraftGenerator())


def get_agent_runtime() -> AgentRuntime:
    settings = get_settings()
    try:
        delegate, close_gateway = create_model_gateway(settings)
    except ModelGatewayPolicyError as error:
        raise AgentRuntimeBlocked(str(error)) from error
    gateway = GuardedModelGateway(
        RetryingModelGateway(delegate, settings.llm_max_retries),
        settings,
        UsageBudget(
            request_limit=1,
            output_token_limit=settings.llm_max_output_tokens,
        ),
    )
    return AgentRuntime(
        AgentRuntimeRepository(settings.database_url, settings),
        gateway,
        settings,
        close_gateway=close_gateway,
    )


def get_release_repository() -> ReleaseGovernanceRepository:
    return ReleaseGovernanceRepository(get_settings().database_url)


def get_source_registry_repository() -> SourceRegistryRepository:
    return SourceRegistryRepository(get_settings().database_url)


def get_audit_reader() -> AuditReader:
    return AuditReader(get_settings().database_url)


def get_genesis_history_repository() -> GenesisHistoryRepository:
    return GenesisHistoryRepository(get_settings().database_url)


def get_tool_registry_repository() -> ToolRegistryRepository:
    return ToolRegistryRepository(get_settings().database_url)


def get_permission_registry_repository() -> PermissionRegistryRepository:
    return PermissionRegistryRepository(get_settings().database_url)


def require_registry_editor(actor: ActorContext) -> None:
    if not {HumanRole.DIRECTOR, HumanRole.DIVISION_OWNER, HumanRole.IT_LEAD}.intersection(
        actor.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="registry editor role required"
        )


def require_agent_registry_editor(actor: ActorContext) -> None:
    """Agent Contracts are created and changed only by the IT Lead."""
    if HumanRole.IT_LEAD not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="IT Lead registry authority required"
        )


def require_workspace_access(actor: ActorContext, workspace_id: UUID) -> None:
    if workspace_id not in actor.workspace_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="workspace access required"
        )


def registry_http_error(error: AgentRegistryError) -> HTTPException:
    if isinstance(error, AgentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, AgentConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def runtime_http_error(error: AgentRuntimeError) -> HTTPException:
    if isinstance(error, AgentRuntimeBlocked):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def source_http_error(error: SourceRegistryError) -> HTTPException:
    if isinstance(error, SourceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, SourceConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def genesis_http_error(error: GenesisHistoryError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def tool_http_error(error: ToolRegistryError) -> HTTPException:
    if isinstance(error, ToolNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ToolConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def permission_http_error(error: PermissionRegistryError) -> HTTPException:
    if isinstance(error, PermissionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, PermissionConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def release_http_error(error: ReleaseGovernanceError) -> HTTPException:
    if isinstance(error, (LifecycleConflictError, SegregationOfDutiesError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def require_checker(actor: ActorContext) -> None:
    if not {HumanRole.QA_SECURITY, HumanRole.TECHNICAL_REVIEWER}.intersection(actor.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="checker role required")


def require_approver(actor: ActorContext) -> None:
    if HumanRole.DIRECTOR not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Director approval required"
        )


def require_review_role(actor: ActorContext, gate: str) -> None:
    required = HumanRole.BUSINESS_REVIEWER if gate == "BUSINESS" else HumanRole.TECHNICAL_REVIEWER
    if required not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"{gate} reviewer role required"
        )


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "alos",
        "environment": settings.environment,
    }


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    if not database_is_ready(get_settings().database_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not ready",
        )
    return {"status": "ok", "database": "ready"}


@app.post("/api/v1/auth/local-token")
def create_local_token(request: LocalTokenRequest) -> dict[str, str]:
    return {"access_token": issue_local_token(request, get_settings()), "token_type": "bearer"}


@app.post("/api/v1/auth/login", response_model=AuthenticationPrincipal)
def login(request: PasswordLoginRequest, response: Response) -> AuthenticationPrincipal:
    """Create an HttpOnly, same-site browser session without returning its token to JavaScript."""
    try:
        principal = get_identity_authentication_repository().authenticate(request)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        ) from error
    settings = get_settings()
    token = issue_access_token(
        LocalTokenRequest(
            user_id=principal.user_id,
            organization_id=principal.organization_id,
            roles=principal.roles,
            division_codes=principal.division_codes,
            workspace_ids=principal.workspace_ids,
        ),
        settings,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.environment in {"staging", "production"},
        samesite="lax",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return principal


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=get_settings().environment in {"staging", "production"},
        samesite="lax",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/whoami")
def whoami(actor: Annotated[ActorContext, Depends(get_current_actor)]) -> ActorContext:
    return actor


@app.get("/api/v1/workspaces", response_model=list[WorkspaceSummary])
def list_workspaces(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[WorkspaceSummary]:
    return get_identity_authentication_repository().list_workspaces(
        organization_id=actor.organization_id, user_id=actor.user_id
    )


@app.get("/api/v1/governance/model-policy", response_model=ModelPolicySummary)
def get_model_policy(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ModelPolicySummary:
    """Model names are operational policy, while API credentials remain server-only secrets."""
    del actor
    settings = get_settings()
    return ModelPolicySummary(
        provider=settings.llm_provider,
        model_light=settings.model_for_route("light"),
        model_standard=settings.model_for_route("standard"),
        model_critical=settings.model_for_route("critical"),
        max_output_tokens=settings.llm_max_output_tokens,
    )


@app.post("/api/v1/local/bootstrap")
def bootstrap_local_registry_context(request: LocalBootstrapRequest) -> dict[str, str]:
    """Create a local-only human/workspace context for the authenticated H2 Builder."""
    if get_settings().environment not in {"local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="local bootstrap is disabled"
        )
    try:
        context = get_agent_registry_repository().bootstrap_local_context(request, uuid4())
        token = issue_local_token(
            LocalTokenRequest(
                user_id=context.user_id,
                organization_id=context.organization_id,
                roles=[HumanRole.IT_LEAD],
                division_codes=[DivisionCode.IT],
                workspace_ids=[context.workspace_id],
            ),
            get_settings(),
        )
        return {
            **context.model_dump(mode="json"),
            "access_token": token,
            "token_type": "bearer",
        }
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.post("/api/v1/local/release-review-team")
def bootstrap_local_release_review_team(workspace_id: UUID) -> dict[str, object]:
    """Issue local-only test tokens for distinct H4 lifecycle duties."""
    if get_settings().environment not in {"local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="local review-team bootstrap is disabled"
        )
    try:
        team: LocalReleaseTeam = get_release_repository().bootstrap_local_release_team(
            workspace_id, uuid4()
        )
        tokens = {
            participant.duty.lower(): issue_local_token(
                LocalTokenRequest(
                    user_id=participant.user_id,
                    organization_id=team.organization_id,
                    roles=[participant.role],
                    division_codes=[team.division_code],
                    workspace_ids=[team.workspace_id],
                ),
                get_settings(),
            )
            for participant in team.participants
        }
        return {"team": team.model_dump(mode="json"), "access_tokens": tokens}
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post("/api/v1/genesis/conversations", response_model=GenesisConversationRecord)
def create_genesis_conversation(
    request: GenesisConversationRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> GenesisConversationRecord:
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_genesis_history_repository().create_conversation(
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.get(
    "/api/v1/genesis/conversations/{conversation_id}", response_model=GenesisConversationRecord
)
def get_genesis_conversation(
    conversation_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> GenesisConversationRecord:
    try:
        return get_genesis_history_repository().get_conversation(
            conversation_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.post(
    "/api/v1/genesis/conversations/{conversation_id}/messages", response_model=GenesisMessageRecord
)
def add_genesis_message(
    conversation_id: UUID,
    request: GenesisMessageRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> GenesisMessageRecord:
    try:
        return get_genesis_history_repository().add_human_message(
            conversation_id,
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.get(
    "/api/v1/genesis/conversations/{conversation_id}/messages",
    response_model=list[GenesisMessageRecord],
)
def list_genesis_messages(
    conversation_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[GenesisMessageRecord]:
    try:
        return get_genesis_history_repository().list_messages(
            conversation_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.get(
    "/api/v1/genesis/conversations/{conversation_id}/artifacts",
    response_model=list[GenesisArtifactRecord],
)
def list_genesis_artifacts(
    conversation_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[GenesisArtifactRecord]:
    try:
        return get_genesis_history_repository().list_artifacts(
            conversation_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.post("/api/v1/tools", response_model=ToolDefinitionRecord)
def register_tool_draft(
    request: ToolDefinitionRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ToolDefinitionRecord:
    """A maker can only register a read-only Tool Registry draft."""
    require_registry_editor(actor)
    try:
        return get_tool_registry_repository().create_draft(
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ToolRegistryError as error:
        raise tool_http_error(error) from error


@app.get("/api/v1/tools", response_model=list[ToolDefinitionRecord])
def list_tools(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[ToolDefinitionRecord]:
    require_registry_editor(actor)
    return get_tool_registry_repository().list_tools(actor.organization_id)


@app.post("/api/v1/tools/{tool_key}/approve", response_model=ToolDefinitionRecord)
def approve_tool(
    tool_key: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ToolDefinitionRecord:
    if not {HumanRole.DIRECTOR, HumanRole.QA_SECURITY}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="tool approval authority required"
        )
    try:
        return get_tool_registry_repository().approve(
            tool_key,
            organization_id=actor.organization_id,
            approver_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ToolRegistryError as error:
        raise tool_http_error(error) from error


@app.post("/api/v1/permission-policies", response_model=PermissionPolicyRecord)
def register_permission_policy_draft(
    request: PermissionPolicyRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> PermissionPolicyRecord:
    require_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_permission_registry_repository().create_draft(
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except PermissionRegistryError as error:
        raise permission_http_error(error) from error


@app.get("/api/v1/permission-policies", response_model=list[PermissionPolicyRecord])
def list_permission_policies(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    agent_key: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$"),
) -> list[PermissionPolicyRecord]:
    require_registry_editor(actor)
    return get_permission_registry_repository().list_policies(
        actor.organization_id, agent_key=agent_key
    )


@app.post(
    "/api/v1/permission-policies/{permission_policy_id}/approve",
    response_model=PermissionPolicyRecord,
)
def approve_permission_policy(
    permission_policy_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> PermissionPolicyRecord:
    if not {HumanRole.DIRECTOR, HumanRole.QA_SECURITY}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="permission approval authority required"
        )
    try:
        return get_permission_registry_repository().approve(
            permission_policy_id,
            organization_id=actor.organization_id,
            approver_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except PermissionRegistryError as error:
        raise permission_http_error(error) from error


@app.post("/api/v1/agents/drafts")
def create_agent_draft(
    request: AgentBuilderRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    require_agent_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    correlation_id = uuid4()
    try:
        contract = get_agent_draft_builder().build(request, actor.user_id)
        result = get_agent_registry_repository().create_draft(
            contract,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=correlation_id,
            reason="Genesis Builder created an Agent Contract draft",
        )
        return result.model_dump(mode="json")
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.post("/api/v1/designer/agent-drafts")
def design_agent_draft(
    request: AgentDesignerRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    """Genesis Designer is allowed to create a draft only, never an active agent."""
    require_agent_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    correlation_id = uuid4()
    try:
        history = get_genesis_history_repository()
        requirement_record = None
        if request.conversation_id is not None:
            conversation = history.get_conversation(
                request.conversation_id,
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
            )
            if conversation.workspace_id != request.workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Genesis conversation belongs to a different workspace",
                )
            requirement_record = history.record_requirement(
                request.conversation_id,
                request.requirement,
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
                correlation_id=correlation_id,
            )
        contract = get_agent_draft_builder().build(request.to_builder_request(), actor.user_id)
        result = get_agent_registry_repository().create_draft(
            contract,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=correlation_id,
            reason="Genesis Designer created a natural-language Agent Contract draft",
        )
        artifact_ids: dict[str, str] = {}
        if request.conversation_id is not None:
            blueprint_artifact = history.record_system_artifact(
                request.conversation_id,
                "BLUEPRINT",
                {
                    "requirement": request.requirement,
                    "agent_key": result.agent_key,
                    "risk_level": contract.risk_level,
                    "approval_required": contract.approval_required,
                    "forbidden_actions": contract.forbidden_actions,
                },
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
                correlation_id=correlation_id,
            )
            contract_artifact = history.record_system_artifact(
                request.conversation_id,
                "CONTRACT",
                contract.model_dump(mode="json"),
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
                correlation_id=correlation_id,
            )
            artifact_ids = {
                "blueprint_artifact_id": str(blueprint_artifact.artifact_id),
                "contract_artifact_id": str(contract_artifact.artifact_id),
            }
        return {
            "blueprint": {
                "requirement": request.requirement,
                "agent_key": result.agent_key,
                "risk_level": contract.risk_level,
                "approval_required": contract.approval_required,
                "forbidden_actions": contract.forbidden_actions,
            },
            "draft": result.model_dump(mode="json"),
            "genesis": {
                "conversation_id": str(request.conversation_id)
                if request.conversation_id is not None
                else None,
                "change_request_id": str(requirement_record.change_request_id)
                if requirement_record is not None
                else None,
                **artifact_ids,
            },
        }
    except AgentRegistryError as error:
        raise registry_http_error(error) from error
    except GenesisHistoryError as error:
        raise genesis_http_error(error) from error


@app.put("/api/v1/agents/{agent_key}/draft")
def update_agent_draft(
    agent_key: str,
    request: AgentBuilderRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    require_agent_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    if request.agent_key != agent_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="agent key is immutable"
        )
    correlation_id = uuid4()
    try:
        contract = get_agent_draft_builder().build(request, actor.user_id)
        result = get_agent_registry_repository().update_draft(
            contract,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=correlation_id,
            reason="Genesis Builder updated an Agent Contract draft",
        )
        return result.model_dump(mode="json")
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.get("/api/v1/agents", response_model=list[AgentRegistryRecord])
def list_agents(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    workspace_id: UUID,
) -> list[AgentRegistryRecord]:
    require_agent_registry_editor(actor)
    require_workspace_access(actor, workspace_id)
    try:
        return get_agent_registry_repository().list_agents(actor.organization_id, workspace_id)
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.get("/api/v1/agents/{agent_key}", response_model=AgentRegistryRecord)
def get_agent(
    agent_key: str, actor: Annotated[ActorContext, Depends(get_current_actor)]
) -> AgentRegistryRecord:
    require_agent_registry_editor(actor)
    try:
        record = get_agent_registry_repository().get_agent(actor.organization_id, agent_key)
        require_workspace_access(actor, record.workspace_id)
        return record
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.post("/api/v1/sources", response_model=SourceVersionRecord)
def register_source_version(
    request: SourceRegistrationRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> SourceVersionRecord:
    """Register a textual source version; it is not retrievable until human verification."""
    require_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_source_registry_repository().register(
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except SourceRegistryError as error:
        raise source_http_error(error) from error


@app.post("/api/v1/sources/{source_key}/verify", response_model=SourceVersionRecord)
def verify_source_version(
    source_key: str,
    request: SourceVerificationRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> SourceVersionRecord:
    """An explicit human gate makes a source eligible for Runtime evidence retrieval."""
    if not {HumanRole.DIRECTOR, HumanRole.DIVISION_OWNER, HumanRole.IT_LEAD}.intersection(
        actor.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="source verification authority required"
        )
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_source_registry_repository().verify(
            request.workspace_id,
            source_key,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
            reason=request.reason,
        )
    except SourceRegistryError as error:
        raise source_http_error(error) from error


@app.get(
    "/api/v1/workspaces/{workspace_id}/sources/evidence", response_model=list[EvidenceCitation]
)
def search_source_evidence(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    query: str = Query(default="", max_length=2_000),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[EvidenceCitation]:
    """Show deterministic source citations that an approved read-only tool can retrieve."""
    require_workspace_access(actor, workspace_id)
    try:
        return get_source_registry_repository().search_evidence(
            workspace_id, query, organization_id=actor.organization_id, limit=limit
        )
    except SourceRegistryError as error:
        raise source_http_error(error) from error


@app.post("/api/v1/agents/{agent_key}/retire")
def retire_agent(
    agent_key: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    require_agent_registry_editor(actor)
    try:
        result = get_agent_registry_repository().retire(
            agent_key,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
            reason="Human requested agent retirement",
        )
        return result.model_dump(mode="json")
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.post("/api/v1/agents/{agent_key}/runs", response_model=AgentRunResult)
def run_agent(
    agent_key: str,
    request: AgentRunRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> AgentRunResult:
    # H3 is limited to IT Lead-controlled fixture execution. Broader runtime
    # authority is introduced only after lifecycle/review gates are complete.
    require_agent_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_agent_runtime().execute(
            agent_key,
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except AgentRuntimeError as error:
        raise runtime_http_error(error) from error


@app.get("/api/v1/workspaces/{workspace_id}/runs", response_model=list[AgentRunSummary])
def list_workspace_runs(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AgentRunSummary]:
    """Read-only execution telemetry for the future operations dashboard."""
    require_workspace_access(actor, workspace_id)
    try:
        return AgentRuntimeRepository(get_settings().database_url, get_settings()).list_runs(
            workspace_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            limit=limit,
        )
    except AgentRuntimeError as error:
        raise runtime_http_error(error) from error


@app.get(
    "/api/v1/workspaces/{workspace_id}/usage/daily", response_model=WorkspaceUsageSummary
)
def get_workspace_usage(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> WorkspaceUsageSummary:
    """Read the same persisted daily ledger used by the cost guardrail."""
    require_workspace_access(actor, workspace_id)
    try:
        return AgentRuntimeRepository(get_settings().database_url, get_settings()).usage_summary(
            workspace_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except AgentRuntimeError as error:
        raise runtime_http_error(error) from error


@app.get("/api/v1/audit-events", response_model=list[AuditEventRecord])
def list_audit_events(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    limit: int = Query(default=100, ge=1, le=500),
    workspace_id: UUID | None = None,
) -> list[AuditEventRecord]:
    """Only designated control roles may inspect the organization audit trail."""
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD, HumanRole.QA_SECURITY}.intersection(
        actor.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="audit reader role required"
        )
    if workspace_id is not None:
        require_workspace_access(actor, workspace_id)
    return get_audit_reader().list_events(
        actor.organization_id, limit=limit, workspace_id=workspace_id
    )


@app.get("/api/v1/workspaces/{workspace_id}/budget", response_model=WorkspaceBudget)
def get_workspace_budget(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> WorkspaceBudget:
    require_workspace_access(actor, workspace_id)
    try:
        return AgentRuntimeRepository(get_settings().database_url, get_settings()).get_budget_limit(
            workspace_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except AgentRuntimeError as error:
        raise runtime_http_error(error) from error


@app.put("/api/v1/workspaces/{workspace_id}/budget", response_model=WorkspaceBudget)
def set_workspace_budget(
    workspace_id: UUID,
    request: WorkspaceBudgetRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> WorkspaceBudget:
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="budget authority required"
        )
    require_workspace_access(actor, workspace_id)
    try:
        return AgentRuntimeRepository(get_settings().database_url, get_settings()).set_budget_limit(
            workspace_id,
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except AgentRuntimeError as error:
        raise runtime_http_error(error) from error


@app.post("/api/v1/agents/{agent_key}/release-requests", response_model=ReleaseRequestRecord)
def create_release_request(
    agent_key: str,
    request: ReleaseRequestInput,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    try:
        return get_release_repository().create_release_request(
            agent_key,
            request.workspace_id,
            request.requirement,
            organization_id=actor.organization_id,
            maker_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.get("/api/v1/release-requests", response_model=list[ReleaseRequestRecord])
def list_release_requests(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReleaseRequestRecord]:
    require_workspace_access(actor, workspace_id)
    try:
        return get_release_repository().list_release_requests(
            workspace_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            limit=limit,
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.get("/api/v1/release-requests/{change_request_id}", response_model=ReleaseRequestDetail)
def get_release_request_detail(
    change_request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestDetail:
    try:
        return get_release_repository().get_release_request_detail(
            change_request_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post("/api/v1/release-requests/{change_request_id}/test-cases", response_model=TestCaseRecord)
def register_release_test_case(
    change_request_id: UUID,
    request: TestCaseRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> TestCaseRecord:
    try:
        return get_release_repository().register_test_case(
            change_request_id,
            request,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/test-cases/{test_key}/execute",
    response_model=TestExecutionResult,
)
def execute_release_test_case(
    change_request_id: UUID,
    test_key: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> TestExecutionResult:
    require_checker(actor)
    runtime = get_agent_runtime()
    try:
        runner = AgentTestRunner(
            get_release_repository(),
            lambda agent_key, runtime_request: runtime.execute(
                agent_key,
                runtime_request,
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
            ),
        )
        return runner.execute(
            change_request_id,
            test_key,
            checker_user_id=actor.user_id,
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/submit-review",
    response_model=ReleaseRequestRecord,
)
def submit_release_for_review(
    change_request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_checker(actor)
    try:
        return get_release_repository().submit_for_review(
            change_request_id,
            checker_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/reviews", response_model=ReleaseRequestRecord
)
def review_release_request(
    change_request_id: UUID,
    request: ReviewRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_review_role(actor, request.gate)
    try:
        return get_release_repository().review(
            change_request_id,
            request,
            reviewer_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/approve", response_model=ReleaseRequestRecord
)
def approve_release_request(
    change_request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_approver(actor)
    try:
        return get_release_repository().approve(
            change_request_id,
            approver_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/release", response_model=ReleaseRequestRecord
)
def release_approved_request(
    change_request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_approver(actor)
    try:
        return get_release_repository().release(
            change_request_id,
            approver_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/activate", response_model=ReleaseRequestRecord
)
def activate_released_request(
    change_request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_approver(actor)
    try:
        return get_release_repository().activate(
            change_request_id,
            approver_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/suspend", response_model=ReleaseRequestRecord
)
def suspend_release_request(
    change_request_id: UUID,
    request: ReasonRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_approver(actor)
    try:
        return get_release_repository().suspend(
            change_request_id,
            actor_user_id=actor.user_id,
            reason=request.reason,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/kill-switch", response_model=ReleaseRequestRecord
)
def activate_kill_switch(
    change_request_id: UUID,
    request: ReasonRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="kill switch authority required"
        )
    try:
        return get_release_repository().kill_switch(
            change_request_id,
            actor_user_id=actor.user_id,
            reason=request.reason,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/clear-kill-switch",
    response_model=ReleaseRequestRecord,
)
def clear_kill_switch(
    change_request_id: UUID,
    request: ReasonRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="kill switch authority required"
        )
    try:
        return get_release_repository().clear_kill_switch(
            change_request_id,
            actor_user_id=actor.user_id,
            reason=request.reason,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error


@app.post(
    "/api/v1/release-requests/{change_request_id}/rollback", response_model=ReleaseRequestRecord
)
def rollback_release_request(
    change_request_id: UUID,
    request: RollbackRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseRequestRecord:
    require_approver(actor)
    try:
        return get_release_repository().rollback(
            change_request_id,
            request,
            actor_user_id=actor.user_id,
            correlation_id=uuid4(),
        )
    except ReleaseGovernanceError as error:
        raise release_http_error(error) from error

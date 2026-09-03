from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from alos.agents.registry import (
    AgentBuilderRequest,
    AgentConflictError,
    AgentDraftBuilder,
    AgentNotFoundError,
    AgentRegistryError,
    AgentRegistryRecord,
    AgentRegistryRepository,
    GeminiAgentDraftGenerator,
    LocalBootstrapRequest,
)
from alos.config import get_settings
from alos.gemini_gateway import GeminiModelGateway
from alos.identity import DivisionCode, HumanRole
from alos.model_gateway import GuardedModelGateway, RetryingModelGateway, UsageBudget
from alos.persistence.database import database_is_ready
from alos.release.governance import (
    AgentTestRunner,
    LifecycleConflictError,
    LocalReleaseTeam,
    ReasonRequest,
    ReleaseGovernanceError,
    ReleaseGovernanceRepository,
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
    AgentRuntime,
    AgentRuntimeBlocked,
    AgentRuntimeError,
    AgentRuntimeRepository,
    WorkspaceBudget,
    WorkspaceBudgetRequest,
)
from alos.security.tokens import (
    ActorContext,
    LocalTokenRequest,
    get_current_actor,
    issue_local_token,
)

app = FastAPI(title="ALOS", version="0.2.0")


class AgentDesignerRequest(BaseModel):
    """Minimal natural-language entry point; resulting contracts always stay DRAFT."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str = Field(min_length=1, max_length=200)
    requirement: str = Field(min_length=20, max_length=10_000)
    parent_agent_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")

    def to_builder_request(self) -> AgentBuilderRequest:
        return AgentBuilderRequest(
            workspace_id=self.workspace_id,
            agent_key=self.agent_key,
            name=self.name,
            objective=self.requirement,
            parent_agent_key=self.parent_agent_key,
            risk_level="LOW",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            model_policy={"provider": "gemini", "usage": "local_test"},
            tool_keys=[],
            permission_keys=[],
            approval_required=True,
            forbidden_actions=[
                "Do not write data, contact external parties, spend funds, or change production."
            ],
            kpis=[{"name": "citation_coverage", "target": 1}],
        )


def get_agent_registry_repository() -> AgentRegistryRepository:
    return AgentRegistryRepository(get_settings().database_url)


def get_agent_draft_builder() -> AgentDraftBuilder:
    settings = get_settings()
    return AgentDraftBuilder(GeminiAgentDraftGenerator(settings))


def get_agent_runtime() -> AgentRuntime:
    settings = get_settings()
    if settings.llm_provider != "gemini":
        raise AgentRuntimeBlocked("H3 local Runtime requires the Gemini Model Gateway")
    delegate = GeminiModelGateway(settings)
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
        close_gateway=delegate.close,
    )


def get_release_repository() -> ReleaseGovernanceRepository:
    return ReleaseGovernanceRepository(get_settings().database_url)


def require_registry_editor(actor: ActorContext) -> None:
    if not {HumanRole.DIRECTOR, HumanRole.DIVISION_OWNER, HumanRole.IT_LEAD}.intersection(
        actor.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="registry editor role required"
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


@app.get("/api/v1/whoami")
def whoami(actor: Annotated[ActorContext, Depends(get_current_actor)]) -> ActorContext:
    return actor


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
                roles=[HumanRole.DIRECTOR],
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


@app.post("/api/v1/agents/drafts")
def create_agent_draft(
    request: AgentBuilderRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    require_registry_editor(actor)
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
    require_registry_editor(actor)
    require_workspace_access(actor, request.workspace_id)
    correlation_id = uuid4()
    try:
        contract = get_agent_draft_builder().build(request.to_builder_request(), actor.user_id)
        result = get_agent_registry_repository().create_draft(
            contract,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=correlation_id,
            reason="Genesis Designer created a natural-language Agent Contract draft",
        )
        return {
            "blueprint": {
                "requirement": request.requirement,
                "agent_key": request.agent_key,
                "risk_level": contract.risk_level,
                "approval_required": contract.approval_required,
                "forbidden_actions": contract.forbidden_actions,
            },
            "draft": result.model_dump(mode="json"),
        }
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.put("/api/v1/agents/{agent_key}/draft")
def update_agent_draft(
    agent_key: str,
    request: AgentBuilderRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    require_registry_editor(actor)
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
) -> list[AgentRegistryRecord]:
    require_registry_editor(actor)
    try:
        return get_agent_registry_repository().list_agents(actor.organization_id)
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.get("/api/v1/agents/{agent_key}", response_model=AgentRegistryRecord)
def get_agent(
    agent_key: str, actor: Annotated[ActorContext, Depends(get_current_actor)]
) -> AgentRegistryRecord:
    require_registry_editor(actor)
    try:
        return get_agent_registry_repository().get_agent(actor.organization_id, agent_key)
    except AgentRegistryError as error:
        raise registry_http_error(error) from error


@app.post("/api/v1/agents/{agent_key}/retire")
def retire_agent(
    agent_key: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> dict[str, object]:
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="retirement authority required"
        )
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
    require_registry_editor(actor)
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


@app.get("/api/v1/workspaces/{workspace_id}/budget", response_model=WorkspaceBudget)
def get_workspace_budget(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> WorkspaceBudget:
    if not {HumanRole.DIRECTOR, HumanRole.IT_LEAD}.intersection(actor.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="budget authority required"
        )
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

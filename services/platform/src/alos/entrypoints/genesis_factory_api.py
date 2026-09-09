"""Authenticated HTTP boundary for the persistent GENESIS Factory."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from alos.agents.registry import AgentRegistryError, AgentRegistryRepository
from alos.capabilities.registry import CapabilityRegistryRepository
from alos.config import Settings, get_settings
from alos.genesis.factory.analyzer import RequirementAnalysisError, RequirementAnalyzer
from alos.genesis.factory.models import RequirementUnderstanding
from alos.genesis.factory.persistence import (
    FactoryPersistenceError,
    FactoryRepository,
    FactoryRequestConflictError,
    FactoryRequestCreate,
    FactoryRequestNotFoundError,
    FactoryRequestPage,
    FactoryRequestRecord,
    FactoryStatus,
)
from alos.genesis.factory.pipeline import FactoryDependencyResolver
from alos.genesis.factory.service import FactoryAnalysisError, GenesisFactoryService
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGatewayPolicyError,
    RetryingModelGateway,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.release.governance import ReleaseGovernanceError, ReleaseGovernanceRepository
from alos.runtime.agentic import (
    ALOSModelAdapter,
    ExecutionContext,
    ExecutionLimits,
    PydanticAgenticEngine,
)
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/genesis/factory", tags=["genesis-factory"])


class FactoryAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str | None = Field(default=None, min_length=1, max_length=200)


class GatewayRequirementAnalyzer:
    """Construct one governed model boundary for each semantic analysis."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def analyze(
        self,
        requirement: str,
        *,
        context: ExecutionContext,
        limits: ExecutionLimits,
    ) -> RequirementUnderstanding:
        delegate, close_gateway = create_model_gateway(self._settings)
        try:
            gateway = GuardedModelGateway(
                RetryingModelGateway(delegate, self._settings.llm_max_retries),
                self._settings,
                UsageBudget(
                    request_limit=limits.max_model_steps,
                    output_token_limit=limits.max_output_tokens,
                ),
            )
            model = ALOSModelAdapter(
                gateway,
                model_name=self._settings.llm_model_standard,
                classification="INTERNAL",
                correlation_id=context.correlation_id,
                max_output_tokens=limits.max_output_tokens,
            )
            return RequirementAnalyzer(PydanticAgenticEngine(model)).analyze(
                requirement,
                context=context,
                limits=limits,
            )
        finally:
            close_gateway()


def get_genesis_factory_service() -> GenesisFactoryService:
    settings = get_settings()
    return GenesisFactoryService(
        FactoryRepository(settings.database_url),
        GatewayRequirementAnalyzer(settings),
        FactoryDependencyResolver(CapabilityRegistryRepository(settings.database_url)),
        AgentRegistryRepository(settings.database_url),
        ReleaseGovernanceRepository(settings.database_url),
        limits=ExecutionLimits(
            max_model_steps=settings.agentic_max_model_steps,
            max_tool_calls=settings.agentic_max_tool_calls,
            max_delegation_depth=settings.agentic_max_delegation_depth,
            max_subagents=settings.agentic_max_subagents,
            max_concurrency=settings.agentic_max_concurrency,
            max_output_tokens=settings.llm_max_output_tokens,
            max_total_tokens=(settings.llm_max_output_tokens * settings.agentic_max_model_steps),
            max_cost_per_run=settings.agentic_max_cost_per_run,
        ),
    )


@router.post(
    "/requests",
    response_model=FactoryRequestRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_factory_request(
    request: FactoryRequestCreate,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    service: Annotated[GenesisFactoryService, Depends(get_genesis_factory_service)],
) -> FactoryRequestRecord:
    try:
        return service.create(request, actor, correlation_id=uuid4())
    except FactoryPersistenceError as error:
        raise _factory_http_error(error) from error


@router.get("/requests/{request_id}", response_model=FactoryRequestRecord)
def get_factory_request(
    request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    service: Annotated[GenesisFactoryService, Depends(get_genesis_factory_service)],
) -> FactoryRequestRecord:
    try:
        return service.get(request_id, actor)
    except FactoryPersistenceError as error:
        raise _factory_http_error(error) from error


@router.get("/requests", response_model=FactoryRequestPage)
def list_factory_requests(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    service: Annotated[GenesisFactoryService, Depends(get_genesis_factory_service)],
    workspace_id: UUID | None = None,
    factory_status: Annotated[FactoryStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FactoryRequestPage:
    try:
        return service.list_requests(
            actor,
            workspace_id=workspace_id,
            status=factory_status,
            limit=limit,
            offset=offset,
        )
    except FactoryPersistenceError as error:
        raise _factory_http_error(error) from error


@router.post("/requests/{request_id}/analyze", response_model=FactoryRequestRecord)
def analyze_factory_request(
    request_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    service: Annotated[GenesisFactoryService, Depends(get_genesis_factory_service)],
    request: Annotated[FactoryAnalyzeRequest | None, Body()] = None,
) -> FactoryRequestRecord:
    options = request or FactoryAnalyzeRequest()
    try:
        return service.analyze(
            request_id,
            actor,
            correlation_id=uuid4(),
            agent_key=options.agent_key,
            name=options.name,
        )
    except FactoryPersistenceError as error:
        raise _factory_http_error(error) from error
    except (
        FactoryAnalysisError,
        RequirementAnalysisError,
        ModelGatewayPolicyError,
        AgentRegistryError,
        ReleaseGovernanceError,
    ) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


def _factory_http_error(error: FactoryPersistenceError) -> HTTPException:
    if isinstance(error, FactoryRequestNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, FactoryRequestConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))

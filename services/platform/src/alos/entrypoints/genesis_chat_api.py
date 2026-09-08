"""General GENESIS conversation API."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from alos.capabilities.registry import CapabilityRegistryRepository
from alos.config import Settings, get_settings
from alos.genesis.chat import (
    ExternalResearchService,
    GenesisChatError,
    GenesisChatService,
    GenesisTurnRequest,
    GenesisTurnResult,
)
from alos.genesis.history import (
    GenesisConversationContextRecord,
    GenesisConversationContextRequest,
    GenesisConversationRecord,
    GenesisHistoryError,
    GenesisHistoryRepository,
)
from alos.genesis.router import AgentRouter
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGateway,
    ModelGatewayError,
    RetryingModelGateway,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.operational.repository import OperationalRepository
from alos.security.tokens import ActorContext, get_current_actor
from alos.tools.executor import ToolExecutor

router = APIRouter(prefix="/api/v1/genesis", tags=["genesis-chat"])


@router.get("/conversations", response_model=list[GenesisConversationRecord])
def list_conversations(
    workspace_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[GenesisConversationRecord]:
    try:
        return GenesisHistoryRepository(get_settings().database_url).list_conversations(
            workspace_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            limit=limit,
        )
    except GenesisHistoryError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get(
    "/conversations/{conversation_id}/context",
    response_model=list[GenesisConversationContextRecord],
)
def list_conversation_context(
    conversation_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[GenesisConversationContextRecord]:
    try:
        return GenesisHistoryRepository(get_settings().database_url).list_context(
            conversation_id,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
        )
    except GenesisHistoryError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/context",
    response_model=GenesisConversationContextRecord,
)
def attach_conversation_context(
    conversation_id: UUID,
    request: GenesisConversationContextRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> GenesisConversationContextRecord:
    settings = get_settings()
    service, close_gateway = _chat_service(settings)
    correlation_id = uuid4()
    try:
        service.authorize_context(request, actor, correlation_id)
        return GenesisHistoryRepository(settings.database_url).attach_context(
            conversation_id,
            request,
            organization_id=actor.organization_id,
            actor_user_id=actor.user_id,
            correlation_id=correlation_id,
        )
    except (GenesisHistoryError, GenesisChatError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    finally:
        close_gateway()


@router.post(
    "/conversations/{conversation_id}/turns", response_model=GenesisTurnResult
)
def run_conversation_turn(
    conversation_id: UUID,
    request: GenesisTurnRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> GenesisTurnResult:
    settings = get_settings()
    service, close_gateway = _chat_service(settings)
    try:
        return service.turn(conversation_id, request, actor, correlation_id=uuid4())
    except GenesisHistoryError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except GenesisChatError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ModelGatewayError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GENESIS model unavailable: {error.code}",
        ) from error
    finally:
        close_gateway()


def _chat_service(settings: Settings) -> tuple[GenesisChatService, Callable[[], None]]:
    def close_gateway() -> None:
        return None

    gateway: ModelGateway | None = None
    try:
        delegate, close_gateway = create_model_gateway(settings)
        gateway = GuardedModelGateway(
            RetryingModelGateway(delegate, settings.llm_max_retries),
            settings,
            UsageBudget(request_limit=1, output_token_limit=settings.llm_max_output_tokens),
        )
    except ModelGatewayError:
        if settings.environment not in {"local", "test"}:
            raise
    database_url = settings.database_url
    return (
        GenesisChatService(
            GenesisHistoryRepository(database_url),
            CapabilityRegistryRepository(database_url),
            AgentRouter(database_url),
            ToolExecutor(database_url),
            ExternalResearchService(database_url),
            OperationalRepository(database_url),
            gateway=gateway,
            model=settings.llm_model_standard,
            max_output_tokens=min(2_000, settings.llm_max_output_tokens),
        ),
        close_gateway,
    )

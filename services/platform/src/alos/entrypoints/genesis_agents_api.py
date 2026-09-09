"""HTTP boundary for the governed GENESIS Agent Designer."""

from collections.abc import Callable
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from alos.agents.registry import AgentRegistryError, AgentRegistryRepository
from alos.capabilities.registry import CapabilityRegistryRepository
from alos.config import Settings, get_settings
from alos.genesis.agent_designer import (
    AgentDesignGenerator,
    AgentDesignRequest,
    AgentDesignResult,
    DeterministicAgentDesignGenerator,
    GenesisAgentDesigner,
    GenesisAgentDesignerError,
    ModelAgentDesignGenerator,
)
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGatewayPolicyError,
    RetryingModelGateway,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.release.governance import ReleaseGovernanceError, ReleaseGovernanceRepository
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/genesis", tags=["genesis-agent-factory"])


@router.post("/agent-requests", response_model=AgentDesignResult)
def create_agent_from_business_request(
    request: AgentDesignRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> AgentDesignResult:
    settings = get_settings()
    designer, close_gateway = create_genesis_agent_designer(
        settings, deterministic=request.deterministic
    )
    try:
        return designer.design(request, actor, correlation_id=uuid4())
    except HTTPException:
        raise
    except (GenesisAgentDesignerError, AgentRegistryError, ReleaseGovernanceError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    finally:
        close_gateway()


def create_genesis_agent_designer(
    settings: Settings, *, deterministic: bool
) -> tuple[GenesisAgentDesigner, Callable[[], None]]:
    def close_gateway() -> None:
        return None

    generator: AgentDesignGenerator
    if deterministic:
        if settings.environment not in {"local", "test"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="deterministic Agent Designer is restricted to local/test",
            )
        generator = DeterministicAgentDesignGenerator()
    else:
        try:
            delegate, close_gateway = create_model_gateway(settings)
            gateway = GuardedModelGateway(
                RetryingModelGateway(delegate, settings.llm_max_retries),
                settings,
                UsageBudget(request_limit=1, output_token_limit=settings.llm_max_output_tokens),
            )
            generator = ModelAgentDesignGenerator(
                gateway,
                settings.llm_model_standard,
                max_output_tokens=min(4_000, settings.llm_max_output_tokens),
            )
        except ModelGatewayPolicyError as error:
            if settings.environment not in {"local", "test"}:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(error),
                ) from error
            generator = DeterministicAgentDesignGenerator()
    database_url = settings.database_url
    return (
        GenesisAgentDesigner(
            generator,
            CapabilityRegistryRepository(database_url),
            AgentRegistryRepository(database_url),
            ReleaseGovernanceRepository(database_url),
        ),
        close_gateway,
    )

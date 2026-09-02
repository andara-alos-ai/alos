from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentDefinition, AgentReference
from alos.agents.registry import RegistryError
from alos.agents.runtime import (
    AgentCapabilityExecuteRequest,
    AgentCapabilityExecutionView,
    AgentLifecycleService,
    RuntimePolicyViolation,
)
from alos.agents.runtime.application import AgentCapabilityService
from alos.config import Settings, get_settings
from alos.entrypoints.api import (
    AgentRegistryDependency,
    OperationalStoreDependency,
    PrincipalDependency,
    SharedRuntimeDependency,
)
from alos.security.authorization import AuthorizationDenied

router = APIRouter(prefix="/agent-runtime", tags=["agents", "shared-runtime"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def capability_service(
    settings: SettingsDependency,
    agents: AgentRegistryDependency,
    runtime: SharedRuntimeDependency,
    store: OperationalStoreDependency,
) -> AgentCapabilityService:
    return AgentCapabilityService(
        agents,
        CapabilityRegistry(settings.definitions_root),
        runtime,
        store,
    )


CapabilityServiceDependency = Annotated[
    AgentCapabilityService, Depends(capability_service)
]


class AgentLifecycleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=10, max_length=1000)


class AgentRollbackCommand(AgentLifecycleCommand):
    rollback_target: AgentReference


def lifecycle_service(
    agents: AgentRegistryDependency,
    store: OperationalStoreDependency,
) -> AgentLifecycleService:
    return AgentLifecycleService(agents, store)


LifecycleServiceDependency = Annotated[AgentLifecycleService, Depends(lifecycle_service)]


@router.post("/execute", response_model=AgentCapabilityExecutionView, status_code=201)
def execute_agent_capability(
    request: AgentCapabilityExecuteRequest,
    principal: PrincipalDependency,
    service: CapabilityServiceDependency,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=120)
    ],
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> AgentCapabilityExecutionView:
    try:
        return service.execute(request, principal, idempotency_key, correlation_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimePolicyViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Eksekusi agent duplikat") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/agents/{agent_id}/{version}/activate",
    response_model=AgentDefinition,
    tags=["agents", "shared-runtime"],
)
def activate_generated_agent(
    agent_id: str,
    version: str,
    request: AgentLifecycleCommand,
    principal: PrincipalDependency,
    service: LifecycleServiceDependency,
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> AgentDefinition:
    return _lifecycle_execute(
        lambda: service.activate(
            agent_id, version, principal, request.reason, correlation_id
        )
    )


@router.post(
    "/agents/{agent_id}/{version}/suspend",
    response_model=AgentDefinition,
    tags=["agents", "shared-runtime"],
)
def suspend_generated_agent(
    agent_id: str,
    version: str,
    request: AgentLifecycleCommand,
    principal: PrincipalDependency,
    service: LifecycleServiceDependency,
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> AgentDefinition:
    return _lifecycle_execute(
        lambda: service.suspend(agent_id, version, principal, request.reason, correlation_id)
    )


@router.post(
    "/agents/{agent_id}/{version}/rollback",
    response_model=AgentDefinition,
    tags=["agents", "shared-runtime"],
)
def rollback_generated_agent(
    agent_id: str,
    version: str,
    request: AgentRollbackCommand,
    principal: PrincipalDependency,
    service: LifecycleServiceDependency,
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
) -> AgentDefinition:
    return _lifecycle_execute(
        lambda: service.rollback(
            agent_id,
            version,
            request.rollback_target,
            principal,
            request.reason,
            correlation_id,
        )
    )


def _lifecycle_execute[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RegistryError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database audit belum tersedia") from exc

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.runtime import (
    AgentCapabilityExecuteRequest,
    AgentCapabilityExecutionView,
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

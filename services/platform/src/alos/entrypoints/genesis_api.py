from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.registry import AgentRegistry
from alos.config import Settings, get_settings
from alos.entrypoints.api import current_principal, database_for_url
from alos.genesis import (
    GenesisDesignService,
    GenesisPipelineService,
    GenesisPipelineView,
    GenesisSubmitRequest,
    PostgresGenesisStore,
)
from alos.genesis.models import GenesisReviewCreate
from alos.security import Principal
from alos.security.authorization import AuthorizationDenied

router = APIRouter(prefix="/genesis", tags=["genesis", "design-time"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def genesis_service(settings: SettingsDependency) -> GenesisPipelineService:
    agents = AgentRegistry(settings.definitions_root)
    return GenesisPipelineService(
        GenesisDesignService(agents),
        CapabilityRegistry(settings.definitions_root),
        PostgresGenesisStore(database_for_url(settings.database_url).engine),
    )


GenesisDependency = Annotated[GenesisPipelineService, Depends(genesis_service)]


@router.post("/requests", response_model=GenesisPipelineView, status_code=201)
def submit_genesis_request(
    request: GenesisSubmitRequest,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.submit(request, principal))


@router.get("/requests/{request_id}", response_model=GenesisPipelineView)
def get_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.get(request_id, principal))


@router.post("/requests/{request_id}/reviews", response_model=GenesisPipelineView)
def review_genesis_request(
    request_id: UUID,
    request: GenesisReviewCreate,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.review(request_id, request, principal))


@router.post("/requests/{request_id}/stage", response_model=GenesisPipelineView)
def stage_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.stage(request_id, principal))


@router.post("/requests/{request_id}/release", response_model=GenesisPipelineView)
def release_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.release(request_id, principal))


def _execute(action: Callable[[], GenesisPipelineView]) -> GenesisPipelineView:
    try:
        return action()
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Genesis gate sudah diproses") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc

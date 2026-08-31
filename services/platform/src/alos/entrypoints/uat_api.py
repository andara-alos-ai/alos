from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.entrypoints.api import PrincipalDependency, SettingsDependency, database_for_url
from alos.security.authorization import AuthorizationDenied
from alos.uat import (
    UatCatalog,
    UatRunCreate,
    UatRunView,
    UatScenarioRecord,
    UatSignoffCreate,
    load_uat_catalog,
)
from alos.uat.repository import PostgresUatRepository
from alos.uat.service import UatService

router = APIRouter(prefix="/uat", tags=["controlled-pilot-uat"])


def uat_service(settings: SettingsDependency) -> UatService:
    catalog = load_uat_catalog(settings.definitions_root)
    repository = PostgresUatRepository(
        database_for_url(settings.database_url).engine,
        catalog,
    )
    return UatService(repository, catalog)


UatServiceDependency = Annotated[UatService, Depends(uat_service)]


def _handle_error(error: Exception) -> HTTPException:
    if isinstance(error, AuthorizationDenied):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, IntegrityError):
        return HTTPException(
            status_code=409,
            detail="Data UAT bertentangan dengan state yang sudah tersimpan",
        )
    if isinstance(error, ValueError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, OperationalError):
        return HTTPException(status_code=503, detail="Database belum tersedia")
    raise error


@router.get("/catalog", response_model=UatCatalog)
def get_uat_catalog(
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatCatalog:
    del principal
    return service.catalog


@router.get("/runs", response_model=tuple[UatRunView, ...])
def list_uat_runs(
    project_id: UUID,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> tuple[UatRunView, ...]:
    try:
        return service.list_runs(project_id, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.get("/runs/{uat_run_id}", response_model=UatRunView)
def get_uat_run(
    uat_run_id: UUID,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatRunView:
    try:
        return service.get_run(uat_run_id, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.post("/runs", response_model=UatRunView, status_code=201)
def create_uat_run(
    request: UatRunCreate,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatRunView:
    try:
        return service.create_run(request, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.post("/runs/{uat_run_id}/start", response_model=UatRunView)
def start_uat_run(
    uat_run_id: UUID,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatRunView:
    try:
        return service.start_run(uat_run_id, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.put(
    "/runs/{uat_run_id}/scenarios/{scenario_id}",
    response_model=UatRunView,
)
def record_uat_scenario(
    uat_run_id: UUID,
    scenario_id: str,
    request: UatScenarioRecord,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatRunView:
    try:
        return service.record_scenario(uat_run_id, scenario_id, request, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.post("/runs/{uat_run_id}/signoffs", response_model=UatRunView)
def signoff_uat_run(
    uat_run_id: UUID,
    request: UatSignoffCreate,
    principal: PrincipalDependency,
    service: UatServiceDependency,
) -> UatRunView:
    try:
        return service.signoff(uat_run_id, request, principal)
    except Exception as exc:
        raise _handle_error(exc) from exc

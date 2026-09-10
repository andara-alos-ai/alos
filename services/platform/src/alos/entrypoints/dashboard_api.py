"""Read-only executive dashboard and portfolio endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from alos.executive_dashboard import ExecutiveDashboardSnapshot
from alos.identity import HumanRole
from alos.identity.authentication import WorkspaceSummary
from alos.portfolio import DivisionsOverviewSnapshot, ProjectPortfolioSnapshot, ProjectStatus
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(tags=["dashboard"])


def _get_executive_dashboard_repository():
    from alos import main as main_module

    return main_module.get_executive_dashboard_repository()


def _get_identity_authentication_repository():
    from alos import main as main_module

    return main_module.get_identity_authentication_repository()


def _get_portfolio_repository():
    from alos import main as main_module

    return main_module.get_portfolio_repository()


@router.get("/api/v1/executive-dashboard", response_model=ExecutiveDashboardSnapshot)
def get_executive_dashboard(
    response: Response,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ExecutiveDashboardSnapshot:
    """Return a read-only company snapshot from the Director's accessible workspaces."""
    if HumanRole.DIRECTOR not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Director authority required for executive dashboard",
        )
    response.headers["Cache-Control"] = "no-store"
    return _get_executive_dashboard_repository().snapshot(
        organization_id=actor.organization_id,
        actor_user_id=actor.user_id,
        workspace_ids=actor.workspace_ids,
    )


@router.get("/api/v1/divisions/overview", response_model=DivisionsOverviewSnapshot)
def get_divisions_overview(
    response: Response,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> DivisionsOverviewSnapshot:
    """Return division health derived only from the actor's accessible workspaces."""
    response.headers["Cache-Control"] = "no-store"
    return _get_portfolio_repository().divisions_overview(
        organization_id=actor.organization_id,
        workspace_ids=actor.workspace_ids,
    )


@router.get("/api/v1/projects/portfolio", response_model=ProjectPortfolioSnapshot)
def get_project_portfolio(
    response: Response,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    division_code: Annotated[str | None, Query(max_length=40)] = None,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=160)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectPortfolioSnapshot:
    """Return the filtered project portfolio without crossing workspace boundaries."""
    if date_from and date_to and date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_to must be on or after date_from",
        )
    response.headers["Cache-Control"] = "no-store"
    return _get_portfolio_repository().project_portfolio(
        organization_id=actor.organization_id,
        workspace_ids=actor.workspace_ids,
        division_code=division_code,
        project_status=project_status,
        category=category,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/api/v1/workspaces", response_model=list[WorkspaceSummary])
def list_workspaces(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[WorkspaceSummary]:
    return _get_identity_authentication_repository().list_workspaces(
        organization_id=actor.organization_id, user_id=actor.user_id
    )

"""HTTP boundary for scoped project write operations."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status

from alos.config import get_settings
from alos.project_operations import (
    MilestoneCreateRequest,
    MilestoneRecord,
    MilestoneStatusRequest,
    ProjectConflict,
    ProjectCreateRequest,
    ProjectIssueCreateRequest,
    ProjectIssueRecord,
    ProjectIssueStatusRequest,
    ProjectNotFound,
    ProjectOperationError,
    ProjectOperationsRepository,
    ProjectRecord,
    ProjectUpdateRequest,
)
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1", tags=["projects"])


def repository() -> ProjectOperationsRepository:
    return ProjectOperationsRepository(get_settings().database_url)


def project_error(error: ProjectOperationError) -> HTTPException:
    if isinstance(error, ProjectNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ProjectConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post("/projects", response_model=ProjectRecord, status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ProjectRecord:
    try:
        return repository().create_project(actor, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error


@router.patch("/projects/{project_id}", response_model=ProjectRecord)
def update_project(
    project_id: UUID,
    request: ProjectUpdateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ProjectRecord:
    try:
        return repository().update_project(actor, project_id, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> Response:
    try:
        repository().delete_project(actor, project_id, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_project_milestone(
    project_id: UUID,
    request: MilestoneCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> MilestoneRecord:
    try:
        return repository().create_milestone(actor, project_id, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error


@router.patch("/project-milestones/{milestone_id}/status", response_model=MilestoneRecord)
def update_project_milestone(
    milestone_id: UUID,
    request: MilestoneStatusRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> MilestoneRecord:
    try:
        return repository().update_milestone(actor, milestone_id, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error


@router.post(
    "/project-issues",
    response_model=ProjectIssueRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_project_issue(
    request: ProjectIssueCreateRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ProjectIssueRecord:
    try:
        return repository().create_issue(actor, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error


@router.patch("/project-issues/{issue_id}/status", response_model=ProjectIssueRecord)
def update_project_issue(
    issue_id: UUID,
    request: ProjectIssueStatusRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ProjectIssueRecord:
    try:
        return repository().update_issue(actor, issue_id, request, uuid4())
    except ProjectOperationError as error:
        raise project_error(error) from error

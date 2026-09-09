"""Multi-source document intelligence endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from alos.config import get_settings
from alos.documents.intelligence import (
    DocumentComparisonRequest,
    DocumentComparisonResult,
    DocumentIntelligenceError,
    DocumentIntelligenceRepository,
    DocumentRevisionDraft,
    DocumentRevisionDraftRequest,
)
from alos.entrypoints.operational_api import correlation_id
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/documents", tags=["Document intelligence"])


def repository() -> DocumentIntelligenceRepository:
    return DocumentIntelligenceRepository(get_settings().database_url)


@router.post("/compare", response_model=DocumentComparisonResult)
def compare_documents(
    request: DocumentComparisonRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> DocumentComparisonResult:
    try:
        return repository().compare(actor, request, correlation_id=correlation)
    except DocumentIntelligenceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/{document_id}/revision-drafts", response_model=DocumentRevisionDraft)
def create_revision_draft(
    document_id: UUID,
    request: DocumentRevisionDraftRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    correlation: Annotated[UUID, Depends(correlation_id)],
) -> DocumentRevisionDraft:
    try:
        return repository().create_revision_draft(
            actor, document_id, request, correlation_id=correlation
        )
    except DocumentIntelligenceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


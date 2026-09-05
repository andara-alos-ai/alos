"""Governed, source-bound document analysis for Genesis.

This is deliberately a deterministic first step. It binds a Director's
question to an internal, approved document and produces a reviewable DRAFT.
It does not call a model, modify the source document, research externally, or
create/activate an Agent Contract.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alos.documents.center import (
    DocumentCenterRepository,
    DocumentConflictError,
    DocumentDetail,
    DocumentDraftRequest,
    DocumentRecord,
)
from alos.genesis.history import (
    GenesisArtifactRecord,
    GenesisConversationRecord,
    GenesisConversationRequest,
    GenesisHistoryRepository,
)


class GenesisDocumentAnalysisError(RuntimeError):
    """A safe failure while creating a source-bound Genesis analysis."""


class GenesisDocumentAnalysisRequest(BaseModel):
    """A Director's request to analyse one canonical internal document."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    source_document_id: UUID
    prompt: str = Field(min_length=20, max_length=10_000)


class GenesisDocumentSourceReference(BaseModel):
    document_id: UUID
    title: str
    version_number: int
    content_sha256: str
    status: str
    classification: str


class GenesisDocumentAnalysisResult(BaseModel):
    conversation: GenesisConversationRecord
    source: GenesisDocumentSourceReference
    analysis: GenesisArtifactRecord
    draft: DocumentRecord


class GenesisDocumentAnalysisService:
    """Create the first governed Genesis artifact from one source document."""

    def __init__(
        self,
        documents: DocumentCenterRepository,
        history: GenesisHistoryRepository,
    ) -> None:
        self._documents = documents
        self._history = history

    def create_analysis(
        self,
        request: GenesisDocumentAnalysisRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentAnalysisResult:
        source = self._documents.get_document(
            request.source_document_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        self._validate_source(source, request)
        source_reference = GenesisDocumentSourceReference(
            document_id=source.document.document_id,
            title=source.document.title,
            version_number=source.document.version_number,
            content_sha256=source.content_sha256,
            status=source.document.status,
            classification=source.document.classification,
        )
        conversation = self._history.create_conversation(
            GenesisConversationRequest(workspace_id=request.workspace_id),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        self._history.record_requirement(
            conversation.conversation_id,
            request.prompt,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        analysis = self._history.record_system_artifact(
            conversation.conversation_id,
            "ANALYSIS",
            _analysis_artifact_content(source_reference, request.prompt, source.content),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        draft = self._documents.create_genesis_analysis_draft(
            DocumentDraftRequest(
                workspace_id=request.workspace_id,
                title=_draft_title(source_reference.title),
                content=_analysis_draft_content(source_reference, request.prompt),
                category="GENESIS_ANALYSIS",
                classification=source.document.classification,
            ),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            conversation_id=conversation.conversation_id,
        )
        return GenesisDocumentAnalysisResult(
            conversation=conversation,
            source=source_reference,
            analysis=analysis,
            draft=draft,
        )

    @staticmethod
    def _validate_source(
        source: DocumentDetail, request: GenesisDocumentAnalysisRequest
    ) -> None:
        if source.document.workspace_id != request.workspace_id:
            raise GenesisDocumentAnalysisError(
                "source document must belong to the requested workspace"
            )
        if source.document.origin != "MANUAL":
            raise GenesisDocumentAnalysisError(
                "Genesis analysis requires a canonical internal source document"
            )
        if source.document.status not in {"APPROVED", "ACTIVE"}:
            raise DocumentConflictError(
                "source document must be APPROVED or ACTIVE before Genesis can read it"
            )


def _analysis_artifact_content(
    source: GenesisDocumentSourceReference, prompt: str, content: str
) -> dict[str, Any]:
    """Return source facts only; semantic R&D needs a later approved step."""

    return {
        "kind": "DOCUMENT_ANALYSIS",
        "source": source.model_dump(mode="json"),
        "prompt": prompt.strip(),
        "reading": {
            "content_characters": len(content),
            "source_bound": True,
            "source_modified": False,
        },
        "status": "DRAFT_FOR_HUMAN_REVIEW",
        "next_stage": "RND_RECOMMENDATION",
        "limitations": [
            "No external research was performed.",
            "No model inference was performed.",
            "No semantic conclusion is treated as approved without human review.",
        ],
    }


def _draft_title(source_title: str) -> str:
    prefix = "Analisis Genesis — "
    return f"{prefix}{source_title}"[:200]


def _analysis_draft_content(
    source: GenesisDocumentSourceReference, prompt: str
) -> str:
    return "\n".join(
        (
            f"# {_draft_title(source.title)}",
            "",
            "## Permintaan Direktur",
            prompt.strip(),
            "",
            "## Sumber terikat (read-only)",
            f"- Dokumen: {source.title}",
            f"- Document ID: {source.document_id}",
            f"- Versi: {source.version_number}",
            f"- SHA-256: {source.content_sha256}",
            f"- Status saat dibaca: {source.status}",
            f"- Klasifikasi: {source.classification}",
            "",
            "## Hasil pemeriksaan awal",
            "Sumber berhasil diikat ke analisis ini. Belum ada kesimpulan substantif,",
            "riset eksternal, atau perubahan terhadap dokumen sumber.",
            "",
            "## Checklist sebelum R&D",
            "- [ ] Checker independen memverifikasi versi dan SHA sumber.",
            "- [ ] Owner menegaskan ruang lingkup pertanyaan Direktur.",
            "- [ ] Reviewer menilai apakah R&D internal atau eksternal diperlukan.",
            "",
            "## Batasan",
            "Draft ini bukan persetujuan, bukan perubahan dokumen sumber, dan bukan",
            "instruksi untuk membuat atau mengaktifkan agent.",
        )
    )

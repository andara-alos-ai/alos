"""Governed, source-bound document analysis for Genesis.

This is deliberately a deterministic first step. It binds a Director's
question to an internal, approved document and produces a reviewable DRAFT.
It does not call a model, modify the source document, research externally, or
create/activate an Agent Contract.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alos.documents.center import (
    DocumentCenterRepository,
    DocumentClassification,
    DocumentConflictError,
    DocumentDetail,
    DocumentDraftRequest,
    DocumentRecord,
)
from alos.genesis.document_workflow import (
    GenesisAgentProposalRequest,
    GenesisApprovalHandoffRequest,
    GenesisCompletionDraftRequest,
    GenesisDocumentResearchRequest,
    GenesisDocumentWorkflowRecord,
    GenesisDocumentWorkflowRepository,
)
from alos.genesis.history import (
    GenesisArtifactRecord,
    GenesisConversationRecord,
    GenesisConversationRequest,
    GenesisHistoryRepository,
)
from alos.genesis.semantic_analysis import (
    GenesisSemanticAnalysisError,
    GenesisSemanticAnalysisResult,
    GenesisSemanticAnalyzer,
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
    classification: DocumentClassification


class GenesisDocumentAnalysisResult(BaseModel):
    conversation: GenesisConversationRecord
    source: GenesisDocumentSourceReference
    analysis: GenesisArtifactRecord
    draft: DocumentRecord
    workflow: GenesisDocumentWorkflowRecord
    semantic: GenesisSemanticAnalysisResult | None = None


class GenesisDocumentWorkflowStageResult(BaseModel):
    workflow: GenesisDocumentWorkflowRecord
    source: GenesisDocumentSourceReference
    artifact: GenesisArtifactRecord
    draft: DocumentRecord | None


class GenesisDocumentAnalysisService:
    """Create the first governed Genesis artifact from one source document."""

    def __init__(
        self,
        documents: DocumentCenterRepository,
        history: GenesisHistoryRepository,
        workflows: GenesisDocumentWorkflowRepository,
        semantic_analyzer: GenesisSemanticAnalyzer | None = None,
    ) -> None:
        self._documents = documents
        self._history = history
        self._workflows = workflows
        self._semantic_analyzer = semantic_analyzer

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
        source_reference = _source_reference(source)
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
        semantic: GenesisSemanticAnalysisResult | None = None
        try:
            semantic = self._create_semantic_analysis(
                source=source,
                source_reference=source_reference,
                prompt=request.prompt,
                organization_id=organization_id,
                workspace_id=request.workspace_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            analysis = self._history.record_system_artifact(
                conversation.conversation_id,
                "ANALYSIS",
                _analysis_artifact_content(
                    source_reference,
                    request.prompt,
                    source.content,
                    semantic,
                ),
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            draft = self._documents.create_genesis_analysis_draft(
                DocumentDraftRequest(
                    workspace_id=request.workspace_id,
                    title=_draft_title(source_reference.title),
                    content=_analysis_draft_content(source_reference, request.prompt, semantic),
                    category="GENESIS_ANALYSIS",
                    classification=source.document.classification,
                ),
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                conversation_id=conversation.conversation_id,
            )
            workflow = self._workflows.create(
                organization_id=organization_id,
                workspace_id=request.workspace_id,
                conversation_id=conversation.conversation_id,
                source_document_id=source_reference.document_id,
                source_version_number=source_reference.version_number,
                source_content_sha256=source_reference.content_sha256,
                analysis_document_id=draft.document_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            if semantic is not None:
                self._semantic_analyzer_complete(
                    semantic,
                    analysis_artifact_id=analysis.artifact_id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    correlation_id=correlation_id,
                )
        except Exception as error:
            self._semantic_analyzer_fail(
                semantic,
                error,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            raise
        return GenesisDocumentAnalysisResult(
            conversation=conversation,
            source=source_reference,
            analysis=analysis,
            draft=draft,
            workflow=workflow,
            semantic=semantic,
        )

    def _create_semantic_analysis(
        self,
        *,
        source: DocumentDetail,
        source_reference: GenesisDocumentSourceReference,
        prompt: str,
        organization_id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisSemanticAnalysisResult | None:
        if self._semantic_analyzer is None:
            return None
        if source_reference.classification != "INTERNAL":
            raise GenesisDocumentAnalysisError(
                "semantic Genesis analysis only permits INTERNAL source documents"
            )
        try:
            return self._semantic_analyzer.analyze(
                organization_id=organization_id,
                workspace_id=workspace_id,
                source_document_id=source_reference.document_id,
                source_version_number=source_reference.version_number,
                source_content_sha256=source_reference.content_sha256,
                source_title=source_reference.title,
                source_content=source.content,
                prompt=prompt,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
        except GenesisSemanticAnalysisError as error:
            raise GenesisDocumentAnalysisError(str(error)) from error

    def _semantic_analyzer_complete(
        self,
        semantic: GenesisSemanticAnalysisResult,
        *,
        analysis_artifact_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        if self._semantic_analyzer is None:
            raise AssertionError("semantic analyzer must exist when completing semantic output")
        try:
            self._semantic_analyzer.complete(
                semantic,
                analysis_artifact_id=analysis_artifact_id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
        except GenesisSemanticAnalysisError as error:
            raise GenesisDocumentAnalysisError(str(error)) from error

    def _semantic_analyzer_fail(
        self,
        semantic: GenesisSemanticAnalysisResult | None,
        error: Exception,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        if semantic is None or self._semantic_analyzer is None:
            return
        try:
            self._semantic_analyzer.fail(
                semantic,
                error,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
        except GenesisSemanticAnalysisError:
            # Preserve the original persistence failure; the run is still auditable.
            return

    def create_rnd(
        self,
        workflow_id: UUID,
        request: GenesisDocumentResearchRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowStageResult:
        workflow, source = self._workflow_source(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        self._require_workflow_status(workflow, "ANALYSIS_DRAFT")
        artifact = self._history.record_system_artifact(
            workflow.conversation_id,
            "BLUEPRINT",
            _rnd_artifact_content(workflow, source, request.focus),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        draft = self._documents.create_genesis_workflow_draft(
            DocumentDraftRequest(
                workspace_id=workflow.workspace_id,
                title=_workflow_title("R&D Genesis", source.title),
                content=_rnd_draft_content(source, request.focus),
                category="GENESIS_RND",
                classification=source.classification,
            ),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            conversation_id=workflow.conversation_id,
            audit_action="GENESIS_DOCUMENT_RND_DRAFT_CREATED",
            audit_reason="Genesis prepared a bounded R&D draft that remains DRAFT",
            requires_document_review=False,
        )
        updated = self._workflows.advance(
            workflow_id,
            expected_status="ANALYSIS_DRAFT",
            next_status="RND_DRAFT",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            audit_action="GENESIS_DOCUMENT_WORKFLOW_RND_RECORDED",
            audit_reason="Genesis recorded a bounded R&D draft for human review",
            metadata={
                "rnd_document_id": str(draft.document_id),
                "artifact_id": str(artifact.artifact_id),
            },
            draft_column="rnd_document_id",
            draft_document_id=draft.document_id,
        )
        return GenesisDocumentWorkflowStageResult(
            workflow=updated, source=source, artifact=artifact, draft=draft
        )

    def create_checklist(
        self,
        workflow_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowStageResult:
        workflow, source = self._workflow_source(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        self._require_workflow_status(workflow, "RND_DRAFT")
        artifact = self._history.record_system_artifact(
            workflow.conversation_id,
            "TEST_PLAN",
            _checklist_artifact_content(workflow, source),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        draft = self._documents.create_genesis_workflow_draft(
            DocumentDraftRequest(
                workspace_id=workflow.workspace_id,
                title=_workflow_title("Checklist Genesis", source.title),
                content=_checklist_draft_content(source),
                category="GENESIS_CHECKLIST",
                classification=source.classification,
            ),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            conversation_id=workflow.conversation_id,
            audit_action="GENESIS_DOCUMENT_CHECKLIST_DRAFT_CREATED",
            audit_reason="Genesis prepared a remediation checklist draft that remains DRAFT",
            requires_document_review=False,
        )
        updated = self._workflows.advance(
            workflow_id,
            expected_status="RND_DRAFT",
            next_status="CHECKLIST_DRAFT",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            audit_action="GENESIS_DOCUMENT_WORKFLOW_CHECKLIST_RECORDED",
            audit_reason="Genesis recorded a remediation checklist for human review",
            metadata={
                "checklist_document_id": str(draft.document_id),
                "artifact_id": str(artifact.artifact_id),
            },
            draft_column="checklist_document_id",
            draft_document_id=draft.document_id,
        )
        return GenesisDocumentWorkflowStageResult(
            workflow=updated, source=source, artifact=artifact, draft=draft
        )

    def create_completion_draft(
        self,
        workflow_id: UUID,
        request: GenesisCompletionDraftRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowStageResult:
        workflow, source = self._workflow_source(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        self._require_workflow_status(workflow, "CHECKLIST_DRAFT")
        artifact = self._history.record_system_artifact(
            workflow.conversation_id,
            "DIFF",
            _completion_artifact_content(workflow, source, request.completion_intent),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        draft = self._documents.create_genesis_workflow_draft(
            DocumentDraftRequest(
                workspace_id=workflow.workspace_id,
                title=_workflow_title("Pelengkapan Genesis", source.title),
                content=_completion_draft_content(source, request.completion_intent),
                category="GENESIS_COMPLETION",
                classification=source.classification,
            ),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            conversation_id=workflow.conversation_id,
            audit_action="GENESIS_DOCUMENT_COMPLETION_DRAFT_CREATED",
            audit_reason="Genesis prepared a remediation draft that remains DRAFT",
            requires_document_review=True,
        )
        updated = self._workflows.advance(
            workflow_id,
            expected_status="CHECKLIST_DRAFT",
            next_status="COMPLETION_DRAFT",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            audit_action="GENESIS_DOCUMENT_WORKFLOW_COMPLETION_RECORDED",
            audit_reason="Genesis recorded a remediation draft for human review",
            metadata={
                "completion_document_id": str(draft.document_id),
                "artifact_id": str(artifact.artifact_id),
            },
            draft_column="completion_document_id",
            draft_document_id=draft.document_id,
        )
        return GenesisDocumentWorkflowStageResult(
            workflow=updated, source=source, artifact=artifact, draft=draft
        )

    def create_agent_proposal(
        self,
        workflow_id: UUID,
        request: GenesisAgentProposalRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowStageResult:
        workflow, source = self._workflow_source(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        self._require_workflow_status(workflow, "COMPLETION_DRAFT")
        artifact = self._history.record_system_artifact(
            workflow.conversation_id,
            "CONTRACT",
            _agent_proposal_artifact_content(workflow, source, request),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        updated = self._workflows.advance(
            workflow_id,
            expected_status="COMPLETION_DRAFT",
            next_status="AGENT_PROPOSAL_DRAFT",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            audit_action="GENESIS_DOCUMENT_WORKFLOW_AGENT_PROPOSAL_RECORDED",
            audit_reason="Genesis recorded an agent proposal that is not an Agent Contract",
            metadata={"artifact_id": str(artifact.artifact_id)},
            artifact_column="agent_proposal_artifact_id",
            artifact_id=artifact.artifact_id,
        )
        return GenesisDocumentWorkflowStageResult(
            workflow=updated, source=source, artifact=artifact, draft=None
        )

    def create_governance_handoff(
        self,
        workflow_id: UUID,
        request: GenesisApprovalHandoffRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowStageResult:
        workflow, source = self._workflow_source(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        self._require_workflow_status(workflow, "AGENT_PROPOSAL_DRAFT")
        artifact = self._history.record_system_artifact(
            workflow.conversation_id,
            "RELEASE_PROPOSAL",
            _governance_handoff_artifact_content(workflow, source, request.note),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        updated = self._workflows.advance(
            workflow_id,
            expected_status="AGENT_PROPOSAL_DRAFT",
            next_status="READY_FOR_GOVERNANCE",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            audit_action="GENESIS_DOCUMENT_WORKFLOW_GOVERNANCE_HANDOFF_RECORDED",
            audit_reason="GENESIS recorded a handoff to the governed agent release lifecycle",
            metadata={"artifact_id": str(artifact.artifact_id), "note": request.note.strip()},
            artifact_column="governance_handoff_artifact_id",
            artifact_id=artifact.artifact_id,
        )
        return GenesisDocumentWorkflowStageResult(
            workflow=updated, source=source, artifact=artifact, draft=None
        )

    def _workflow_source(
        self,
        workflow_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> tuple[GenesisDocumentWorkflowRecord, GenesisDocumentSourceReference]:
        workflow = self._workflows.get(
            workflow_id, organization_id=organization_id, actor_user_id=actor_user_id
        )
        source = self._documents.get_document(
            workflow.source_document_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        source_reference = _source_reference(source)
        if (
            source_reference.version_number != workflow.source_version_number
            or source_reference.content_sha256 != workflow.source_content_sha256
        ):
            raise GenesisDocumentAnalysisError(
                "source document changed; start a new Genesis analysis from the latest "
                "approved version"
            )
        self._validate_source(
            source,
            GenesisDocumentAnalysisRequest(
                workspace_id=workflow.workspace_id,
                source_document_id=workflow.source_document_id,
                prompt="Source binding verification for a governed Genesis workflow.",
            ),
        )
        return workflow, source_reference

    @staticmethod
    def _require_workflow_status(
        workflow: GenesisDocumentWorkflowRecord, expected_status: str
    ) -> None:
        if workflow.status != expected_status:
            raise GenesisDocumentAnalysisError(
                f"workflow must be {expected_status} before the requested stage can be created"
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
    source: GenesisDocumentSourceReference,
    prompt: str,
    content: str,
    semantic: GenesisSemanticAnalysisResult | None,
) -> dict[str, Any]:
    """Return immutable source binding plus an optional model answer for review."""

    artifact: dict[str, Any] = {
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
            "No semantic conclusion is treated as approved without human review.",
        ],
    }
    if semantic is None:
        artifact["model_execution"] = {
            "mode": "DETERMINISTIC_SOURCE_BINDING",
            "status": "NOT_ENABLED",
            "reason": "Semantic Model Gateway is not enabled for this environment.",
        }
        artifact["limitations"].append("No model inference was performed.")
    else:
        artifact["model_execution"] = {
            "mode": "SOURCE_BOUND_MODEL_GATEWAY",
            "analysis_run_id": str(semantic.analysis_run_id),
            "provider": semantic.provider,
            "model": semantic.model,
            "input_tokens": semantic.input_tokens,
            "output_tokens": semantic.output_tokens,
            "latency_milliseconds": semantic.latency_milliseconds,
            "estimated_cost_usd": str(semantic.estimated_cost_usd),
            "provider_storage": "store=false",
            "tools": "none",
            "external_web": False,
        }
        artifact["answer"] = semantic.answer
    return artifact


def _draft_title(source_title: str) -> str:
    prefix = "Analisis Genesis — "
    return f"{prefix}{source_title}"[:200]


def _analysis_draft_content(
    source: GenesisDocumentSourceReference,
    prompt: str,
    semantic: GenesisSemanticAnalysisResult | None,
) -> str:
    lines = [
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
    ]
    if semantic is None:
        lines.extend(
            (
                "Sumber berhasil diikat ke analisis ini. Belum ada kesimpulan substantif,",
                "riset eksternal, atau perubahan terhadap dokumen sumber.",
            )
        )
    else:
        lines.extend(
            (
                "Hasil berikut dibuat melalui Model Gateway hanya dari sumber terikat di atas.",
                "Semua kesimpulan dan rekomendasi tetap DRAFT yang wajib diperiksa manusia.",
                "",
                semantic.answer,
            )
        )
    lines.extend(
        (
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
    return "\n".join(lines)


def _source_reference(source: DocumentDetail) -> GenesisDocumentSourceReference:
    return GenesisDocumentSourceReference(
        document_id=source.document.document_id,
        title=source.document.title,
        version_number=source.document.version_number,
        content_sha256=source.content_sha256,
        status=source.document.status,
        classification=source.document.classification,
    )


def _workflow_title(prefix: str, source_title: str) -> str:
    return f"{prefix} — {source_title}"[:200]


def _workflow_source_payload(
    workflow: GenesisDocumentWorkflowRecord, source: GenesisDocumentSourceReference
) -> dict[str, Any]:
    return {
        "workflow_id": str(workflow.workflow_id),
        "source": source.model_dump(mode="json"),
        "source_bound": True,
        "source_modified": False,
    }


def _rnd_artifact_content(
    workflow: GenesisDocumentWorkflowRecord,
    source: GenesisDocumentSourceReference,
    focus: str,
) -> dict[str, Any]:
    return {
        "kind": "RND_RECOMMENDATION",
        **_workflow_source_payload(workflow, source),
        "focus": focus.strip(),
        "research_tracks": [
            "Kelengkapan dan konsistensi dokumen internal.",
            "Bukti, owner, KPI, dan risiko yang perlu ditinjau manusia.",
            "Kebutuhan riset lanjutan yang harus disetujui sebelum sumber eksternal dibaca.",
        ],
        "status": "DRAFT_FOR_HUMAN_REVIEW",
        "limitations": [
            "No external research was performed.",
            "No model inference was performed.",
            "This is not an approved business recommendation.",
        ],
    }


def _rnd_draft_content(source: GenesisDocumentSourceReference, focus: str) -> str:
    return "\n".join(
        (
            f"# {_workflow_title('R&D Genesis', source.title)}",
            "",
            "## Fokus R&D yang diminta",
            focus.strip(),
            "",
            "## Landasan sumber",
            f"- Dokumen: {source.title}",
            f"- Versi terikat: {source.version_number}",
            f"- SHA-256: {source.content_sha256}",
            "",
            "## Area yang perlu diteliti",
            "1. Kelengkapan ruang lingkup, owner, KPI, dan risiko.",
            "2. Bukti internal yang mendukung atau membatasi kesimpulan.",
            "3. Pertanyaan riset eksternal yang memerlukan persetujuan sumber dan biaya.",
            "",
            "## Batasan",
            "R&D ini masih kerangka DRAFT. Genesis belum melakukan browsing, membaca sumber",
            "eksternal, atau menyatakan rekomendasi bisnis sebagai fakta.",
        )
    )


def _checklist_items() -> list[dict[str, str]]:
    return [
        {
            "key": "SOURCE_INTEGRITY",
            "label": "Versi dan SHA sumber diverifikasi checker independen.",
        },
        {
            "key": "SCOPE_OWNER",
            "label": "Owner mengonfirmasi ruang lingkup, target, dan batas keputusan.",
        },
        {
            "key": "KPI_RISK",
            "label": "KPI, risiko, asumsi, dan bukti pendukung dinilai manusia.",
        },
        {
            "key": "RESEARCH_AUTHORITY",
            "label": "Kebutuhan sumber eksternal, jika ada, mendapat otorisasi terpisah.",
        },
    ]


def _checklist_artifact_content(
    workflow: GenesisDocumentWorkflowRecord, source: GenesisDocumentSourceReference
) -> dict[str, Any]:
    return {
        "kind": "REMEDIATION_CHECKLIST",
        **_workflow_source_payload(workflow, source),
        "items": _checklist_items(),
        "status": "DRAFT_FOR_HUMAN_REVIEW",
        "completion_boundary": "Only a human checker can mark document checklist items complete.",
    }


def _checklist_draft_content(source: GenesisDocumentSourceReference) -> str:
    items = tuple(f"- [ ] {item['label']}" for item in _checklist_items())
    return "\n".join(
        (
            f"# {_workflow_title('Checklist Genesis', source.title)}",
            "",
            "## Sumber terikat",
            f"- Dokumen: {source.title}",
            f"- Versi: {source.version_number}",
            f"- SHA-256: {source.content_sha256}",
            "",
            "## Checklist perbaikan",
            *items,
            "",
            "## Catatan kontrol",
            "Checklist ini adalah DRAFT. Penyelesaian dan bukti tiap item harus diperiksa",
            "oleh manusia independen sebelum dokumen apa pun diajukan untuk review.",
        )
    )


def _completion_artifact_content(
    workflow: GenesisDocumentWorkflowRecord,
    source: GenesisDocumentSourceReference,
    completion_intent: str,
) -> dict[str, Any]:
    return {
        "kind": "COMPLETION_DRAFT",
        **_workflow_source_payload(workflow, source),
        "completion_intent": completion_intent.strip(),
        "checklist_keys": [item["key"] for item in _checklist_items()],
        "status": "DRAFT_FOR_HUMAN_REVIEW",
        "limitations": [
            "The completion draft does not alter the source document.",
            "Human owners must supply and verify substantive information.",
        ],
    }


def _completion_draft_content(
    source: GenesisDocumentSourceReference, completion_intent: str
) -> str:
    return "\n".join(
        (
            f"# {_workflow_title('Pelengkapan Genesis', source.title)}",
            "",
            "## Tujuan pelengkapan",
            completion_intent.strip(),
            "",
            "## Hubungan ke sumber",
            f"Draft ini melengkapi, bukan mengubah, {source.title} v{source.version_number}.",
            f"SHA sumber: {source.content_sha256}",
            "",
            "## Isian yang harus dilengkapi owner",
            "### Ruang lingkup dan owner",
            "[Lengkapi owner, PIC/backup, batas kewenangan, dan target.]",
            "",
            "### KPI, asumsi, dan risiko",
            "[Lengkapi indikator, baseline, target, asumsi, risiko, dan mitigasi.]",
            "",
            "### Evidence dan keputusan",
            "[Tambahkan evidence terverifikasi serta keputusan manusia yang relevan.]",
            "",
            "## Batasan",
            "Genesis tidak mengesahkan isian ini dan tidak memperbarui dokumen sumber "
            "secara otomatis.",
        )
    )


def _agent_proposal_artifact_content(
    workflow: GenesisDocumentWorkflowRecord,
    source: GenesisDocumentSourceReference,
    request: GenesisAgentProposalRequest,
) -> dict[str, Any]:
    agent_key = _suggest_agent_key(source.title)
    name = request.name.strip() if request.name else f"{source.title} Advisor"[:200]
    return {
        "kind": "AGENT_PROPOSAL",
        **_workflow_source_payload(workflow, source),
        "proposal": {
            "agent_key": agent_key,
            "name": name,
            "objective": request.objective.strip(),
            "risk_level": "LOW",
            "approval_required": True,
            "proposed_mode": "READ_ONLY_DRAFT",
            "tool_keys": [],
            "permission_keys": [],
            "forbidden_actions": [
                "Do not modify source documents.",
                "Do not take external actions.",
                "Do not activate, release, or approve any Agent Contract.",
            ],
        },
        "status": "AGENT_CONTRACT_DRAFT_REQUESTED",
        "next_owner": "AGENT_GOVERNANCE",
        "required_human_controls": [
            "Backend policy resolves capabilities, tools, permissions, and risk.",
            "Independent tests, business review, technical review, and approval are mandatory.",
        ],
    }


def _suggest_agent_key(source_title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", source_title).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Z0-9]+", ascii_title.upper())[:5]
    suffix = "_".join(words) or "DOCUMENT_ADVISOR"
    return f"GENESIS_{suffix}"[:80].rstrip("_")


def _governance_handoff_artifact_content(
    workflow: GenesisDocumentWorkflowRecord,
    source: GenesisDocumentSourceReference,
    note: str,
) -> dict[str, Any]:
    return {
        "kind": "GOVERNANCE_HANDOFF",
        **_workflow_source_payload(workflow, source),
        "director_note": note.strip(),
        "status": "PENDING_GOVERNANCE_REVIEW",
        "handoff": {
            "next_owner": "AGENT_GOVERNANCE",
            "required_action": "Review the linked Agent Contract and its generated tests.",
            "governance_requirements": [
                "Approve explicit tool and permission controls independently.",
                "Run the required positive, negative, regression, security, and recovery tests.",
                "Record independent business, technical, and final approval decisions.",
            ],
        },
    }

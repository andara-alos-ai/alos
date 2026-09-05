"""Versioned Document Center with human checklist and approval boundaries."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.persistence.database import psycopg_url

DocumentStatus = Literal["DRAFT", "IN_REVIEW", "APPROVED", "ACTIVE", "REJECTED", "ARCHIVED"]
DocumentOrigin = Literal["MANUAL", "GENESIS"]
DocumentClassification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
ChecklistStatus = Literal["PENDING", "PASSED", "WAIVED"]


class DocumentCenterError(RuntimeError):
    """A safe Document Center domain failure."""


class DocumentNotFoundError(DocumentCenterError):
    """The requested document is not visible in the actor workspace."""


class DocumentConflictError(DocumentCenterError):
    """The requested document transition is not valid."""


class DocumentDraftRequest(BaseModel):
    """A human-created canonical document draft."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    category: str = Field(default="GENERAL", pattern=r"^[A-Z][A-Z0-9_ ]{1,79}$")
    classification: DocumentClassification = "INTERNAL"


class GenesisDocumentDraftRequest(BaseModel):
    """A requirement from which Genesis prepares a governed document skeleton."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    title: str = Field(min_length=3, max_length=200)
    requirement: str = Field(min_length=20, max_length=10_000)
    category: str = Field(default="GENERAL", pattern=r"^[A-Z][A-Z0-9_ ]{1,79}$")
    classification: DocumentClassification = "INTERNAL"


class ChecklistCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=3, max_length=2_000)


class DocumentReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=3, max_length=2_000)


class DocumentRecord(BaseModel):
    document_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_code: str | None
    genesis_conversation_id: UUID | None
    title: str
    category: str
    classification: DocumentClassification
    origin: DocumentOrigin
    status: DocumentStatus
    owner_user_id: UUID
    created_by_user_id: UUID
    version_number: int
    created_at: datetime
    updated_at: datetime


class DocumentChecklistItem(BaseModel):
    document_checklist_item_id: UUID
    check_key: str
    label: str
    check_type: Literal["AUTOMATED", "HUMAN"]
    required: bool
    status: ChecklistStatus
    notes: str | None
    completed_by_user_id: UUID | None
    completed_at: datetime | None


class DocumentReviewRecord(BaseModel):
    document_review_request_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    submitted_by_user_id: UUID
    submitted_at: datetime
    reviewer_user_id: UUID | None
    decided_at: datetime | None
    notes: str | None


class DocumentDetail(BaseModel):
    document: DocumentRecord
    content: str
    content_sha256: str
    checklist: list[DocumentChecklistItem]
    reviews: list[DocumentReviewRecord]


class DocumentCenterRepository:
    """Persist one canonical document record while keeping human gates explicit."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_draft(
        self,
        request: DocumentDraftRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> DocumentRecord:
        return self._create_draft(
            request,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            origin="MANUAL",
            genesis_conversation_id=None,
            generated_by_system=False,
            audit_actor_kind="HUMAN",
        )

    def create_genesis_draft(
        self,
        request: GenesisDocumentDraftRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        conversation_id: UUID,
    ) -> DocumentRecord:
        draft = DocumentDraftRequest(
            workspace_id=request.workspace_id,
            title=request.title,
            content=_genesis_draft_content(request.title, request.requirement),
            category=request.category,
            classification=request.classification,
        )
        return self._create_draft(
            draft,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            origin="GENESIS",
            genesis_conversation_id=conversation_id,
            generated_by_system=True,
            audit_actor_kind="SYSTEM",
        )

    def list_documents(
        self,
        workspace_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> list[DocumentRecord]:
        with self._connection() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            rows = connection.execute(
                """
                SELECT document_record.document_id, document_record.organization_id,
                       document_record.workspace_id, division.code AS division_code,
                       document_record.genesis_conversation_id, document_record.title,
                       document_record.category, document_record.classification,
                       document_record.origin, document_record.status,
                       document_record.owner_user_id, document_record.created_by_user_id,
                       document_version.version_number, document_record.created_at,
                       document_record.updated_at
                FROM documents.records AS document_record
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = document_record.division_id
                JOIN LATERAL (
                    SELECT version_number FROM documents.versions
                    WHERE document_id = document_record.document_id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) AS document_version ON true
                WHERE document_record.organization_id = %s AND document_record.workspace_id = %s
                ORDER BY document_record.updated_at DESC, document_record.document_id
                """,
                (organization_id, workspace_id),
            ).fetchall()
        return [DocumentRecord(**row) for row in rows]

    def get_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> DocumentDetail:
        with self._connection() as connection:
            document, version = self._load_document(
                connection, document_id, organization_id, actor_user_id
            )
            checks = connection.execute(
                """
                SELECT document_checklist_item_id, check_key, label, check_type, required, status,
                       notes, completed_by_user_id, completed_at
                FROM documents.checklist_items
                WHERE document_version_id = %s
                ORDER BY created_at, document_checklist_item_id
                """,
                (version["document_version_id"],),
            ).fetchall()
            reviews = connection.execute(
                """
                SELECT document_review_request_id, document_id, document_version_id, status,
                       submitted_by_user_id, submitted_at, reviewer_user_id, decided_at, notes
                FROM documents.review_requests
                WHERE document_id = %s
                ORDER BY submitted_at DESC, document_review_request_id DESC
                """,
                (document_id,),
            ).fetchall()
        return DocumentDetail(
            document=DocumentRecord(**document),
            content=version["content"],
            content_sha256=version["content_sha256"],
            checklist=[DocumentChecklistItem(**row) for row in checks],
            reviews=[DocumentReviewRecord(**row) for row in reviews],
        )

    def complete_checklist_item(
        self,
        document_id: UUID,
        check_key: str,
        request: ChecklistCompletionRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> DocumentDetail:
        with self._transaction() as connection:
            document, version = self._load_document(
                connection, document_id, organization_id, actor_user_id, for_update=True
            )
            if document["status"] != "DRAFT":
                raise DocumentConflictError(
                    "checklist can only be completed while the document is DRAFT"
                )
            if document["created_by_user_id"] == actor_user_id:
                raise DocumentConflictError("draft creator cannot complete a human checklist item")
            check = connection.execute(
                """
                SELECT document_checklist_item_id, check_type, status
                FROM documents.checklist_items
                WHERE document_version_id = %s AND check_key = %s
                FOR UPDATE
                """,
                (version["document_version_id"], check_key),
            ).fetchone()
            if check is None:
                raise DocumentNotFoundError("document checklist item is not available")
            if check["check_type"] != "HUMAN":
                raise DocumentConflictError(
                    "automated checklist items cannot be completed manually"
                )
            if check["status"] == "PASSED":
                raise DocumentConflictError("document checklist item is already completed")
            connection.execute(
                """
                UPDATE documents.checklist_items
                SET status = 'PASSED', notes = %s, completed_by_user_id = %s, completed_at = now()
                WHERE document_checklist_item_id = %s
                """,
                (request.notes, actor_user_id, check["document_checklist_item_id"]),
            )
            self._append_human_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="DOCUMENT_CHECKLIST_COMPLETED",
                entity_type="DOCUMENT",
                entity_id=document_id,
                correlation_id=correlation_id,
                reason="Independent human checker completed a required document checklist item",
                metadata={"check_key": check_key, "document_version": version["version_number"]},
            )
        return self.get_document(
            document_id, organization_id=organization_id, actor_user_id=actor_user_id
        )

    def submit_for_review(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> DocumentDetail:
        with self._transaction() as connection:
            document, version = self._load_document(
                connection, document_id, organization_id, actor_user_id, for_update=True
            )
            if document["status"] != "DRAFT":
                raise DocumentConflictError("only a DRAFT document can be submitted for review")
            if document["created_by_user_id"] != actor_user_id:
                raise DocumentConflictError(
                    "only the draft creator can submit this document for review"
                )
            incomplete = connection.execute(
                """
                SELECT check_key FROM documents.checklist_items
                WHERE document_version_id = %s AND required AND status <> 'PASSED'
                ORDER BY check_key
                """,
                (version["document_version_id"],),
            ).fetchall()
            if incomplete:
                keys = ", ".join(row["check_key"] for row in incomplete)
                raise DocumentConflictError(f"required checklist items are incomplete: {keys}")
            connection.execute(
                """
                INSERT INTO documents.review_requests (
                    document_id, document_version_id, submitted_by_user_id
                ) VALUES (%s, %s, %s)
                """,
                (document_id, version["document_version_id"], actor_user_id),
            )
            connection.execute(
                """
                UPDATE documents.records SET status = 'IN_REVIEW', updated_at = now()
                WHERE document_id = %s
                """,
                (document_id,),
            )
            self._append_human_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="DOCUMENT_SUBMITTED_FOR_REVIEW",
                entity_type="DOCUMENT",
                entity_id=document_id,
                correlation_id=correlation_id,
                reason=(
                    "Draft creator submitted a checklist-complete document for independent review"
                ),
                metadata={"document_version": version["version_number"]},
            )
        return self.get_document(
            document_id, organization_id=organization_id, actor_user_id=actor_user_id
        )

    def decide_review(
        self,
        document_id: UUID,
        request: DocumentReviewDecisionRequest,
        *,
        approved: bool,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> DocumentDetail:
        with self._transaction() as connection:
            document, version = self._load_document(
                connection, document_id, organization_id, actor_user_id, for_update=True
            )
            if document["status"] != "IN_REVIEW":
                raise DocumentConflictError("document is not waiting for review")
            if document["created_by_user_id"] == actor_user_id:
                raise DocumentConflictError("draft creator cannot decide its own document review")
            review = connection.execute(
                """
                SELECT document_review_request_id
                FROM documents.review_requests
                WHERE document_id = %s AND document_version_id = %s AND status = 'PENDING'
                ORDER BY submitted_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (document_id, version["document_version_id"]),
            ).fetchone()
            if review is None:
                raise DocumentConflictError("pending document review is not available")
            review_status = "APPROVED" if approved else "REJECTED"
            document_status = "APPROVED" if approved else "REJECTED"
            connection.execute(
                """
                UPDATE documents.review_requests
                SET status = %s, reviewer_user_id = %s, decided_at = now(), notes = %s
                WHERE document_review_request_id = %s
                """,
                (review_status, actor_user_id, request.notes, review["document_review_request_id"]),
            )
            connection.execute(
                """
                UPDATE documents.records SET status = %s, updated_at = now() WHERE document_id = %s
                """,
                (document_status, document_id),
            )
            self._append_human_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="DOCUMENT_APPROVED" if approved else "DOCUMENT_REJECTED",
                entity_type="DOCUMENT",
                entity_id=document_id,
                correlation_id=correlation_id,
                reason=(
                    "Independent human approved the document"
                    if approved
                    else "Independent human rejected the document"
                ),
                metadata={"document_version": version["version_number"]},
            )
        return self.get_document(
            document_id, organization_id=organization_id, actor_user_id=actor_user_id
        )

    def _create_draft(
        self,
        request: DocumentDraftRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        origin: DocumentOrigin,
        genesis_conversation_id: UUID | None,
        generated_by_system: bool,
        audit_actor_kind: Literal["HUMAN", "SYSTEM"],
    ) -> DocumentRecord:
        with self._transaction() as connection:
            workspace = self._require_workspace_actor(
                connection, organization_id, actor_user_id, request.workspace_id
            )
            row = connection.execute(
                """
                INSERT INTO documents.records (
                    organization_id, workspace_id, division_id, genesis_conversation_id, title,
                    category, classification, origin, owner_user_id, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, organization_id, workspace_id, division_id,
                          genesis_conversation_id, title, category, classification, origin, status,
                          owner_user_id, created_by_user_id, created_at, updated_at
                """,
                (
                    organization_id,
                    request.workspace_id,
                    workspace["division_id"],
                    genesis_conversation_id,
                    request.title.strip(),
                    request.category,
                    request.classification,
                    origin,
                    actor_user_id,
                    actor_user_id,
                ),
            ).fetchone()
            if row is None:
                raise DocumentCenterError("document draft could not be created")
            version = connection.execute(
                """
                INSERT INTO documents.versions (
                    document_id, version_number, content, content_sha256, created_by_user_id,
                    generated_by_system
                ) VALUES (%s, 1, %s, %s, %s, %s)
                RETURNING document_version_id, version_number
                """,
                (
                    row["document_id"],
                    request.content.strip(),
                    _digest(request.content.strip()),
                    actor_user_id,
                    generated_by_system,
                ),
            ).fetchone()
            if version is None:
                raise DocumentCenterError("document draft version could not be created")
            self._create_default_checklist(connection, version["document_version_id"])
            metadata = {"origin": origin, "document_version": version["version_number"]}
            if genesis_conversation_id is not None:
                metadata["conversation_id"] = str(genesis_conversation_id)
            if audit_actor_kind == "SYSTEM":
                self._append_system_audit(
                    connection,
                    organization_id=organization_id,
                    action="GENESIS_DOCUMENT_DRAFT_CREATED",
                    entity_type="DOCUMENT",
                    entity_id=row["document_id"],
                    correlation_id=correlation_id,
                    reason="Genesis prepared a governed document skeleton that remains DRAFT",
                    metadata=metadata,
                )
            else:
                self._append_human_audit(
                    connection,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="DOCUMENT_DRAFT_CREATED",
                    entity_type="DOCUMENT",
                    entity_id=row["document_id"],
                    correlation_id=correlation_id,
                    reason="Human created a canonical Document Center draft",
                    metadata=metadata,
                )
        return DocumentRecord(
            **row,
            division_code=workspace["division_code"],
            version_number=version["version_number"],
        )

    @staticmethod
    def _create_default_checklist(
        connection: psycopg.Connection[Any], document_version_id: UUID
    ) -> None:
        checks = (
            (
                "DOCUMENT_METADATA",
                "Metadata dokumen lengkap",
                "AUTOMATED",
                "PASSED",
                "Judul, kategori, owner, dan klasifikasi tersedia.",
            ),
            (
                "DRAFT_CONTENT",
                "Konten draft tersedia",
                "AUTOMATED",
                "PASSED",
                "Versi draft tersimpan dan memiliki digest.",
            ),
            (
                "SOURCE_EVIDENCE",
                "Evidence/sumber diperiksa atau dinyatakan tidak diperlukan",
                "HUMAN",
                "PENDING",
                None,
            ),
            (
                "SCOPE_OWNER",
                "Ruang lingkup dan owner dikonfirmasi",
                "HUMAN",
                "PENDING",
                None,
            ),
            (
                "RISK_CLASSIFICATION",
                "Klasifikasi dan risiko dokumen ditinjau",
                "HUMAN",
                "PENDING",
                None,
            ),
        )
        for check in checks:
            connection.execute(
                """
                INSERT INTO documents.checklist_items (
                    document_version_id, check_key, label, check_type, status, notes
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (document_version_id, *check),
            )

    def _load_document(
        self,
        connection: psycopg.Connection[Any],
        document_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        *,
        for_update: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        lock = " FOR UPDATE OF document_record" if for_update else ""
        row = connection.execute(
            f"""
            SELECT document_record.document_id, document_record.organization_id,
                   document_record.workspace_id, division.code AS division_code,
                   document_record.genesis_conversation_id, document_record.title,
                   document_record.category, document_record.classification,
                   document_record.origin, document_record.status,
                   document_record.owner_user_id, document_record.created_by_user_id,
                   document_version.document_version_id, document_version.version_number,
                   document_version.content, document_version.content_sha256,
                   document_record.created_at, document_record.updated_at
            FROM documents.records AS document_record
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = document_record.workspace_id
            LEFT JOIN identity.divisions AS division
              ON division.division_id = document_record.division_id
            JOIN LATERAL (
                SELECT document_version_id, version_number, content, content_sha256
                FROM documents.versions
                WHERE document_id = document_record.document_id
                ORDER BY version_number DESC
                LIMIT 1
            ) AS document_version ON true
            WHERE document_record.document_id = %s AND document_record.organization_id = %s
              AND membership.user_id = %s
            {lock}
            """,
            (document_id, organization_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise DocumentNotFoundError("document is not available in the active workspace")
        record = dict(row)
        document = {
            key: value
            for key, value in record.items()
            if key not in {"document_version_id", "content", "content_sha256"}
        }
        version = {
            "document_version_id": record["document_version_id"],
            "version_number": record["version_number"],
            "content": record["content"],
            "content_sha256": record["content_sha256"],
        }
        return document, version

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> dict[str, Any]:
        workspace = connection.execute(
            """
            SELECT workspace.workspace_id, workspace.division_id, division.code AS division_code
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workspace.workspace_id
            LEFT JOIN identity.divisions AS division ON division.division_id = workspace.division_id
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE' AND membership.user_id = %s
            """,
            (workspace_id, organization_id, actor_user_id),
        ).fetchone()
        if workspace is None:
            raise DocumentNotFoundError("active workspace access is required for documents")
        return dict(workspace)

    @staticmethod
    def _append_human_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type, entity_id,
                correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @staticmethod
    def _append_system_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, system_actor, action, entity_type, entity_id,
                correlation_id, reason, metadata
            ) VALUES (%s, 'SYSTEM', 'GENESIS', %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def _genesis_draft_content(title: str, requirement: str) -> str:
    return "\n".join(
        (
            f"# {title.strip()}",
            "",
            "## Kebutuhan yang dicatat",
            requirement.strip(),
            "",
            "## Ruang lingkup",
            "Belum lengkap — lengkapi bersama owner dokumen.",
            "",
            "## Evidence dan sumber",
            "Belum diverifikasi. Tambahkan sumber yang telah disetujui sebelum review.",
            "",
            "## Risiko dan keputusan",
            "Belum ditinjau. Draft ini bukan persetujuan atau dokumen aktif.",
        )
    )


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

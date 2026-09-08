"""Multi-document comparison and immutable revision-draft workflow."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.authorization import AccessMode, require_business_access
from alos.identity import DivisionCode
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class DocumentIntelligenceError(RuntimeError):
    pass


class DocumentVersionReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    version_number: int | None = Field(default=None, ge=1)


class DocumentComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    sources: list[DocumentVersionReference] = Field(min_length=2, max_length=20)
    create_findings: bool = False


class DocumentCitation(BaseModel):
    document_id: UUID
    title: str
    version_number: int
    content_sha256: str
    anchor: str


class DocumentComparisonIssue(BaseModel):
    issue_type: Literal[
        "DUPLICATE", "CONFLICT", "MISSING_FIELD", "MISSING_CLAUSE", "OUTDATED_REFERENCE"
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    description: str
    recommendation: str
    citations: list[DocumentCitation]
    truth_status: Literal["SUPPORTED", "REQUIRES_HUMAN_DECISION"]


class DocumentComparisonResult(BaseModel):
    document_comparison_id: UUID
    status: Literal["DRAFT", "REVIEWED"]
    issues: list[DocumentComparisonIssue]
    citations: list[DocumentCitation]
    finding_ids: list[UUID]
    summary: str
    created_at: datetime


class DocumentRevisionDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_number: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    revised_content: str = Field(min_length=1, max_length=50_000)
    reason: str = Field(min_length=3, max_length=2_000)


class DocumentRevisionDraft(BaseModel):
    document_id: UUID
    source_document_id: UUID
    source_version_number: int
    version_number: int
    title: str
    status: Literal["DRAFT"]
    content_sha256: str
    created_at: datetime


class DocumentIntelligenceRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def compare(
        self,
        actor: ActorContext,
        request: DocumentComparisonRequest,
        *,
        correlation_id: UUID,
    ) -> DocumentComparisonResult:
        require_business_access(
            actor, access_mode=AccessMode.READ, workspace_id=request.workspace_id
        )
        with self._transaction() as connection:
            documents = [
                self._load_version(connection, actor, request.workspace_id, ref)
                for ref in request.sources
            ]
            issues = _compare_documents(documents)
            citations = [
                DocumentCitation(
                    document_id=item["document_id"],
                    title=item["title"],
                    version_number=item["version_number"],
                    content_sha256=item["content_sha256"],
                    anchor="document",
                )
                for item in documents
            ]
            comparison_id = uuid4()
            source_versions = [
                {
                    "document_id": str(item["document_id"]),
                    "version_number": item["version_number"],
                    "content_sha256": item["content_sha256"],
                }
                for item in documents
            ]
            result_payload = {
                "issues": [item.model_dump(mode="json") for item in issues],
                "summary": _summary(issues),
            }
            row = connection.execute(
                """
                INSERT INTO documents.comparisons (
                    document_comparison_id, organization_id, workspace_id,
                    requested_by_user_id, source_versions, result
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING created_at
                """,
                (
                    comparison_id,
                    actor.organization_id,
                    request.workspace_id,
                    actor.user_id,
                    Jsonb(source_versions),
                    Jsonb(result_payload),
                ),
            ).fetchone()
            if row is None:
                raise DocumentIntelligenceError("document comparison could not be saved")
            finding_ids = (
                self._create_findings(
                    connection,
                    actor,
                    request.workspace_id,
                    comparison_id,
                    issues,
                )
                if request.create_findings
                else []
            )
            self._audit(
                connection,
                actor,
                "DOCUMENTS_COMPARED",
                comparison_id,
                correlation_id,
                {"source_count": len(documents), "issue_count": len(issues)},
            )
            return DocumentComparisonResult(
                document_comparison_id=comparison_id,
                status="DRAFT",
                issues=issues,
                citations=citations,
                finding_ids=finding_ids,
                summary=_summary(issues),
                created_at=row["created_at"],
            )

    def create_revision_draft(
        self,
        actor: ActorContext,
        source_document_id: UUID,
        request: DocumentRevisionDraftRequest,
        *,
        correlation_id: UUID,
    ) -> DocumentRevisionDraft:
        with self._transaction() as connection:
            source = self._load_version(
                connection,
                actor,
                None,
                DocumentVersionReference(
                    document_id=source_document_id,
                    version_number=request.source_version_number,
                ),
            )
            division_code = source["division_code"]
            require_business_access(
                actor,
                access_mode=AccessMode.CREATE_DRAFT,
                workspace_id=source["workspace_id"],
                division_code=DivisionCode(division_code) if division_code else None,
            )
            document_id = uuid4()
            content_sha256 = hashlib.sha256(request.revised_content.encode("utf-8")).hexdigest()
            title = request.title or f"{source['title']} — Revision Draft"
            row = connection.execute(
                """
                INSERT INTO documents.records (
                    document_id, organization_id, workspace_id, division_id,
                    genesis_conversation_id, title, category, classification, origin,
                    status, owner_user_id, created_by_user_id,
                    source_document_id, source_version_number
                ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, 'GENESIS', 'DRAFT', %s, %s, %s, %s)
                RETURNING created_at
                """,
                (
                    document_id,
                    actor.organization_id,
                    source["workspace_id"],
                    source["division_id"],
                    title,
                    source["category"],
                    source["classification"],
                    actor.user_id,
                    actor.user_id,
                    source_document_id,
                    source["version_number"],
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO documents.versions (
                    document_id, version_number, content, content_sha256,
                    created_by_user_id, generated_by_system
                ) VALUES (%s, 1, %s, %s, %s, true)
                """,
                (document_id, request.revised_content, content_sha256, actor.user_id),
            )
            self._audit(
                connection,
                actor,
                "DOCUMENT_REVISION_DRAFT_CREATED",
                document_id,
                correlation_id,
                {
                    "source_document_id": str(source_document_id),
                    "source_version_number": source["version_number"],
                    "reason": request.reason,
                },
            )
            if row is None:
                raise DocumentIntelligenceError("document revision draft could not be created")
            return DocumentRevisionDraft(
                document_id=document_id,
                source_document_id=source_document_id,
                source_version_number=source["version_number"],
                version_number=1,
                title=title,
                status="DRAFT",
                content_sha256=content_sha256,
                created_at=row["created_at"],
            )

    @staticmethod
    def _load_version(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        workspace_id: UUID | None,
        reference: DocumentVersionReference,
    ) -> dict[str, Any]:
        workspace_clause = "AND document.workspace_id = %s" if workspace_id else ""
        version_clause = "AND version.version_number = %s" if reference.version_number else ""
        parameters: list[Any] = [
            reference.document_id,
            actor.organization_id,
            actor.workspace_ids,
        ]
        if workspace_id:
            parameters.append(workspace_id)
        if reference.version_number:
            parameters.append(reference.version_number)
        row = connection.execute(
            f"""
            SELECT document.document_id, document.workspace_id, document.division_id,
                   division.code AS division_code, document.title, document.category,
                   document.classification, version.version_number, version.content,
                   version.content_sha256
            FROM documents.records AS document
            JOIN documents.versions AS version ON version.document_id = document.document_id
            LEFT JOIN identity.divisions AS division ON division.division_id = document.division_id
            WHERE document.document_id = %s AND document.organization_id = %s
              AND document.workspace_id = ANY(%s) {workspace_clause} {version_clause}
            ORDER BY version.version_number DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()
        if row is None:
            raise DocumentIntelligenceError("document version was not found in the actor scope")
        if row["division_code"] and DivisionCode(row["division_code"]) not in actor.division_codes:
            from alos.authorization import effective_data_scope
            from alos.identity import DataScope

            if effective_data_scope(actor) != DataScope.COMPANY:
                raise DocumentIntelligenceError("document version was not found in the actor scope")
        return dict(row)

    @staticmethod
    def _create_findings(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        workspace_id: UUID,
        comparison_id: UUID,
        issues: list[DocumentComparisonIssue],
    ) -> list[UUID]:
        finding_ids: list[UUID] = []
        for issue in issues:
            finding_id = uuid4()
            connection.execute(
                """
                INSERT INTO operational.findings (
                    finding_id, organization_id, workspace_id, source_kind, source_id,
                    title, description, severity, recommendation, citation_refs,
                    generated_by, created_by_user_id
                ) VALUES (%s, %s, %s, 'GENESIS', %s, %s, %s, %s, %s, %s, 'GENESIS', NULL)
                """,
                (
                    finding_id,
                    actor.organization_id,
                    workspace_id,
                    comparison_id,
                    f"Document {issue.issue_type.replace('_', ' ').title()}",
                    issue.description,
                    issue.severity,
                    issue.recommendation,
                    Jsonb([citation.model_dump(mode="json") for citation in issue.citations]),
                ),
            )
            finding_ids.append(finding_id)
        return finding_ids

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        action: str,
        entity_id: UUID,
        correlation_id: UUID,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'DOCUMENT_INTELLIGENCE', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_id,
                correlation_id,
                "Human requested governed document intelligence",
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


def _compare_documents(documents: list[dict[str, Any]]) -> list[DocumentComparisonIssue]:
    issues: list[DocumentComparisonIssue] = []
    by_digest: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        by_digest.setdefault(document["content_sha256"], []).append(document)
    for duplicates in by_digest.values():
        if len(duplicates) > 1:
            issues.append(
                DocumentComparisonIssue(
                    issue_type="DUPLICATE",
                    severity="LOW",
                    description="Two or more selected versions have identical content.",
                    recommendation=(
                        "Keep one canonical version and retain the others as traceable history."
                    ),
                    citations=[_citation(item, "document") for item in duplicates],
                    truth_status="SUPPORTED",
                )
            )

    fields_by_document = [_fields(item["content"]) for item in documents]
    all_fields = set().union(*(set(fields) for fields in fields_by_document))
    for field in sorted(all_fields):
        values = {
            fields[field].casefold(): index
            for index, fields in enumerate(fields_by_document)
            if field in fields
        }
        if len(values) > 1:
            citations = [
                _citation(documents[index], field)
                for index, fields in enumerate(fields_by_document)
                if field in fields
            ]
            issues.append(
                DocumentComparisonIssue(
                    issue_type="CONFLICT",
                    severity="HIGH",
                    description=(
                        f"Field '{field}' has inconsistent values across selected documents."
                    ),
                    recommendation="Assign a human owner to decide the canonical business value.",
                    citations=citations,
                    truth_status="REQUIRES_HUMAN_DECISION",
                )
            )
        missing = [index for index, fields in enumerate(fields_by_document) if field not in fields]
        if missing and len(missing) < len(documents):
            issues.append(
                DocumentComparisonIssue(
                    issue_type="MISSING_FIELD",
                    severity="MEDIUM",
                    description=(
                        f"Field '{field}' is missing from {len(missing)} selected document(s)."
                    ),
                    recommendation=(
                        "Review whether the field is mandatory before drafting a revision."
                    ),
                    citations=[
                        _citation(documents[index], field)
                        for index, fields in enumerate(fields_by_document)
                        if field in fields
                    ],
                    truth_status="REQUIRES_HUMAN_DECISION",
                )
            )
    current_year = datetime.now().year
    for document in documents:
        years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", document["content"])]
        if years and min(years) < current_year - 5:
            issues.append(
                DocumentComparisonIssue(
                    issue_type="OUTDATED_REFERENCE",
                    severity="MEDIUM",
                    description="The document contains a reference older than five years.",
                    recommendation=(
                        "Verify whether the referenced policy or regulation is still current."
                    ),
                    citations=[_citation(document, str(min(years)))],
                    truth_status="REQUIRES_HUMAN_DECISION",
                )
            )
    return issues


def _fields(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        key, separator, value = line.partition(":")
        normalized = key.strip().casefold()
        if separator and 2 <= len(normalized) <= 80 and value.strip():
            result[normalized] = value.strip()
    return result


def _citation(document: dict[str, Any], anchor: str) -> DocumentCitation:
    return DocumentCitation(
        document_id=document["document_id"],
        title=document["title"],
        version_number=document["version_number"],
        content_sha256=document["content_sha256"],
        anchor=anchor,
    )


def _summary(issues: list[DocumentComparisonIssue]) -> str:
    if not issues:
        return (
            "No deterministic duplicate, conflict, missing-field, "
            "or outdated-reference signal found."
        )
    requires_decision = sum(item.truth_status == "REQUIRES_HUMAN_DECISION" for item in issues)
    return f"Found {len(issues)} issue(s); {requires_decision} require a human business decision."

"""Durable Genesis history.  Human requirements and system artifacts are distinct."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.model_gateway import ModelResponse
from alos.persistence.database import psycopg_url

ArtifactType = Literal["ANALYSIS", "BLUEPRINT", "CONTRACT", "TEST_PLAN", "DIFF", "RELEASE_PROPOSAL"]
ContextMode = Literal["AUTO", "INTERNAL", "EXTERNAL", "INTERNAL_AND_EXTERNAL"]
ContextEntityType = Literal["DOCUMENT", "PROJECT", "TASK", "EVIDENCE", "FINDING", "REPORT"]


class GenesisHistoryError(RuntimeError):
    """A safe Genesis history failure."""


class GenesisConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=200)
    context_mode: ContextMode = "AUTO"


class GenesisConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class GenesisMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=10_000)


class GenesisConversationRecord(BaseModel):
    conversation_id: UUID
    organization_id: UUID
    workspace_id: UUID | None
    created_by_user_id: UUID | None
    status: Literal["OPEN", "CLOSED"]
    created_at: datetime
    title: str | None = None
    context_mode: ContextMode = "AUTO"
    updated_at: datetime | None = None


class GenesisMessageRecord(BaseModel):
    message_id: UUID
    conversation_id: UUID
    actor_kind: Literal["HUMAN", "SYSTEM"]
    actor_user_id: UUID | None
    system_actor: Literal["GENESIS"] | None
    content: str
    created_at: datetime
    correlation_id: UUID | None = None
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"] = "COMPLETED"
    structured_content: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_activity: list[dict[str, Any]] = Field(default_factory=list)


class GenesisConversationContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ContextEntityType
    entity_id: UUID
    source_version: str | None = Field(default=None, max_length=100)


class GenesisConversationContextRecord(GenesisConversationContextRequest):
    conversation_context_id: UUID
    conversation_id: UUID
    attached_by_user_id: UUID
    created_at: datetime


class GenesisContextOption(BaseModel):
    entity_type: ContextEntityType
    entity_id: UUID
    title: str
    source_version: str | None = None
    status: str
    scope: str


class GenesisArtifactRecord(BaseModel):
    artifact_id: UUID
    conversation_id: UUID
    artifact_type: ArtifactType
    version: int
    content: dict[str, Any]
    digest: str
    created_at: datetime


class GenesisRequirementRecord(BaseModel):
    change_request_id: UUID
    conversation_id: UUID
    message_id: UUID
    workspace_id: UUID
    requirement: str
    status: str


class GenesisHistoryRepository:
    """Preserve history without giving Genesis approval or activation authority."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_conversation(
        self,
        request: GenesisConversationRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisConversationRecord:
        with self._transaction() as connection:
            self._require_workspace_actor(
                connection, organization_id, actor_user_id, request.workspace_id
            )
            row = connection.execute(
                """
                INSERT INTO genesis.conversations (
                    organization_id, workspace_id, created_by_user_id, title, context_mode
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING conversation_id, organization_id, workspace_id, created_by_user_id,
                          status, title, context_mode, created_at, updated_at
                """,
                (
                    organization_id,
                    request.workspace_id,
                    actor_user_id,
                    request.title,
                    request.context_mode,
                ),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis conversation could not be created")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_CONVERSATION_CREATED",
                "GENESIS_CONVERSATION",
                row["conversation_id"],
                correlation_id,
                "Human opened a Genesis conversation",
                {"workspace_id": str(request.workspace_id)},
            )
            return GenesisConversationRecord(**row)

    def list_conversations(
        self,
        workspace_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[GenesisConversationRecord]:
        with self._connection() as connection:
            self._require_workspace_actor(
                connection, organization_id, actor_user_id, workspace_id
            )
            rows = connection.execute(
                """
                SELECT conversation_id, organization_id, workspace_id, created_by_user_id,
                       status, title, context_mode, created_at, updated_at
                FROM genesis.conversations
                WHERE organization_id = %s AND workspace_id = %s
                  AND created_by_user_id = %s
                  AND (%s OR status = 'OPEN')
                ORDER BY updated_at DESC, conversation_id DESC
                LIMIT %s
                """,
                (organization_id, workspace_id, actor_user_id, include_archived, limit),
            ).fetchall()
        return [GenesisConversationRecord(**row) for row in rows]

    def rename_conversation(
        self,
        conversation_id: UUID,
        request: GenesisConversationUpdateRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisConversationRecord:
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            row = connection.execute(
                """
                UPDATE genesis.conversations
                SET title = %s, updated_at = now()
                WHERE conversation_id = %s
                RETURNING conversation_id, organization_id, workspace_id, created_by_user_id,
                          status, title, context_mode, created_at, updated_at
                """,
                (request.title.strip(), conversation_id),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis conversation could not be renamed")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_CONVERSATION_RENAMED",
                "GENESIS_CONVERSATION",
                conversation_id,
                correlation_id,
                "Human renamed a Genesis conversation",
                {},
            )
            return GenesisConversationRecord(**row)

    def archive_conversation(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisConversationRecord:
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            row = connection.execute(
                """
                UPDATE genesis.conversations
                SET status = 'CLOSED', updated_at = now()
                WHERE conversation_id = %s
                RETURNING conversation_id, organization_id, workspace_id, created_by_user_id,
                          status, title, context_mode, created_at, updated_at
                """,
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis conversation could not be archived")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_CONVERSATION_ARCHIVED",
                "GENESIS_CONVERSATION",
                conversation_id,
                correlation_id,
                "Human archived a Genesis conversation without deleting its history",
                {},
            )
            return GenesisConversationRecord(**row)

    def add_human_message(
        self,
        conversation_id: UUID,
        request: GenesisMessageRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisMessageRecord:
        with self._transaction() as connection:
            conversation = self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            row = connection.execute(
                """
                INSERT INTO genesis.messages (
                    conversation_id, actor_kind, actor_user_id, content, correlation_id
                )
                VALUES (%s, 'HUMAN', %s, %s, %s)
                RETURNING message_id, conversation_id, actor_kind, actor_user_id, system_actor,
                          content, correlation_id, status, structured_content, citations,
                          tool_activity, created_at
                """,
                (conversation_id, actor_user_id, request.content, correlation_id),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis message could not be created")
            connection.execute(
                "UPDATE genesis.conversations SET updated_at = now() WHERE conversation_id = %s",
                (conversation_id,),
            )
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_MESSAGE_RECORDED",
                "GENESIS_CONVERSATION",
                conversation["conversation_id"],
                correlation_id,
                "Human recorded a Genesis conversation message",
                {},
            )
            return GenesisMessageRecord(**row)

    def record_model_usage(
        self,
        conversation_id: UUID,
        response: ModelResponse,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        purpose: str,
    ) -> None:
        with self._transaction() as connection:
            conversation = self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            connection.execute(
                """
                INSERT INTO observability.model_calls (
                    organization_id, workspace_id, conversation_id, correlation_id,
                    purpose, provider, model, input_tokens, output_tokens, latency_ms,
                    estimated_cost_usd
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    organization_id,
                    conversation["workspace_id"],
                    conversation_id,
                    correlation_id,
                    purpose,
                    response.provider,
                    response.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.latency_milliseconds,
                    response.estimated_cost_usd,
                ),
            )

    def add_system_message(
        self,
        conversation_id: UUID,
        *,
        content: str,
        structured_content: dict[str, Any],
        citations: list[dict[str, Any]],
        tool_activity: list[dict[str, Any]],
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisMessageRecord:
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            row = connection.execute(
                """
                INSERT INTO genesis.messages (
                    conversation_id, actor_kind, system_actor, content, correlation_id,
                    structured_content, citations, tool_activity
                ) VALUES (%s, 'SYSTEM', 'GENESIS', %s, %s, %s, %s, %s)
                RETURNING message_id, conversation_id, actor_kind, actor_user_id,
                          system_actor, content, correlation_id, status, structured_content,
                          citations, tool_activity, created_at
                """,
                (
                    conversation_id,
                    content,
                    correlation_id,
                    Jsonb(structured_content),
                    Jsonb(citations),
                    Jsonb(tool_activity),
                ),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("GENESIS response could not be recorded")
            connection.execute(
                "UPDATE genesis.conversations SET updated_at = now() WHERE conversation_id = %s",
                (conversation_id,),
            )
            self._audit_system(
                connection,
                organization_id,
                "GENESIS_RESPONSE_RECORDED",
                "GENESIS_CONVERSATION",
                conversation_id,
                correlation_id,
                "GENESIS recorded a role-aware response with bounded tool activity",
                {"tool_call_count": len(tool_activity), "citation_count": len(citations)},
            )
            return GenesisMessageRecord(**row)

    def attach_context(
        self,
        conversation_id: UUID,
        request: GenesisConversationContextRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisConversationContextRecord:
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            # PostgreSQL treats NULL values as distinct for an ordinary unique key.
            # Context without a source version is valid, so resolve an existing row
            # explicitly before inserting rather than allowing duplicate attachments.
            row = connection.execute(
                """
                SELECT conversation_context_id, conversation_id, entity_type, entity_id,
                       source_version, attached_by_user_id, created_at
                FROM genesis.conversation_context
                WHERE conversation_id = %s
                  AND entity_type = %s
                  AND entity_id = %s
                  AND source_version IS NOT DISTINCT FROM %s
                """,
                (
                    conversation_id,
                    request.entity_type,
                    request.entity_id,
                    request.source_version,
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    INSERT INTO genesis.conversation_context (
                        conversation_id, entity_type, entity_id, source_version,
                        attached_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING conversation_context_id, conversation_id, entity_type, entity_id,
                              source_version, attached_by_user_id, created_at
                    """,
                    (
                        conversation_id,
                        request.entity_type,
                        request.entity_id,
                        request.source_version,
                        actor_user_id,
                    ),
                ).fetchone()
            if row is None:
                raise GenesisHistoryError("GENESIS context could not be attached")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_CONTEXT_ATTACHED",
                request.entity_type,
                request.entity_id,
                correlation_id,
                "Human attached an authorized ALOS entity to a GENESIS conversation",
                {"conversation_id": str(conversation_id)},
            )
            return GenesisConversationContextRecord(**row)

    def list_context(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> list[GenesisConversationContextRecord]:
        with self._connection() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            rows = connection.execute(
                """
                SELECT conversation_context_id, conversation_id, entity_type, entity_id,
                       source_version, attached_by_user_id, created_at
                FROM genesis.conversation_context
                WHERE conversation_id = %s
                ORDER BY created_at, conversation_context_id
                """,
                (conversation_id,),
            ).fetchall()
        return [GenesisConversationContextRecord(**row) for row in rows]

    def remove_context(
        self,
        conversation_id: UUID,
        conversation_context_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        """Remove only the conversation association; the governed source remains untouched."""
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            removed = connection.execute(
                """
                DELETE FROM genesis.conversation_context
                WHERE conversation_context_id = %s AND conversation_id = %s
                RETURNING entity_type, entity_id
                """,
                (conversation_context_id, conversation_id),
            ).fetchone()
            if removed is None:
                raise GenesisHistoryError("Genesis conversation context was not found")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_CONTEXT_REMOVED",
                removed["entity_type"],
                removed["entity_id"],
                correlation_id,
                "Human removed a context association without deleting the source entity",
                {"conversation_id": str(conversation_id)},
            )

    def list_context_options(
        self,
        workspace_id: UUID,
        entity_type: ContextEntityType,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        division_codes: list[str],
        company_scope: bool,
        search: str = "",
        limit: int = 25,
    ) -> list[GenesisContextOption]:
        """List safe, scoped entity metadata for the non-technical context picker."""
        queries = {
            "DOCUMENT": """
                SELECT 'DOCUMENT' AS entity_type, document.document_id AS entity_id,
                       document.title, latest.version_number::text AS source_version,
                       document.status, coalesce(division.code, 'COMPANY') AS scope
                FROM documents.records AS document
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = document.division_id
                LEFT JOIN LATERAL (
                    SELECT version_number FROM documents.versions
                    WHERE document_id = document.document_id
                    ORDER BY version_number DESC LIMIT 1
                ) AS latest ON true
                WHERE document.organization_id = %s AND document.workspace_id = %s
                  AND (%s OR document.division_id IS NULL OR division.code = ANY(%s))
                  AND document.status <> 'ARCHIVED' AND document.title ILIKE %s
                ORDER BY document.updated_at DESC LIMIT %s
            """,
            "PROJECT": """
                SELECT 'PROJECT' AS entity_type, project.project_id AS entity_id,
                       project.name AS title, NULL::text AS source_version,
                       project.status, division.code AS scope
                FROM portfolio.projects AS project
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                WHERE project.organization_id = %s AND project.workspace_id = %s
                  AND (%s OR division.code = ANY(%s))
                  AND project.status <> 'ARCHIVED' AND project.name ILIKE %s
                ORDER BY project.updated_at DESC LIMIT %s
            """,
            "TASK": """
                SELECT 'TASK' AS entity_type, task.task_id AS entity_id,
                       task.title, NULL::text AS source_version,
                       task.status, division.code AS scope
                FROM operational.tasks AS task
                JOIN identity.divisions AS division ON division.division_id = task.division_id
                WHERE task.organization_id = %s AND task.workspace_id = %s
                  AND (%s OR division.code = ANY(%s)) AND task.title ILIKE %s
                ORDER BY task.updated_at DESC LIMIT %s
            """,
            "EVIDENCE": """
                SELECT 'EVIDENCE' AS entity_type, evidence.evidence_id AS entity_id,
                       coalesce(evidence.metadata ->> 'title',
                           'Evidence ' || left(evidence.evidence_id::text, 8)) AS title,
                       evidence.version::text AS source_version,
                       evidence.validation_status AS status, division.code AS scope
                FROM operational.evidence AS evidence
                JOIN identity.divisions AS division
                  ON division.division_id = evidence.division_id
                WHERE evidence.organization_id = %s AND evidence.workspace_id = %s
                  AND (%s OR division.code = ANY(%s))
                  AND coalesce(evidence.metadata ->> 'title', evidence.evidence_id::text)
                      ILIKE %s
                ORDER BY evidence.created_at DESC LIMIT %s
            """,
            "FINDING": """
                SELECT 'FINDING' AS entity_type, finding.finding_id AS entity_id,
                       finding.title, NULL::text AS source_version,
                       finding.status, coalesce(division.code, 'COMPANY') AS scope
                FROM operational.findings AS finding
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = finding.division_id
                WHERE finding.organization_id = %s AND finding.workspace_id = %s
                  AND (%s OR finding.division_id IS NULL OR division.code = ANY(%s))
                  AND finding.title ILIKE %s
                ORDER BY finding.updated_at DESC LIMIT %s
            """,
            "REPORT": """
                SELECT 'REPORT' AS entity_type, report.report_id AS entity_id,
                       definition.name AS title, NULL::text AS source_version,
                       report.status, coalesce(division.code, 'COMPANY') AS scope
                FROM reporting.reports AS report
                JOIN reporting.definitions AS definition
                  ON definition.report_definition_id = report.report_definition_id
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = definition.division_id
                WHERE report.organization_id = %s AND report.workspace_id = %s
                  AND (%s OR definition.division_id IS NULL OR division.code = ANY(%s))
                  AND definition.name ILIKE %s
                ORDER BY report.updated_at DESC LIMIT %s
            """,
        }
        with self._connection() as connection:
            self._require_workspace_actor(
                connection, organization_id, actor_user_id, workspace_id
            )
            rows = connection.execute(
                queries[entity_type],
                (
                    organization_id,
                    workspace_id,
                    company_scope,
                    division_codes,
                    f"%{search.strip()}%",
                    min(max(limit, 1), 100),
                ),
            ).fetchall()
        return [GenesisContextOption(**row) for row in rows]

    def record_requirement(
        self,
        conversation_id: UUID,
        requirement: str,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisRequirementRecord:
        """Persist the exact natural-language request before a provider is called."""
        with self._transaction() as connection:
            conversation = self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            workspace_id = conversation["workspace_id"]
            if workspace_id is None:
                raise GenesisHistoryError("Genesis conversation requires a workspace")
            message = connection.execute(
                """
                INSERT INTO genesis.messages (conversation_id, actor_kind, actor_user_id, content)
                VALUES (%s, 'HUMAN', %s, %s)
                RETURNING message_id
                """,
                (conversation_id, actor_user_id, requirement),
            ).fetchone()
            change = connection.execute(
                """
                INSERT INTO genesis.change_requests (
                    organization_id, workspace_id, conversation_id, requested_by_user_id,
                    requirement
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING change_request_id, status
                """,
                (organization_id, workspace_id, conversation_id, actor_user_id, requirement),
            ).fetchone()
            if message is None or change is None:
                raise GenesisHistoryError("Genesis requirement could not be recorded")
            self._audit_human(
                connection,
                organization_id,
                actor_user_id,
                "GENESIS_REQUIREMENT_RECORDED",
                "CHANGE_REQUEST",
                change["change_request_id"],
                correlation_id,
                "Human submitted a natural-language Genesis requirement",
                {"conversation_id": str(conversation_id)},
            )
            return GenesisRequirementRecord(
                change_request_id=change["change_request_id"],
                conversation_id=conversation_id,
                message_id=message["message_id"],
                workspace_id=workspace_id,
                requirement=requirement,
                status=change["status"],
            )

    def record_system_artifact(
        self,
        conversation_id: UUID,
        artifact_type: ArtifactType,
        content: dict[str, Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisArtifactRecord:
        """Store an immutable Genesis artifact; it is evidence, never an approval."""
        with self._transaction() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"alos-artifact:{conversation_id}:{artifact_type}",),
            )
            version = connection.execute(
                """
                SELECT coalesce(max(version), 0) + 1 AS next_version
                FROM genesis.artifacts
                WHERE conversation_id = %s AND artifact_type = %s
                """,
                (conversation_id, artifact_type),
            ).fetchone()
            if version is None:
                raise GenesisHistoryError("Genesis artifact version could not be allocated")
            digest = _digest(content)
            row = connection.execute(
                """
                INSERT INTO genesis.artifacts (
                    conversation_id, artifact_type, version, content, digest
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING artifact_id, conversation_id, artifact_type, version, content,
                          digest, created_at
                """,
                (
                    conversation_id,
                    artifact_type,
                    version["next_version"],
                    Jsonb(content),
                    digest,
                ),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis artifact could not be recorded")
            self._audit_system(
                connection,
                organization_id,
                "GENESIS_ARTIFACT_RECORDED",
                "GENESIS_ARTIFACT",
                row["artifact_id"],
                correlation_id,
                "Genesis recorded an immutable design artifact",
                {"conversation_id": str(conversation_id), "artifact_type": artifact_type},
            )
            return GenesisArtifactRecord(**row)

    def get_conversation(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisConversationRecord:
        with self._connection() as connection:
            conversation = self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            return GenesisConversationRecord(**conversation)

    def list_messages(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> list[GenesisMessageRecord]:
        with self._connection() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            rows = connection.execute(
                """
                SELECT message_id, conversation_id, actor_kind, actor_user_id, system_actor,
                       content, correlation_id, status, structured_content, citations,
                       tool_activity, created_at
                FROM genesis.messages
                WHERE conversation_id = %s
                ORDER BY created_at, message_id
                """,
                (conversation_id,),
            ).fetchall()
        return [GenesisMessageRecord(**row) for row in rows]

    def list_artifacts(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> list[GenesisArtifactRecord]:
        with self._connection() as connection:
            self._conversation_for_actor(
                connection, conversation_id, organization_id, actor_user_id
            )
            rows = connection.execute(
                """
                SELECT artifact_id, conversation_id, artifact_type, version, content, digest,
                       created_at
                FROM genesis.artifacts
                WHERE conversation_id = %s
                ORDER BY artifact_type, version
                """,
                (conversation_id,),
            ).fetchall()
        return [GenesisArtifactRecord(**row) for row in rows]

    @staticmethod
    def _conversation_for_actor(
        connection: psycopg.Connection[Any],
        conversation_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> dict[str, Any]:
        conversation = connection.execute(
            """
            SELECT conversation.conversation_id, conversation.organization_id,
                   conversation.workspace_id,
                   conversation.created_by_user_id, conversation.status, conversation.title,
                   conversation.context_mode, conversation.created_at, conversation.updated_at
            FROM genesis.conversations AS conversation
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = conversation.workspace_id
            WHERE conversation.conversation_id = %s AND conversation.organization_id = %s
              AND membership.user_id = %s AND conversation.status = 'OPEN'
              AND conversation.created_by_user_id = %s
            """,
            (conversation_id, organization_id, actor_user_id, actor_user_id),
        ).fetchone()
        if conversation is None:
            raise GenesisHistoryError("open Genesis conversation is not available to this actor")
        return dict(conversation)

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        membership = connection.execute(
            """
            SELECT 1 FROM identity.users AS actor
            JOIN workspace.memberships AS membership ON membership.user_id = actor.user_id
            JOIN workspace.workspaces AS workspace
              ON workspace.workspace_id = membership.workspace_id
            WHERE actor.organization_id = %s AND actor.user_id = %s
              AND workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
            """,
            (organization_id, actor_user_id, workspace_id, organization_id),
        ).fetchone()
        if membership is None:
            raise GenesisHistoryError("active workspace membership is required")

    @staticmethod
    def _audit_human(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
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
    def _audit_system(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, system_actor, action, entity_type,
                entity_id, correlation_id, reason, metadata
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


def _digest(content: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

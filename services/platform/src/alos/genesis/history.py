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

from alos.persistence.database import psycopg_url

ArtifactType = Literal["ANALYSIS", "BLUEPRINT", "CONTRACT", "TEST_PLAN", "DIFF", "RELEASE_PROPOSAL"]


class GenesisHistoryError(RuntimeError):
    """A safe Genesis history failure."""


class GenesisConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID


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


class GenesisMessageRecord(BaseModel):
    message_id: UUID
    conversation_id: UUID
    actor_kind: Literal["HUMAN", "SYSTEM"]
    actor_user_id: UUID | None
    system_actor: Literal["GENESIS"] | None
    content: str
    created_at: datetime


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
                    organization_id, workspace_id, created_by_user_id
                )
                VALUES (%s, %s, %s)
                RETURNING conversation_id, organization_id, workspace_id, created_by_user_id,
                          status,
                          created_at
                """,
                (organization_id, request.workspace_id, actor_user_id),
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
                INSERT INTO genesis.messages (conversation_id, actor_kind, actor_user_id, content)
                VALUES (%s, 'HUMAN', %s, %s)
                RETURNING message_id, conversation_id, actor_kind, actor_user_id, system_actor,
                          content, created_at
                """,
                (conversation_id, actor_user_id, request.content),
            ).fetchone()
            if row is None:
                raise GenesisHistoryError("Genesis message could not be created")
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
                       content,
                       created_at
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
                   conversation.created_by_user_id, conversation.status, conversation.created_at
            FROM genesis.conversations AS conversation
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = conversation.workspace_id
            WHERE conversation.conversation_id = %s AND conversation.organization_id = %s
              AND membership.user_id = %s AND conversation.status = 'OPEN'
            """,
            (conversation_id, organization_id, actor_user_id),
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

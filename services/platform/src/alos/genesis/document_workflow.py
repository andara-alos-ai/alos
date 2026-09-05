"""Durable state machine for Genesis document workflows.

Each transition is source-bound, append-only in the Genesis artifact history,
and ends at an H4 handoff rather than a release or activation.
"""

from __future__ import annotations

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

WorkflowStatus = Literal[
    "ANALYSIS_DRAFT",
    "RND_DRAFT",
    "CHECKLIST_DRAFT",
    "COMPLETION_DRAFT",
    "AGENT_PROPOSAL_DRAFT",
    "READY_FOR_H4",
]
WorkflowDraftColumn = Literal[
    "rnd_document_id", "checklist_document_id", "completion_document_id"
]
WorkflowArtifactColumn = Literal["agent_proposal_artifact_id", "h4_handoff_artifact_id"]


class GenesisDocumentWorkflowError(RuntimeError):
    """A safe document-workflow persistence failure."""


class GenesisDocumentWorkflowNotFoundError(GenesisDocumentWorkflowError):
    """The workflow is not visible to the current workspace actor."""


class GenesisDocumentWorkflowConflictError(GenesisDocumentWorkflowError):
    """The requested workflow transition is out of order."""


class GenesisDocumentWorkflowRecord(BaseModel):
    workflow_id: UUID
    organization_id: UUID
    workspace_id: UUID
    conversation_id: UUID
    source_document_id: UUID
    source_version_number: int
    source_content_sha256: str
    analysis_document_id: UUID
    rnd_document_id: UUID | None
    checklist_document_id: UUID | None
    completion_document_id: UUID | None
    agent_proposal_artifact_id: UUID | None
    h4_handoff_artifact_id: UUID | None
    status: WorkflowStatus
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class GenesisDocumentResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str = Field(min_length=20, max_length=10_000)


class GenesisCompletionDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion_intent: str = Field(min_length=20, max_length=10_000)


class GenesisAgentProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=20, max_length=10_000)
    name: str | None = Field(default=None, min_length=3, max_length=200)


class GenesisApprovalHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=3, max_length=2_000)


class GenesisDocumentWorkflowRepository:
    """Persist ordered Genesis document workflow state with workspace RBAC."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        conversation_id: UUID,
        source_document_id: UUID,
        source_version_number: int,
        source_content_sha256: str,
        analysis_document_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisDocumentWorkflowRecord:
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            row = connection.execute(
                """
                INSERT INTO genesis.document_workflows (
                    organization_id, workspace_id, conversation_id, source_document_id,
                    source_version_number, source_content_sha256, analysis_document_id,
                    created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING workflow_id, organization_id, workspace_id, conversation_id,
                          source_document_id, source_version_number, source_content_sha256,
                          analysis_document_id, rnd_document_id, checklist_document_id,
                          completion_document_id, agent_proposal_artifact_id,
                          h4_handoff_artifact_id, status, created_by_user_id, created_at, updated_at
                """,
                (
                    organization_id,
                    workspace_id,
                    conversation_id,
                    source_document_id,
                    source_version_number,
                    source_content_sha256,
                    analysis_document_id,
                    actor_user_id,
                ),
            ).fetchone()
            if row is None:
                raise GenesisDocumentWorkflowError("Genesis document workflow could not be created")
            self._append_system_audit(
                connection,
                organization_id=organization_id,
                action="GENESIS_DOCUMENT_WORKFLOW_CREATED",
                entity_id=row["workflow_id"],
                correlation_id=correlation_id,
                reason="Genesis bound a document analysis workflow to an immutable source version",
                metadata={
                    "source_document_id": str(source_document_id),
                    "source_version_number": source_version_number,
                    "analysis_document_id": str(analysis_document_id),
                },
            )
            return GenesisDocumentWorkflowRecord(**row)

    def get(
        self,
        workflow_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisDocumentWorkflowRecord:
        with self._connection() as connection:
            return GenesisDocumentWorkflowRecord(
                **self._load_workflow(connection, workflow_id, organization_id, actor_user_id)
            )

    def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> list[GenesisDocumentWorkflowRecord]:
        with self._connection() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            rows = connection.execute(
                """
                SELECT workflow_id, organization_id, workspace_id, conversation_id,
                       source_document_id, source_version_number, source_content_sha256,
                       analysis_document_id, rnd_document_id, checklist_document_id,
                       completion_document_id, agent_proposal_artifact_id,
                       h4_handoff_artifact_id, status, created_by_user_id, created_at, updated_at
                FROM genesis.document_workflows
                WHERE organization_id = %s AND workspace_id = %s
                ORDER BY updated_at DESC, workflow_id DESC
                """,
                (organization_id, workspace_id),
            ).fetchall()
        return [GenesisDocumentWorkflowRecord(**row) for row in rows]

    def advance(
        self,
        workflow_id: UUID,
        *,
        expected_status: WorkflowStatus,
        next_status: WorkflowStatus,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        audit_action: str,
        audit_reason: str,
        metadata: dict[str, Any],
        draft_column: WorkflowDraftColumn | None = None,
        draft_document_id: UUID | None = None,
        artifact_column: WorkflowArtifactColumn | None = None,
        artifact_id: UUID | None = None,
    ) -> GenesisDocumentWorkflowRecord:
        if (draft_column is None) != (draft_document_id is None):
            raise ValueError("workflow draft column and document id must be supplied together")
        if (artifact_column is None) != (artifact_id is None):
            raise ValueError("workflow artifact column and artifact id must be supplied together")
        if draft_column not in {
            None,
            "rnd_document_id",
            "checklist_document_id",
            "completion_document_id",
        }:
            raise ValueError("invalid workflow draft column")
        if artifact_column not in {
            None,
            "agent_proposal_artifact_id",
            "h4_handoff_artifact_id",
        }:
            raise ValueError("invalid workflow artifact column")
        with self._transaction() as connection:
            workflow = self._load_workflow(
                connection,
                workflow_id,
                organization_id,
                actor_user_id,
                for_update=True,
            )
            if workflow["status"] != expected_status:
                raise GenesisDocumentWorkflowConflictError(
                    f"workflow must be {expected_status} before it can become {next_status}"
                )
            assignments = ["status = %s", "updated_at = now()"]
            params: list[object] = [next_status]
            if draft_column is not None and draft_document_id is not None:
                assignments.append(f"{draft_column} = %s")
                params.append(draft_document_id)
            if artifact_column is not None and artifact_id is not None:
                assignments.append(f"{artifact_column} = %s")
                params.append(artifact_id)
            params.append(workflow_id)
            row = connection.execute(
                f"""
                UPDATE genesis.document_workflows
                SET {", ".join(assignments)}
                WHERE workflow_id = %s
                RETURNING workflow_id, organization_id, workspace_id, conversation_id,
                          source_document_id, source_version_number, source_content_sha256,
                          analysis_document_id, rnd_document_id, checklist_document_id,
                          completion_document_id, agent_proposal_artifact_id,
                          h4_handoff_artifact_id, status, created_by_user_id, created_at, updated_at
                """,
                params,
            ).fetchone()
            if row is None:
                raise GenesisDocumentWorkflowError("Genesis document workflow could not advance")
            self._append_system_audit(
                connection,
                organization_id=organization_id,
                action=audit_action,
                entity_id=workflow_id,
                correlation_id=correlation_id,
                reason=audit_reason,
                metadata=metadata,
            )
            return GenesisDocumentWorkflowRecord(**row)

    @staticmethod
    def _load_workflow(
        connection: psycopg.Connection[Any],
        workflow_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        lock = " FOR UPDATE OF workflow" if for_update else ""
        row = connection.execute(
            f"""
            SELECT workflow.workflow_id, workflow.organization_id, workflow.workspace_id,
                   workflow.conversation_id, workflow.source_document_id,
                   workflow.source_version_number, workflow.source_content_sha256,
                   workflow.analysis_document_id, workflow.rnd_document_id,
                   workflow.checklist_document_id, workflow.completion_document_id,
                   workflow.agent_proposal_artifact_id, workflow.h4_handoff_artifact_id,
                   workflow.status, workflow.created_by_user_id, workflow.created_at,
                   workflow.updated_at
            FROM genesis.document_workflows AS workflow
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workflow.workspace_id
            WHERE workflow.workflow_id = %s AND workflow.organization_id = %s
              AND membership.user_id = %s
            {lock}
            """,
            (workflow_id, organization_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise GenesisDocumentWorkflowNotFoundError(
                "Genesis document workflow is not available in the active workspace"
            )
        return dict(row)

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        membership = connection.execute(
            """
            SELECT 1
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workspace.workspace_id
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE' AND membership.user_id = %s
            """,
            (workspace_id, organization_id, actor_user_id),
        ).fetchone()
        if membership is None:
            raise GenesisDocumentWorkflowNotFoundError("active workspace access is required")

    @staticmethod
    def _append_system_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        action: str,
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
            ) VALUES (%s, 'SYSTEM', 'GENESIS', %s, 'GENESIS_DOCUMENT_WORKFLOW', %s, %s, %s, %s)
            """,
            (
                organization_id,
                action,
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

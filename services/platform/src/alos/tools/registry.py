"""Tool Registry where a maker cannot approve their own Runtime tool."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.persistence.database import psycopg_url

ToolRisk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ToolState = Literal["DRAFT", "IN_REVIEW", "APPROVED", "RETIRED"]
_APPROVABLE_HANDLERS = {
    "FIXTURE_SOURCE_READ",
    "SOURCE_REGISTRY_SEARCH",
    "ORGANIZATION_CONTEXT_READ",
    "DIVISION_CONTEXT_READ",
    "PROJECT_LIST",
    "PROJECT_READ",
    "TASK_LIST",
    "TASK_READ",
    "TASK_CREATE_DRAFT",
    "TASK_UPDATE_STATUS",
    "EVIDENCE_READ",
    "DOCUMENT_SEARCH",
    "DOCUMENT_READ",
    "DOCUMENT_COMPARE",
    "FINDING_CREATE",
    "APPROVAL_REQUEST",
    "REPORT_GENERATE",
    "GLOBAL_SEARCH",
}
_ACCESS_MODES = {
    "READ",
    "READ_ONLY",
    "CREATE_DRAFT",
    "UPDATE_SCOPED",
    "REQUEST_APPROVAL",
    "EXECUTE_APPROVED_ACTION",
}


class ToolRegistryError(RuntimeError):
    """A safe Tool Registry domain failure."""


class ToolConflictError(ToolRegistryError):
    """Tool state or uniqueness forbids the requested change."""


class ToolNotFoundError(ToolRegistryError):
    """Tool does not exist in the actor organization."""


class ToolDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str = Field(min_length=1, max_length=200)
    risk_level: ToolRisk = "LOW"
    manifest: dict[str, Any]

    @model_validator(mode="after")
    def validate_runtime_manifest(self) -> ToolDefinitionRequest:
        if self.manifest.get("access_mode") not in _ACCESS_MODES:
            raise ValueError("tool access_mode is not supported")
        if self.manifest.get("runtime_handler") not in _APPROVABLE_HANDLERS:
            raise ValueError("tool runtime handler is not implemented by the shared Runtime")
        for schema_key in ("input_schema", "output_schema"):
            schema = self.manifest.setdefault(schema_key, {"type": "object"})
            if not isinstance(schema, dict) or schema.get("type") not in {"object", "array"}:
                raise ValueError(f"tool {schema_key} must be a typed JSON schema")
        self.manifest.setdefault("required_permission", self.tool_key)
        self.manifest.setdefault("allowed_scopes", ["COMPANY", "DIVISION", "PROJECT"])
        if self.manifest.get("access_mode") == "EXECUTE_APPROVED_ACTION" and not self.manifest.get(
            "approval_digest_required", False
        ):
            raise ValueError("direct execution requires an approval-bound payload digest")
        return self


class ToolDefinitionRecord(BaseModel):
    tool_definition_id: UUID
    tool_key: str
    name: str
    risk_level: ToolRisk
    manifest: dict[str, Any]
    lifecycle_status: ToolState
    owner_user_id: UUID | None
    created_at: datetime


class ToolRegistryRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_draft(
        self,
        request: ToolDefinitionRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> ToolDefinitionRecord:
        with self._transaction() as connection:
            self._require_actor(connection, organization_id, actor_user_id)
            try:
                row = connection.execute(
                    """
                    INSERT INTO agents.tool_definitions (
                        organization_id, tool_key, name, risk_level, manifest, lifecycle_status,
                        owner_user_id
                    ) VALUES (%s, %s, %s, %s, %s, 'DRAFT', %s)
                    RETURNING tool_definition_id, tool_key, name, risk_level, manifest,
                              lifecycle_status, owner_user_id, created_at
                    """,
                    (
                        organization_id,
                        request.tool_key,
                        request.name,
                        request.risk_level,
                        Jsonb(request.manifest),
                        actor_user_id,
                    ),
                ).fetchone()
            except UniqueViolation as error:
                raise ToolConflictError("tool key already exists in this organization") from error
            if row is None:
                raise ToolRegistryError("tool draft could not be created")
            self._audit(
                connection,
                organization_id,
                actor_user_id,
                "TOOL_DRAFT_REGISTERED",
                row["tool_definition_id"],
                correlation_id,
                "Human registered a typed Tool Registry draft",
                {
                    "tool_key": request.tool_key,
                    "runtime_handler": request.manifest["runtime_handler"],
                },
            )
            return ToolDefinitionRecord(**row)

    def approve(
        self,
        tool_key: str,
        *,
        organization_id: UUID,
        approver_user_id: UUID,
        correlation_id: UUID,
    ) -> ToolDefinitionRecord:
        with self._transaction() as connection:
            self._require_actor(connection, organization_id, approver_user_id)
            tool = connection.execute(
                """
                SELECT tool_definition_id, tool_key, name, risk_level, manifest, lifecycle_status,
                       owner_user_id, created_at
                FROM agents.tool_definitions
                WHERE organization_id = %s AND tool_key = %s
                FOR UPDATE
                """,
                (organization_id, tool_key),
            ).fetchone()
            if tool is None:
                raise ToolNotFoundError("tool was not found")
            if tool["owner_user_id"] == approver_user_id:
                raise ToolConflictError("tool maker cannot approve their own tool")
            if tool["lifecycle_status"] != "DRAFT":
                raise ToolConflictError("only a draft tool can be approved")
            manifest = tool["manifest"]
            if not isinstance(manifest, dict):
                raise ToolConflictError("tool manifest is invalid")
            ToolDefinitionRequest(
                tool_key=tool["tool_key"],
                name=tool["name"],
                risk_level=tool["risk_level"],
                manifest=manifest,
            )
            row = connection.execute(
                """
                UPDATE agents.tool_definitions
                SET lifecycle_status = 'APPROVED'
                WHERE tool_definition_id = %s
                RETURNING tool_definition_id, tool_key, name, risk_level, manifest,
                          lifecycle_status, owner_user_id, created_at
                """,
                (tool["tool_definition_id"],),
            ).fetchone()
            if row is None:
                raise ToolRegistryError("tool could not be approved")
            self._audit(
                connection,
                organization_id,
                approver_user_id,
                "TOOL_APPROVED",
                row["tool_definition_id"],
                correlation_id,
                "Independent human approved a typed Runtime tool",
                {"tool_key": row["tool_key"]},
            )
            return ToolDefinitionRecord(**row)

    def list_tools(self, organization_id: UUID) -> list[ToolDefinitionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT tool_definition_id, tool_key, name, risk_level, manifest, lifecycle_status,
                       owner_user_id, created_at
                FROM agents.tool_definitions
                WHERE organization_id = %s
                ORDER BY tool_key
                """,
                (organization_id,),
            ).fetchall()
        return [ToolDefinitionRecord(**row) for row in rows]

    @staticmethod
    def _require_actor(
        connection: psycopg.Connection[Any], organization_id: UUID, actor_user_id: UUID
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM identity.users WHERE organization_id = %s AND user_id = %s",
            (organization_id, actor_user_id),
        ).fetchone() is None:
            raise ToolRegistryError("actor does not belong to the organization")

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
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
            ) VALUES (%s, 'HUMAN', %s, %s, 'TOOL_DEFINITION', %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
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

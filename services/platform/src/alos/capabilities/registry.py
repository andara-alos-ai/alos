"""First-class Business Capability Registry and governed typed-tool catalog."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from alos.persistence.database import psycopg_url


class CapabilityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_key: str
    domain: str
    name: str
    description: str
    supported_scopes: list[str]
    allowed_data_classification: list[str]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    access_mode: Literal[
        "READ", "CREATE_DRAFT", "UPDATE_SCOPED", "REQUEST_APPROVAL",
        "EXECUTE_APPROVED_ACTION",
    ]
    availability: Literal["AVAILABLE", "UNAVAILABLE", "DEGRADED"]
    configuration_status: Literal["CONFIGURED", "NEEDS_CONFIGURATION", "NOT_APPLICABLE"]
    version: int
    metadata: dict[str, Any]
    backing_tools: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TypedToolRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str
    capability_key: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    allowed_scopes: list[str]
    required_permission: str
    access_mode: str
    timeout_seconds: int
    idempotency_policy: Literal["NONE", "OPTIONAL", "REQUIRED"]
    audit_policy: Literal["ALWAYS", "ON_WRITE"]
    runtime_handler: str
    lifecycle_status: str
    version: int


class CapabilityResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_keys: list[str] = Field(min_length=1, max_length=50)


class CapabilityResolution(BaseModel):
    resolved: list[CapabilityRecord]
    missing_dependencies: list[str]
    unavailable: list[str]
    activation_readiness: Literal["READY", "NEEDS_CONFIGURATION"]


class CapabilityRegistryRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def list_capabilities(
        self, *, domain: str | None = None, configured_only: bool = False
    ) -> list[CapabilityRecord]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if domain:
            conditions.append("definition.domain = %s")
            parameters.append(domain)
        if configured_only:
            conditions.append(
                "definition.availability = 'AVAILABLE' "
                "AND definition.configuration_status = 'CONFIGURED'"
            )
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT definition.capability_key, definition.domain, definition.name,
                       definition.description, definition.supported_scopes,
                       definition.allowed_data_classification, definition.risk_level,
                       definition.access_mode, definition.availability,
                       definition.configuration_status, definition.version, definition.metadata,
                       definition.created_at, definition.updated_at,
                       COALESCE(array_agg(tool.tool_key ORDER BY tool.tool_key)
                           FILTER (WHERE tool.tool_key IS NOT NULL), '{{}}') AS backing_tools
                FROM capabilities.definitions AS definition
                LEFT JOIN capabilities.tools AS tool
                  ON tool.capability_key = definition.capability_key
                 AND tool.lifecycle_status = 'APPROVED'
                {where}
                GROUP BY definition.capability_key
                ORDER BY definition.domain, definition.capability_key
                """,
                parameters,
            ).fetchall()
        return [CapabilityRecord(**row) for row in rows]

    def list_tools(self, *, capability_key: str | None = None) -> list[TypedToolRecord]:
        condition = "WHERE capability_key = %s" if capability_key else ""
        parameters: list[Any] = [capability_key] if capability_key else []
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT tool_key, capability_key, description, input_schema, output_schema,
                       risk_level, allowed_scopes, required_permission, access_mode,
                       timeout_seconds, idempotency_policy, audit_policy, runtime_handler,
                       lifecycle_status, version
                FROM capabilities.tools
                {condition}
                ORDER BY capability_key, tool_key
                """,
                parameters,
            ).fetchall()
        return [TypedToolRecord(**row) for row in rows]

    def get_tool(self, tool_key: str) -> TypedToolRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT tool_key, capability_key, description, input_schema, output_schema,
                       risk_level, allowed_scopes, required_permission, access_mode,
                       timeout_seconds, idempotency_policy, audit_policy, runtime_handler,
                       lifecycle_status, version
                FROM capabilities.tools
                WHERE tool_key = %s
                """,
                (tool_key,),
            ).fetchone()
        return TypedToolRecord(**row) if row else None

    def resolve(self, request: CapabilityResolutionRequest) -> CapabilityResolution:
        requested = list(dict.fromkeys(request.capability_keys))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT definition.capability_key, definition.domain, definition.name,
                       definition.description, definition.supported_scopes,
                       definition.allowed_data_classification, definition.risk_level,
                       definition.access_mode, definition.availability,
                       definition.configuration_status, definition.version, definition.metadata,
                       definition.created_at, definition.updated_at,
                       COALESCE(array_agg(tool.tool_key ORDER BY tool.tool_key)
                           FILTER (WHERE tool.lifecycle_status = 'APPROVED'), '{}') AS backing_tools
                FROM capabilities.definitions AS definition
                LEFT JOIN capabilities.tools AS tool
                  ON tool.capability_key = definition.capability_key
                WHERE definition.capability_key = ANY(%s)
                GROUP BY definition.capability_key
                ORDER BY definition.capability_key
                """,
                (requested,),
            ).fetchall()
        resolved = [CapabilityRecord(**row) for row in rows]
        found = {item.capability_key for item in resolved}
        missing = [key for key in requested if key not in found]
        unavailable = [
            item.capability_key
            for item in resolved
            if item.availability != "AVAILABLE"
            or item.configuration_status != "CONFIGURED"
            or not item.backing_tools
        ]
        return CapabilityResolution(
            resolved=resolved,
            missing_dependencies=missing,
            unavailable=unavailable,
            activation_readiness="NEEDS_CONFIGURATION" if missing or unavailable else "READY",
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

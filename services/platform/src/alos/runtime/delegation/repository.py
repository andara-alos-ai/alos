"""Persistent bounded Agent delegation using authoritative runtime state."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.genesis.governed_foundations import (
    DelegationRequest,
    Scope,
    validate_delegation,
)
from alos.persistence.database import psycopg_url


class DelegationError(RuntimeError):
    """A safe bounded delegation failure."""


class DelegationBlocked(DelegationError):
    """A policy or runtime invariant rejected a delegation."""


class DelegationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DelegationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delegation_id: UUID
    parent_run_id: UUID
    child_run_id: UUID | None
    parent_agent_version_id: UUID | None
    child_agent_version_id: UUID
    depth: int
    scope: Scope
    status: DelegationStatus
    correlation_id: UUID
    created_at: datetime
    completed_at: datetime | None
    model_calls: int
    tool_calls: int
    total_tokens: int
    estimated_cost_usd: Decimal
    block_reason: str | None


class DelegationUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class DelegationRepository:
    """Validate against live DB state and persist correlation lineage."""

    _COLUMNS = """
        delegation_id, parent_run_id, child_run_id, parent_agent_version_id,
        child_agent_version_id, depth, organization_id, workspace_id, division_id,
        project_id, tenant_id, status, correlation_id, created_at, completed_at,
        model_calls, tool_calls, total_tokens, estimated_cost_usd, block_reason
    """

    def __init__(self, database_url: str, *, max_depth: int, max_subagents: int) -> None:
        self._database_url = psycopg_url(database_url)
        self._max_depth = max_depth
        self._max_subagents = max_subagents

    def request(
        self,
        parent_run_id: UUID,
        child_agent_version_id: UUID,
        child_scope: Scope,
        *,
        remaining_cost_budget: Decimal,
    ) -> DelegationRecord:
        with self._transaction() as connection:
            parent = connection.execute(
                """
                SELECT run.agent_run_id, run.agent_version_id, run.organization_id,
                       run.workspace_id, run.division_id, run.project_id, run.tenant_id,
                       run.correlation_id, run.status
                FROM runtime.agent_runs AS run
                WHERE run.agent_run_id = %s FOR UPDATE
                """,
                (parent_run_id,),
            ).fetchone()
            if parent is None or parent["status"] != "RUNNING":
                raise DelegationBlocked("parent Agent run must be RUNNING")
            if parent["workspace_id"] is None:
                raise DelegationBlocked("parent Agent run has no workspace scope")
            child = connection.execute(
                """
                SELECT version.lifecycle_status, contract.organization_id,
                       contract.workspace_id
                FROM agents.versions AS version
                JOIN agents.contracts AS contract USING (agent_contract_id)
                WHERE version.agent_version_id = %s
                """,
                (child_agent_version_id,),
            ).fetchone()
            parent_scope = Scope(
                organization_id=parent["organization_id"],
                workspace_id=parent["workspace_id"],
                division_id=parent["division_id"],
                project_id=parent["project_id"],
                tenant_id=parent["tenant_id"],
            )
            child_active = bool(
                child is not None
                and child["lifecycle_status"] == "ACTIVE"
                and child["organization_id"] == child_scope.organization_id
                and child["workspace_id"] == child_scope.workspace_id
            )
            parent_delegation = connection.execute(
                """
                SELECT depth FROM runtime.delegations
                WHERE child_run_id = %s ORDER BY created_at DESC LIMIT 1
                """,
                (parent_run_id,),
            ).fetchone()
            depth = (parent_delegation["depth"] if parent_delegation else 0) + 1
            active_row = connection.execute(
                """
                SELECT count(*) AS count FROM runtime.delegations
                WHERE parent_run_id = %s AND status IN ('REQUESTED', 'RUNNING')
                """,
                (parent_run_id,),
            ).fetchone()
            active_subagents = int(active_row["count"]) if active_row else 0
            lineage_rows = connection.execute(
                """
                WITH RECURSIVE lineage AS (
                    SELECT delegation.parent_run_id, delegation.child_agent_version_id
                    FROM runtime.delegations AS delegation
                    WHERE delegation.child_run_id = %s
                    UNION ALL
                    SELECT ancestor.parent_run_id, ancestor.child_agent_version_id
                    FROM runtime.delegations AS ancestor
                    JOIN lineage ON ancestor.child_run_id = lineage.parent_run_id
                )
                SELECT child_agent_version_id FROM lineage
                """,
                (parent_run_id,),
            ).fetchall()
            lineage = tuple(
                dict.fromkeys(
                    [parent["agent_version_id"]]
                    + [row["child_agent_version_id"] for row in lineage_rows]
                )
            )
            try:
                validate_delegation(
                    DelegationRequest(
                        parent_run_id=parent_run_id,
                        child_agent_version_id=child_agent_version_id,
                        parent_scope=parent_scope,
                        child_scope=child_scope,
                        active_child=child_active,
                        delegation_depth=depth - 1,
                        active_subagents=active_subagents,
                        remaining_cost_budget=float(remaining_cost_budget),
                        lineage_agent_version_ids=lineage,
                    ),
                    max_depth=self._max_depth,
                    max_subagents=self._max_subagents,
                )
            except ValueError as error:
                raise DelegationBlocked(str(error)) from error
            row = connection.execute(
                f"""
                INSERT INTO runtime.delegations (
                    parent_run_id, parent_agent_version_id, child_agent_version_id,
                    depth, organization_id, workspace_id, division_id, project_id,
                    tenant_id, status, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'REQUESTED', %s)
                RETURNING {self._COLUMNS}
                """,
                (
                    parent_run_id,
                    parent["agent_version_id"],
                    child_agent_version_id,
                    depth,
                    child_scope.organization_id,
                    child_scope.workspace_id,
                    child_scope.division_id,
                    child_scope.project_id,
                    child_scope.tenant_id,
                    parent["correlation_id"],
                ),
            ).fetchone()
            if row is None:
                raise DelegationError("delegation could not be persisted")
            self._audit(
                connection,
                organization_id=parent_scope.organization_id,
                action="AGENT_DELEGATION_REQUESTED",
                entity_id=row["delegation_id"],
                correlation_id=parent["correlation_id"],
                metadata={"parent_run_id": str(parent_run_id), "depth": depth},
            )
            return self._record(row)

    def bind_child_run(self, delegation_id: UUID, child_run_id: UUID) -> DelegationRecord:
        with self._transaction() as connection:
            current = self._load(connection, delegation_id, for_update=True)
            if current.status != DelegationStatus.REQUESTED:
                raise DelegationBlocked("delegation is not awaiting a child run")
            child = connection.execute(
                """
                SELECT organization_id, workspace_id, tenant_id, agent_version_id, status
                FROM runtime.agent_runs WHERE agent_run_id = %s
                """,
                (child_run_id,),
            ).fetchone()
            if (
                child is None
                or child["organization_id"] != current.scope.organization_id
                or child["workspace_id"] != current.scope.workspace_id
                or child["tenant_id"] != current.scope.tenant_id
                or child["agent_version_id"] != current.child_agent_version_id
                or child["status"] not in {"QUEUED", "RUNNING"}
            ):
                raise DelegationBlocked("child run does not match the delegated scope")
            row = connection.execute(
                f"""
                UPDATE runtime.delegations
                SET child_run_id = %s, status = 'RUNNING'
                WHERE delegation_id = %s AND status = 'REQUESTED'
                RETURNING {self._COLUMNS}
                """,
                (child_run_id, delegation_id),
            ).fetchone()
            if row is None:
                raise DelegationError("delegation child run could not be linked")
            return self._record(row)

    def complete(
        self,
        delegation_id: UUID,
        status: DelegationStatus,
        *,
        usage: DelegationUsage,
        block_reason: str | None = None,
    ) -> DelegationRecord:
        if status not in {
            DelegationStatus.SUCCEEDED,
            DelegationStatus.BLOCKED,
            DelegationStatus.FAILED,
            DelegationStatus.CANCELLED,
        }:
            raise DelegationError("delegation completion requires a terminal status")
        with self._transaction() as connection:
            current = self._load(connection, delegation_id, for_update=True)
            if current.status not in {DelegationStatus.REQUESTED, DelegationStatus.RUNNING}:
                raise DelegationBlocked("delegation is already terminal")
            row = connection.execute(
                f"""
                UPDATE runtime.delegations
                SET status = %s, completed_at = now(), model_calls = %s, tool_calls = %s,
                    total_tokens = %s, estimated_cost_usd = %s, block_reason = %s
                WHERE delegation_id = %s
                RETURNING {self._COLUMNS}
                """,
                (
                    status.value,
                    usage.model_calls,
                    usage.tool_calls,
                    usage.total_tokens,
                    usage.estimated_cost_usd,
                    block_reason[:1000] if block_reason else None,
                    delegation_id,
                ),
            ).fetchone()
            if row is None:
                raise DelegationError("delegation completion could not be persisted")
            return self._record(row)

    def get(self, delegation_id: UUID) -> DelegationRecord:
        with self._connection() as connection:
            return self._load(connection, delegation_id)

    def _load(
        self,
        connection: psycopg.Connection[Any],
        delegation_id: UUID,
        *,
        for_update: bool = False,
    ) -> DelegationRecord:
        lock = "FOR UPDATE" if for_update else ""
        row = connection.execute(
            f"""
            SELECT {self._COLUMNS} FROM runtime.delegations
            WHERE delegation_id = %s {lock}
            """,
            (delegation_id,),
        ).fetchone()
        if row is None:
            raise DelegationError("delegation was not found")
        return self._record(row)

    @staticmethod
    def _record(row: dict[str, Any]) -> DelegationRecord:
        if row["organization_id"] is None or row["workspace_id"] is None:
            raise DelegationError("delegation scope is incomplete")
        return DelegationRecord(
            delegation_id=row["delegation_id"],
            parent_run_id=row["parent_run_id"],
            child_run_id=row["child_run_id"],
            parent_agent_version_id=row["parent_agent_version_id"],
            child_agent_version_id=row["child_agent_version_id"],
            depth=row["depth"],
            scope=Scope(
                organization_id=row["organization_id"],
                workspace_id=row["workspace_id"],
                division_id=row["division_id"],
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
            ),
            status=row["status"],
            correlation_id=row["correlation_id"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            model_calls=row["model_calls"],
            tool_calls=row["tool_calls"],
            total_tokens=row["total_tokens"],
            estimated_cost_usd=row["estimated_cost_usd"],
            block_reason=row["block_reason"],
        )

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        action: str,
        entity_id: UUID,
        correlation_id: UUID,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, system_actor, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'SYSTEM', 'GENESIS', %s, 'AGENT_DELEGATION', %s, %s, %s, %s)
            """,
            (
                organization_id,
                action,
                entity_id,
                correlation_id,
                "Bounded Agent delegation state changed",
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

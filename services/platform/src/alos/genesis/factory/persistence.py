"""PostgreSQL persistence for the governed GENESIS Factory lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import psycopg
from psycopg.errors import ForeignKeyViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.authorization import require_division, require_tenant, require_workspace
from alos.genesis.factory.models import ImplementationDecision, RequirementUnderstanding
from alos.genesis.factory.pipeline import FactoryProposal, FactoryResolution, GeneratedTest
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class FactoryPersistenceError(RuntimeError):
    """A safe Factory persistence failure."""


class FactoryRequestNotFoundError(FactoryPersistenceError):
    """The request is absent or outside the authenticated scope."""


class FactoryRequestConflictError(FactoryPersistenceError):
    """A request violates idempotency or lifecycle requirements."""


class FactoryStatus(StrEnum):
    REQUEST = "REQUEST"
    ANALYZING = "ANALYZING"
    DRAFT = "DRAFT"
    NEEDS_CONFIGURATION = "NEEDS_CONFIGURATION"
    NEEDS_IMPLEMENTATION = "NEEDS_IMPLEMENTATION"
    BLOCKED = "BLOCKED"
    TESTING = "TESTING"
    TESTED = "TESTED"
    IN_REVIEW = "IN_REVIEW"


class FactorySourceType(StrEnum):
    DIRECT = "DIRECT"
    RESEARCH = "RESEARCH"


class FactoryRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_id: UUID | None = None
    project_id: UUID | None = None
    tenant_id: UUID | None = None
    requirement: str = Field(min_length=10, max_length=10_000)
    source_type: FactorySourceType = FactorySourceType.DIRECT
    source_research_id: UUID | None = None
    owner_user_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)


class FactoryGeneratedTestRecord(GeneratedTest):
    factory_test_id: UUID
    execution_status: str
    agent_version_id: UUID | None
    created_at: datetime


class FactoryRequestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_request_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    project_id: UUID | None
    tenant_id: UUID | None
    requirement: str
    source_type: FactorySourceType
    source_research_id: UUID | None
    status: FactoryStatus
    requirement_understanding: RequirementUnderstanding | None
    implementation_decision: ImplementationDecision | None
    dependency_resolution: FactoryResolution | None
    factory_proposal: FactoryProposal | None
    blockers: list[dict[str, Any]]
    agent_contract_id: UUID | None
    agent_version_id: UUID | None
    requested_by_user_id: UUID
    owner_user_id: UUID | None
    reviewer_user_id: UUID | None
    idempotency_key: str
    correlation_id: UUID
    last_error_code: str | None
    created_at: datetime
    analyzed_at: datetime | None
    updated_at: datetime
    generated_tests: list[FactoryGeneratedTestRecord] = Field(default_factory=list)


class FactoryRequestPage(BaseModel):
    items: list[FactoryRequestRecord]
    limit: int
    offset: int
    has_more: bool


class FactoryRepository:
    """Tenant-aware durable Factory state with transactional lifecycle writes."""

    _COLUMNS = """
        factory_request_id, organization_id, workspace_id, division_id, project_id,
        tenant_id, requirement, source_type, source_research_id, status,
        requirement_understanding, implementation_decision, dependency_resolution,
        factory_proposal, blockers, agent_contract_id, agent_version_id,
        requested_by_user_id, owner_user_id, reviewer_user_id, idempotency_key,
        correlation_id, last_error_code, created_at, analyzed_at, updated_at
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create(
        self,
        request: FactoryRequestCreate,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> FactoryRequestRecord:
        require_workspace(actor, request.workspace_id)
        require_tenant(actor, request.tenant_id)
        self._validate_source(request)
        with self._transaction() as connection:
            self._require_scope(connection, actor, request)
            try:
                row = connection.execute(
                    f"""
                    INSERT INTO genesis.factory_requests (
                        organization_id, workspace_id, division_id, project_id, tenant_id,
                        requirement, source_type, source_research_id, requested_by_user_id,
                        owner_user_id, idempotency_key, correlation_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (organization_id, requested_by_user_id, idempotency_key)
                    DO NOTHING
                    RETURNING {self._COLUMNS}
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        request.division_id,
                        request.project_id,
                        request.tenant_id,
                        request.requirement.strip(),
                        request.source_type.value,
                        request.source_research_id,
                        actor.user_id,
                        request.owner_user_id or actor.user_id,
                        request.idempotency_key,
                        correlation_id,
                    ),
                ).fetchone()
            except ForeignKeyViolation as error:
                raise FactoryRequestConflictError(
                    "Factory request references an unavailable scoped resource"
                ) from error
            if row is None:
                row = connection.execute(
                    f"""
                    SELECT {self._COLUMNS} FROM genesis.factory_requests
                    WHERE organization_id = %s AND requested_by_user_id = %s
                      AND idempotency_key = %s
                    """,
                    (actor.organization_id, actor.user_id, request.idempotency_key),
                ).fetchone()
                if row is None:
                    raise FactoryPersistenceError("idempotent Factory request could not be read")
                if not self._same_create(row, request):
                    raise FactoryRequestConflictError(
                        "idempotency key is already bound to different Factory request data"
                    )
                return self._record(connection, row)
            self._audit(
                connection,
                actor=actor,
                action="GENESIS_FACTORY_REQUEST_CREATED",
                entity_id=row["factory_request_id"],
                correlation_id=correlation_id,
                reason="A scoped GENESIS Factory requirement was persisted",
                metadata={"workspace_id": str(request.workspace_id), "status": "REQUEST"},
            )
            return self._record(connection, row)

    def get(self, request_id: UUID, actor: ActorContext) -> FactoryRequestRecord:
        with self._connection() as connection:
            row = self._load_visible(connection, request_id, actor)
            return self._record(connection, row)

    def list_requests(
        self,
        actor: ActorContext,
        *,
        workspace_id: UUID | None = None,
        status: FactoryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> FactoryRequestPage:
        if workspace_id is not None:
            require_workspace(actor, workspace_id)
        workspace_ids = [workspace_id] if workspace_id is not None else actor.workspace_ids
        if not workspace_ids:
            return FactoryRequestPage(items=[], limit=limit, offset=offset, has_more=False)
        conditions = ["organization_id = %s", "workspace_id = ANY(%s)"]
        parameters: list[Any] = [actor.organization_id, workspace_ids]
        self._append_tenant_filter(conditions, parameters, actor)
        if status is not None:
            conditions.append("status = %s")
            parameters.append(status.value)
        bounded_limit = min(max(limit, 1), 200)
        bounded_offset = max(offset, 0)
        parameters.extend([bounded_limit + 1, bounded_offset])
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {self._COLUMNS} FROM genesis.factory_requests
                WHERE {' AND '.join(conditions)}
                ORDER BY updated_at DESC, factory_request_id DESC
                LIMIT %s OFFSET %s
                """,
                parameters,
            ).fetchall()
            items = [self._record(connection, row) for row in rows[:bounded_limit]]
        return FactoryRequestPage(
            items=items,
            limit=bounded_limit,
            offset=bounded_offset,
            has_more=len(rows) > bounded_limit,
        )

    def begin_analysis(
        self, request_id: UUID, actor: ActorContext, *, correlation_id: UUID
    ) -> FactoryRequestRecord:
        with self._transaction() as connection:
            current = self._load_visible(connection, request_id, actor, for_update=True)
            if current["status"] not in {
                FactoryStatus.REQUEST.value,
                FactoryStatus.BLOCKED.value,
                FactoryStatus.NEEDS_CONFIGURATION.value,
                FactoryStatus.NEEDS_IMPLEMENTATION.value,
            }:
                raise FactoryRequestConflictError(
                    f"Factory request cannot be analyzed from {current['status']}"
                )
            row = connection.execute(
                f"""
                UPDATE genesis.factory_requests
                SET status = 'ANALYZING', last_error_code = NULL, blockers = '[]'::jsonb,
                    correlation_id = %s, updated_at = now()
                WHERE factory_request_id = %s
                RETURNING {self._COLUMNS}
                """,
                (correlation_id, request_id),
            ).fetchone()
            if row is None:
                raise FactoryPersistenceError("Factory analysis could not be started")
            self._audit(
                connection,
                actor=actor,
                action="GENESIS_FACTORY_ANALYSIS_STARTED",
                entity_id=request_id,
                correlation_id=correlation_id,
                reason="The governed Factory pipeline began semantic analysis",
                metadata={"previous_status": current["status"]},
            )
            return self._record(connection, row)

    def complete_analysis(
        self,
        request_id: UUID,
        actor: ActorContext,
        *,
        understanding: RequirementUnderstanding,
        decision: ImplementationDecision,
        proposal: FactoryProposal,
        agent_contract_id: UUID | None,
        agent_version_id: UUID | None,
        correlation_id: UUID,
    ) -> FactoryRequestRecord:
        status = self._proposal_status(proposal)
        blockers = [
            item.model_dump(mode="json")
            for item in proposal.resolution.missing_dependencies
        ]
        with self._transaction() as connection:
            current = self._load_visible(connection, request_id, actor, for_update=True)
            if current["status"] != FactoryStatus.ANALYZING.value:
                raise FactoryRequestConflictError("Factory request is not being analyzed")
            row = connection.execute(
                f"""
                UPDATE genesis.factory_requests
                SET status = %s, requirement_understanding = %s,
                    implementation_decision = %s, dependency_resolution = %s,
                    factory_proposal = %s, blockers = %s, agent_contract_id = %s,
                    agent_version_id = %s, analyzed_at = now(), updated_at = now(),
                    correlation_id = %s, last_error_code = NULL
                WHERE factory_request_id = %s
                RETURNING {self._COLUMNS}
                """,
                (
                    status.value,
                    Jsonb(understanding.model_dump(mode="json")),
                    Jsonb(decision.model_dump(mode="json")),
                    Jsonb(proposal.resolution.model_dump(mode="json")),
                    Jsonb(proposal.model_dump(mode="json")),
                    Jsonb(blockers),
                    agent_contract_id,
                    agent_version_id,
                    correlation_id,
                    request_id,
                ),
            ).fetchone()
            if row is None:
                raise FactoryPersistenceError("Factory analysis could not be persisted")
            connection.execute(
                "DELETE FROM genesis.factory_generated_tests WHERE factory_request_id = %s",
                (request_id,),
            )
            for test in proposal.tests:
                connection.execute(
                    """
                    INSERT INTO genesis.factory_generated_tests (
                        factory_request_id, category, objective, expected_status, agent_version_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        test.category,
                        test.objective,
                        test.expected_status,
                        agent_version_id,
                    ),
                )
            self._audit(
                connection,
                actor=actor,
                action="GENESIS_FACTORY_ANALYSIS_COMPLETED",
                entity_id=request_id,
                correlation_id=correlation_id,
                reason="Factory analysis, resolution, proposal, and test proposals were persisted",
                metadata={
                    "status": status.value,
                    "implementation_type": decision.implementation_type.value,
                    "agent_contract_id": str(agent_contract_id) if agent_contract_id else None,
                },
            )
            return self._record(connection, row)

    def fail_analysis(
        self,
        request_id: UUID,
        actor: ActorContext,
        *,
        error_code: str,
        reason: str,
        correlation_id: UUID,
    ) -> FactoryRequestRecord:
        blocker = {
            "key": error_code[:120],
            "kind": "FACTORY",
            "status": "BLOCKED",
            "reason": reason[:1000],
        }
        with self._transaction() as connection:
            current = self._load_visible(connection, request_id, actor, for_update=True)
            if current["status"] != FactoryStatus.ANALYZING.value:
                raise FactoryRequestConflictError("Factory request is not being analyzed")
            row = connection.execute(
                f"""
                UPDATE genesis.factory_requests
                SET status = 'BLOCKED', blockers = %s, last_error_code = %s,
                    correlation_id = %s, updated_at = now()
                WHERE factory_request_id = %s
                RETURNING {self._COLUMNS}
                """,
                (Jsonb([blocker]), error_code[:120], correlation_id, request_id),
            ).fetchone()
            if row is None:
                raise FactoryPersistenceError("Factory failure could not be persisted")
            self._audit(
                connection,
                actor=actor,
                action="GENESIS_FACTORY_ANALYSIS_BLOCKED",
                entity_id=request_id,
                correlation_id=correlation_id,
                reason="Factory analysis stopped safely",
                metadata={"error_code": error_code[:120]},
            )
            return self._record(connection, row)

    @staticmethod
    def _validate_source(request: FactoryRequestCreate) -> None:
        if (
            request.source_type == FactorySourceType.DIRECT
            and request.source_research_id is not None
        ):
            raise FactoryRequestConflictError("direct Factory requests cannot reference research")
        if request.source_type == FactorySourceType.RESEARCH and request.source_research_id is None:
            raise FactoryRequestConflictError("research Factory requests require source lineage")

    @staticmethod
    def _same_create(row: dict[str, Any], request: FactoryRequestCreate) -> bool:
        return all(
            (
                row["workspace_id"] == request.workspace_id,
                row["division_id"] == request.division_id,
                row["project_id"] == request.project_id,
                row["tenant_id"] == request.tenant_id,
                row["requirement"] == request.requirement.strip(),
                row["source_type"] == request.source_type.value,
                row["source_research_id"] == request.source_research_id,
            )
        )

    @staticmethod
    def _proposal_status(proposal: FactoryProposal) -> FactoryStatus:
        readiness = proposal.resolution.readiness.value
        if readiness == "NEEDS_CONFIGURATION":
            return FactoryStatus.NEEDS_CONFIGURATION
        if readiness == "NEEDS_IMPLEMENTATION":
            return FactoryStatus.NEEDS_IMPLEMENTATION
        if readiness == "BLOCKED":
            return FactoryStatus.BLOCKED
        return FactoryStatus.DRAFT

    def _load_visible(
        self,
        connection: psycopg.Connection[Any],
        request_id: UUID,
        actor: ActorContext,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        conditions = [
            "factory_request_id = %s",
            "organization_id = %s",
            "workspace_id = ANY(%s)",
        ]
        parameters: list[Any] = [request_id, actor.organization_id, actor.workspace_ids]
        self._append_tenant_filter(conditions, parameters, actor)
        lock = "FOR UPDATE" if for_update else ""
        row = connection.execute(
            f"""
            SELECT {self._COLUMNS} FROM genesis.factory_requests
            WHERE {' AND '.join(conditions)} {lock}
            """,
            parameters,
        ).fetchone()
        if row is None:
            raise FactoryRequestNotFoundError("Factory request was not found")
        return row

    @staticmethod
    def _append_tenant_filter(
        conditions: list[str], parameters: list[Any], actor: ActorContext
    ) -> None:
        if actor.tenant_ids:
            conditions.append("(tenant_id IS NULL OR tenant_id = ANY(%s))")
            parameters.append(actor.tenant_ids)
        else:
            conditions.append("tenant_id IS NULL")

    @staticmethod
    def _require_scope(
        connection: psycopg.Connection[Any], actor: ActorContext, request: FactoryRequestCreate
    ) -> None:
        workspace = connection.execute(
            """
            SELECT workspace.division_id, division.code AS division_code
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workspace.workspace_id
            LEFT JOIN identity.divisions AS division
              ON division.division_id = workspace.division_id
            JOIN identity.users AS actor_user
              ON actor_user.user_id = membership.user_id
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE' AND membership.user_id = %s
              AND actor_user.organization_id = %s AND actor_user.status = 'ACTIVE'
            """,
            (
                request.workspace_id,
                actor.organization_id,
                actor.user_id,
                actor.organization_id,
            ),
        ).fetchone()
        if workspace is None:
            raise FactoryRequestNotFoundError("active workspace membership is required")
        if request.division_id is not None:
            division = connection.execute(
                """
                SELECT code FROM identity.divisions
                WHERE division_id = %s AND organization_id = %s
                """,
                (request.division_id, actor.organization_id),
            ).fetchone()
            if division is None:
                raise FactoryRequestNotFoundError("division is outside the organization")
            require_division(actor, division["code"])
            if (
                workspace["division_id"] is not None
                and workspace["division_id"] != request.division_id
            ):
                raise FactoryRequestConflictError("division is outside the workspace scope")
        if request.project_id is not None:
            project = connection.execute(
                """
                SELECT division.code AS division_code
                FROM portfolio.projects AS project
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                WHERE project.project_id = %s AND project.organization_id = %s
                  AND project.workspace_id = %s AND project.status <> 'ARCHIVED'
                """,
                (request.project_id, actor.organization_id, request.workspace_id),
            ).fetchone()
            if project is None:
                raise FactoryRequestNotFoundError("project is outside the workspace scope")
            require_division(actor, project["division_code"])
        if request.source_research_id is not None:
            source = connection.execute(
                """
                SELECT 1 FROM research.projects
                WHERE research_id = %s AND organization_id = %s AND workspace_id = %s
                  AND tenant_id IS NOT DISTINCT FROM %s
                  AND status IN ('DECISION', 'CLOSED') AND decision_id IS NOT NULL
                """,
                (
                    request.source_research_id,
                    actor.organization_id,
                    request.workspace_id,
                    request.tenant_id,
                ),
            ).fetchone()
            if source is None:
                raise FactoryRequestConflictError(
                    "research must have a governed decision in the same scope before handoff"
                )

    def _record(
        self, connection: psycopg.Connection[Any], row: dict[str, Any]
    ) -> FactoryRequestRecord:
        tests = connection.execute(
            """
            SELECT factory_test_id, category, objective, expected_status, execution_status,
                   agent_version_id, created_at
            FROM genesis.factory_generated_tests
            WHERE factory_request_id = %s
            ORDER BY category, factory_test_id
            """,
            (row["factory_request_id"],),
        ).fetchall()
        return FactoryRequestRecord(
            **row,
            generated_tests=[FactoryGeneratedTestRecord(**test) for test in tests],
        )

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        *,
        actor: ActorContext,
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
            ) VALUES (%s, 'HUMAN', %s, %s, 'GENESIS_FACTORY_REQUEST', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
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

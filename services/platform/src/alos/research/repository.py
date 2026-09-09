"""Domain-neutral research persistence with immutable evidence and decisions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.authorization import require_division, require_tenant, require_workspace
from alos.genesis.factory.persistence import (
    FactoryRepository,
    FactoryRequestCreate,
    FactoryRequestRecord,
    FactorySourceType,
)
from alos.genesis.governed_foundations import ResearchStatus, Scope
from alos.identity import HumanRole
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class ResearchError(RuntimeError):
    """A safe persistent research failure."""


class ResearchNotFoundError(ResearchError):
    """Research is absent or outside authenticated scope."""


class ResearchConflictError(ResearchError):
    """Research lifecycle or evidence requirements were not satisfied."""


class ResearchArtifactType(StrEnum):
    QUESTION = "QUESTION"
    METHOD = "METHOD"
    SOURCE = "SOURCE"
    EVIDENCE = "EVIDENCE"
    FINDING = "FINDING"
    ASSUMPTION = "ASSUMPTION"
    LIMITATION = "LIMITATION"
    ALTERNATIVE = "ALTERNATIVE"
    RISK = "RISK"
    IMPACT = "IMPACT"
    COST = "COST"
    RECOMMENDATION = "RECOMMENDATION"
    EXPERIMENT_PLAN = "EXPERIMENT_PLAN"
    EVALUATION_PLAN = "EVALUATION_PLAN"


class ResearchProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    research_type: str = Field(min_length=2, max_length=100)
    domain: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    objective: str = Field(min_length=10, max_length=10_000)
    questions: tuple[str, ...] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ResearchArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: ResearchArtifactType
    payload: dict[str, Any]
    source_reference: str | None = Field(default=None, max_length=2_000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ResearchArtifact(ResearchArtifactRequest):
    research_artifact_id: UUID
    created_by_user_id: UUID
    correlation_id: UUID
    created_at: datetime
    content_trust: Literal["UNTRUSTED"] = "UNTRUSTED"


class ResearchDecision(BaseModel):
    decision_id: UUID
    decision: Literal["APPROVE_HANDOFF", "CONTINUE", "REJECT"]
    rationale: str
    decided_by_user_id: UUID
    correlation_id: UUID
    created_at: datetime


class ResearchProjectRecord(BaseModel):
    research_id: UUID
    scope: Scope
    research_type: str
    domain: str
    title: str
    objective: str
    questions: list[str]
    status: ResearchStatus
    requested_by_user_id: UUID | None
    idempotency_key: str | None
    correlation_id: UUID | None
    decision_id: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    artifacts: list[ResearchArtifact]
    decision: ResearchDecision | None


_TRANSITIONS: dict[ResearchStatus, set[ResearchStatus]] = {
    ResearchStatus.REQUEST: {ResearchStatus.SCOPING},
    ResearchStatus.SCOPING: {ResearchStatus.RESEARCH},
    ResearchStatus.RESEARCH: {ResearchStatus.EVIDENCE_COLLECTION},
    ResearchStatus.EVIDENCE_COLLECTION: {ResearchStatus.ANALYSIS},
    ResearchStatus.ANALYSIS: {ResearchStatus.FINDINGS},
    ResearchStatus.FINDINGS: {ResearchStatus.RECOMMENDATION},
    ResearchStatus.RECOMMENDATION: {
        ResearchStatus.EXPERIMENT,
        ResearchStatus.EVALUATION,
        ResearchStatus.REVIEW,
    },
    ResearchStatus.EXPERIMENT: {ResearchStatus.EVALUATION},
    ResearchStatus.EVALUATION: {ResearchStatus.REVIEW},
    ResearchStatus.REVIEW: {ResearchStatus.DECISION},
    ResearchStatus.DECISION: {ResearchStatus.CLOSED},
    ResearchStatus.CLOSED: set(),
}


class ResearchRepository:
    """Persist research without granting it authority to change production."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create(
        self,
        request: ResearchProjectCreate,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> ResearchProjectRecord:
        self._authorize_scope(actor, request.scope)
        with self._transaction() as connection:
            self._require_database_scope(connection, actor, request.scope)
            row = connection.execute(
                """
                INSERT INTO research.projects (
                    organization_id, workspace_id, division_id, project_id, tenant_id,
                    research_type, domain, title, objective, questions, status,
                    requested_by_user_id, idempotency_key, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'REQUEST', %s, %s, %s)
                ON CONFLICT (organization_id, requested_by_user_id, idempotency_key)
                    WHERE requested_by_user_id IS NOT NULL AND idempotency_key IS NOT NULL
                DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING research_id
                """,
                (
                    request.scope.organization_id,
                    request.scope.workspace_id,
                    request.scope.division_id,
                    request.scope.project_id,
                    request.scope.tenant_id,
                    request.research_type,
                    request.domain,
                    request.title,
                    request.objective,
                    Jsonb(list(request.questions)),
                    actor.user_id,
                    request.idempotency_key,
                    correlation_id,
                ),
            ).fetchone()
            if row is None:
                raise ResearchError("research project could not be persisted")
            self._audit(
                connection,
                actor,
                action="RESEARCH_PROJECT_CREATED",
                entity_id=row["research_id"],
                correlation_id=correlation_id,
                metadata={"domain": request.domain, "status": "REQUEST"},
            )
            return self._load(connection, row["research_id"], actor)

    def add_artifact(
        self,
        research_id: UUID,
        request: ResearchArtifactRequest,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> ResearchArtifact:
        with self._transaction() as connection:
            project = self._load(connection, research_id, actor, for_update=True)
            if project.status in {ResearchStatus.DECISION, ResearchStatus.CLOSED}:
                raise ResearchConflictError("decided research evidence is immutable")
            row = connection.execute(
                """
                INSERT INTO research.artifacts (
                    research_id, artifact_type, payload, source_reference, confidence,
                    created_by_user_id, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING research_artifact_id, artifact_type, payload, source_reference,
                          confidence, created_by_user_id, correlation_id, created_at
                """,
                (
                    research_id,
                    request.artifact_type.value,
                    Jsonb(request.payload),
                    request.source_reference,
                    request.confidence,
                    actor.user_id,
                    correlation_id,
                ),
            ).fetchone()
            if row is None:
                raise ResearchError("research artifact could not be persisted")
            self._audit(
                connection,
                actor,
                action="RESEARCH_ARTIFACT_APPENDED",
                entity_id=row["research_artifact_id"],
                correlation_id=correlation_id,
                metadata={
                    "research_id": str(research_id),
                    "artifact_type": request.artifact_type.value,
                },
            )
            return ResearchArtifact(**row)

    def transition(
        self,
        research_id: UUID,
        target: ResearchStatus,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> ResearchProjectRecord:
        with self._transaction() as connection:
            project = self._load(connection, research_id, actor, for_update=True)
            if target not in _TRANSITIONS[project.status]:
                raise ResearchConflictError(
                    f"invalid research lifecycle transition: {project.status} -> {target}"
                )
            self._require_transition_evidence(project, target)
            row = connection.execute(
                """
                UPDATE research.projects
                SET status = %s, updated_at = now(),
                    completed_at = CASE WHEN %s = 'CLOSED' THEN now() ELSE completed_at END
                WHERE research_id = %s AND status = %s RETURNING research_id
                """,
                (target.value, target.value, research_id, project.status.value),
            ).fetchone()
            if row is None:
                raise ResearchConflictError("research lifecycle changed concurrently")
            self._audit(
                connection,
                actor,
                action="RESEARCH_LIFECYCLE_TRANSITIONED",
                entity_id=research_id,
                correlation_id=correlation_id,
                metadata={"from": project.status.value, "to": target.value},
            )
            return self._load(connection, research_id, actor)

    def decide(
        self,
        research_id: UUID,
        decision: Literal["APPROVE_HANDOFF", "CONTINUE", "REJECT"],
        rationale: str,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> ResearchProjectRecord:
        if not {HumanRole.DIRECTOR, HumanRole.BUSINESS_REVIEWER}.intersection(actor.roles):
            raise ResearchConflictError("independent research decision role is required")
        with self._transaction() as connection:
            project = self._load(connection, research_id, actor, for_update=True)
            if project.status != ResearchStatus.REVIEW:
                raise ResearchConflictError("research must be in REVIEW before decision")
            if project.requested_by_user_id == actor.user_id:
                raise ResearchConflictError("research requester cannot approve their own handoff")
            row = connection.execute(
                """
                INSERT INTO research.decisions (
                    research_id, decision, rationale, decided_by_user_id, correlation_id
                ) VALUES (%s, %s, %s, %s, %s) RETURNING decision_id
                """,
                (research_id, decision, rationale, actor.user_id, correlation_id),
            ).fetchone()
            if row is None:
                raise ResearchError("research decision could not be persisted")
            connection.execute(
                """
                UPDATE research.projects
                SET decision_id = %s, status = 'DECISION', updated_at = now()
                WHERE research_id = %s
                """,
                (row["decision_id"], research_id),
            )
            self._audit(
                connection,
                actor,
                action="RESEARCH_DECIDED",
                entity_id=research_id,
                correlation_id=correlation_id,
                metadata={"decision": decision, "decision_id": str(row["decision_id"])},
            )
            return self._load(connection, research_id, actor)

    def create_factory_handoff(
        self,
        research_id: UUID,
        factory: FactoryRepository,
        actor: ActorContext,
        *,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> FactoryRequestRecord:
        project = self.get(research_id, actor)
        if (
            project.status not in {ResearchStatus.DECISION, ResearchStatus.CLOSED}
            or project.decision is None
            or project.decision.decision != "APPROVE_HANDOFF"
        ):
            raise ResearchConflictError("research lacks an approved governed Factory handoff")
        recommendation = next(
            (
                artifact
                for artifact in reversed(project.artifacts)
                if artifact.artifact_type == ResearchArtifactType.RECOMMENDATION
            ),
            None,
        )
        if recommendation is None:
            raise ResearchConflictError("research has no recommendation to hand off")
        text = recommendation.payload.get("recommendation")
        if not isinstance(text, str) or len(text.strip()) < 10:
            raise ResearchConflictError("research recommendation is invalid")
        return factory.create(
            FactoryRequestCreate(
                workspace_id=project.scope.workspace_id,
                division_id=project.scope.division_id,
                project_id=project.scope.project_id,
                tenant_id=project.scope.tenant_id,
                requirement=text.strip(),
                source_type=FactorySourceType.RESEARCH,
                source_research_id=research_id,
                owner_user_id=project.requested_by_user_id,
                idempotency_key=idempotency_key,
            ),
            actor,
            correlation_id=correlation_id,
        )

    def get(self, research_id: UUID, actor: ActorContext) -> ResearchProjectRecord:
        with self._connection() as connection:
            return self._load(connection, research_id, actor)

    @staticmethod
    def _require_transition_evidence(
        project: ResearchProjectRecord, target: ResearchStatus
    ) -> None:
        types = {artifact.artifact_type for artifact in project.artifacts}
        required = {
            ResearchStatus.EVIDENCE_COLLECTION: {ResearchArtifactType.METHOD},
            ResearchStatus.ANALYSIS: {ResearchArtifactType.EVIDENCE},
            ResearchStatus.FINDINGS: {ResearchArtifactType.FINDING},
            ResearchStatus.RECOMMENDATION: {ResearchArtifactType.RECOMMENDATION},
            ResearchStatus.REVIEW: {
                ResearchArtifactType.EVIDENCE,
                ResearchArtifactType.FINDING,
                ResearchArtifactType.RECOMMENDATION,
            },
        }.get(target, set())
        if not required.issubset(types):
            missing = ", ".join(sorted(item.value for item in required - types))
            raise ResearchConflictError(f"research transition requires artifacts: {missing}")

    def _load(
        self,
        connection: psycopg.Connection[Any],
        research_id: UUID,
        actor: ActorContext,
        *,
        for_update: bool = False,
    ) -> ResearchProjectRecord:
        tenant = (
            "AND (tenant_id IS NULL OR tenant_id = ANY(%s))"
            if actor.tenant_ids
            else "AND tenant_id IS NULL"
        )
        params: list[Any] = [research_id, actor.organization_id, actor.workspace_ids]
        if actor.tenant_ids:
            params.append(actor.tenant_ids)
        lock = "FOR UPDATE" if for_update else ""
        row = connection.execute(
            f"""
            SELECT research_id, organization_id, workspace_id, division_id, project_id,
                   tenant_id, research_type, domain, title, objective, questions, status,
                   requested_by_user_id, idempotency_key, correlation_id, decision_id,
                   created_at, updated_at, completed_at
            FROM research.projects
            WHERE research_id = %s AND organization_id = %s AND workspace_id = ANY(%s)
              {tenant} {lock}
            """,
            params,
        ).fetchone()
        if row is None:
            raise ResearchNotFoundError("research project was not found")
        scope = Scope(
            organization_id=row["organization_id"],
            workspace_id=row["workspace_id"],
            division_id=row["division_id"],
            project_id=row["project_id"],
            tenant_id=row["tenant_id"],
        )
        self._authorize_scope(actor, scope)
        self._require_database_scope(connection, actor, scope)
        artifacts = connection.execute(
            """
            SELECT research_artifact_id, artifact_type, payload, source_reference,
                   confidence, created_by_user_id, correlation_id, created_at
            FROM research.artifacts WHERE research_id = %s
            ORDER BY created_at, research_artifact_id
            """,
            (research_id,),
        ).fetchall()
        decision = connection.execute(
            """
            SELECT decision_id, decision, rationale, decided_by_user_id,
                   correlation_id, created_at
            FROM research.decisions WHERE research_id = %s
            """,
            (research_id,),
        ).fetchone()
        return ResearchProjectRecord(
            research_id=research_id,
            scope=scope,
            research_type=row["research_type"],
            domain=row["domain"],
            title=row["title"],
            objective=row["objective"],
            questions=row["questions"],
            status=row["status"],
            requested_by_user_id=row["requested_by_user_id"],
            idempotency_key=row["idempotency_key"],
            correlation_id=row["correlation_id"],
            decision_id=row["decision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            artifacts=[ResearchArtifact(**artifact) for artifact in artifacts],
            decision=ResearchDecision(**decision) if decision else None,
        )

    @staticmethod
    def _authorize_scope(actor: ActorContext, scope: Scope) -> None:
        if scope.organization_id != actor.organization_id:
            raise ResearchNotFoundError("research scope is outside the organization")
        require_workspace(actor, scope.workspace_id)
        require_tenant(actor, scope.tenant_id)

    @staticmethod
    def _require_database_scope(
        connection: psycopg.Connection[Any], actor: ActorContext, scope: Scope
    ) -> None:
        workspace = connection.execute(
            """
            SELECT division.code AS division_code
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership USING (workspace_id)
            LEFT JOIN identity.divisions AS division ON division.division_id = %s
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE' AND membership.user_id = %s
            """,
            (scope.division_id, scope.workspace_id, actor.organization_id, actor.user_id),
        ).fetchone()
        if workspace is None:
            raise ResearchNotFoundError("active workspace membership is required")
        if scope.division_id is not None:
            require_division(actor, workspace["division_code"])
        if scope.project_id is not None:
            project = connection.execute(
                """
                SELECT 1 FROM portfolio.projects
                WHERE project_id = %s AND organization_id = %s AND workspace_id = %s
                  AND (%s::uuid IS NULL OR division_id = %s) AND status <> 'ARCHIVED'
                """,
                (
                    scope.project_id,
                    actor.organization_id,
                    scope.workspace_id,
                    scope.division_id,
                    scope.division_id,
                ),
            ).fetchone()
            if project is None:
                raise ResearchNotFoundError("research project scope is not authorized")

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        *,
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
            ) VALUES (%s, 'HUMAN', %s, %s, 'RESEARCH_PROJECT', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_id,
                correlation_id,
                "Generic governed research state changed",
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

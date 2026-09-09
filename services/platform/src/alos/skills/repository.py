"""Scoped Skill persistence and lifecycle enforcement."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.authorization import require_division, require_tenant, require_workspace
from alos.genesis.governed_foundations import Scope, SkillStatus, validate_skill_transition
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class SkillRegistryError(RuntimeError):
    """A safe governed Skill registry failure."""


class SkillNotFoundError(SkillRegistryError):
    """Skill is missing or outside the authenticated scope."""


class SkillConflictError(SkillRegistryError):
    """Skill identity or lifecycle transition conflicts with current state."""


class SkillDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    skill_key: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    name: str = Field(min_length=2, max_length=200)
    semantic_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    procedure: dict[str, Any]
    required_permissions: tuple[str, ...] = ()


class SkillVersionRecord(BaseModel):
    skill_version_id: UUID
    semantic_version: str
    status: SkillStatus
    procedure: dict[str, Any]
    required_permissions: list[str]
    digest: str
    created_at: datetime
    activated_at: datetime | None
    updated_at: datetime


class SkillRecord(BaseModel):
    skill_id: UUID
    scope: Scope
    skill_key: str
    name: str
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    versions: list[SkillVersionRecord]


class SkillRegistry:
    """Persist versions and resolve only ACTIVE Skills inside actor scope."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_draft(
        self,
        request: SkillDraftRequest,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> SkillRecord:
        self._authorize_scope(actor, request.scope)
        digest = self._digest(request.procedure)
        with self._transaction() as connection:
            self._require_database_scope(connection, actor, request.scope)
            try:
                skill = connection.execute(
                    """
                    INSERT INTO skills.skills (
                        organization_id, workspace_id, division_id, project_id, tenant_id,
                        skill_key, name, owner_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (organization_id, workspace_id, tenant_id, skill_key)
                    DO UPDATE SET name = EXCLUDED.name, updated_at = now()
                    RETURNING skill_id
                    """,
                    (
                        request.scope.organization_id,
                        request.scope.workspace_id,
                        request.scope.division_id,
                        request.scope.project_id,
                        request.scope.tenant_id,
                        request.skill_key,
                        request.name,
                        actor.user_id,
                    ),
                ).fetchone()
                if skill is None:
                    raise SkillRegistryError("Skill identity could not be persisted")
                connection.execute(
                    """
                    INSERT INTO skills.versions (
                        skill_id, organization_id, workspace_id, skill_key, semantic_version,
                        status, procedure, required_permissions, digest
                    ) VALUES (%s, %s, %s, %s, %s, 'DRAFT', %s, %s, %s)
                    """,
                    (
                        skill["skill_id"],
                        request.scope.organization_id,
                        request.scope.workspace_id,
                        request.skill_key,
                        request.semantic_version,
                        Jsonb(request.procedure),
                        list(request.required_permissions),
                        digest,
                    ),
                )
            except UniqueViolation as error:
                raise SkillConflictError("Skill version already exists") from error
            self._audit(
                connection,
                actor,
                action="SKILL_DRAFT_CREATED",
                entity_id=skill["skill_id"],
                correlation_id=correlation_id,
                metadata={
                    "skill_key": request.skill_key,
                    "semantic_version": request.semantic_version,
                    "digest": digest,
                },
            )
            return self._load(connection, skill["skill_id"], actor)

    def transition(
        self,
        skill_id: UUID,
        semantic_version: str,
        target: SkillStatus,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> SkillRecord:
        with self._transaction() as connection:
            skill = self._load(connection, skill_id, actor, for_update=True)
            version = next(
                (item for item in skill.versions if item.semantic_version == semantic_version),
                None,
            )
            if version is None:
                raise SkillNotFoundError("Skill version was not found")
            try:
                validate_skill_transition(version.status, target)
            except ValueError as error:
                raise SkillConflictError(str(error)) from error
            connection.execute(
                """
                UPDATE skills.versions
                SET status = %s,
                    activated_at = CASE WHEN %s = 'ACTIVE' THEN now() ELSE activated_at END,
                    updated_at = now()
                WHERE skill_id = %s AND semantic_version = %s AND status = %s
                """,
                (target.value, target.value, skill_id, semantic_version, version.status.value),
            )
            self._audit(
                connection,
                actor,
                action="SKILL_LIFECYCLE_TRANSITIONED",
                entity_id=skill_id,
                correlation_id=correlation_id,
                metadata={
                    "semantic_version": semantic_version,
                    "from": version.status.value,
                    "to": target.value,
                },
            )
            return self._load(connection, skill_id, actor)

    def get(self, skill_id: UUID, actor: ActorContext) -> SkillRecord:
        with self._connection() as connection:
            return self._load(connection, skill_id, actor)

    def resolve_active(
        self,
        skill_key: str,
        scope: Scope,
        actor: ActorContext,
    ) -> SkillVersionRecord:
        self._authorize_scope(actor, scope)
        with self._connection() as connection:
            self._require_database_scope(connection, actor, scope)
            row = connection.execute(
                """
                SELECT version.skill_version_id, version.semantic_version, version.status,
                       version.procedure, version.required_permissions, version.digest,
                       version.created_at, version.activated_at, version.updated_at
                FROM skills.skills AS skill
                JOIN skills.versions AS version USING (skill_id)
                WHERE skill.organization_id = %s AND skill.workspace_id = %s
                  AND skill.tenant_id IS NOT DISTINCT FROM %s
                  AND skill.division_id IS NOT DISTINCT FROM %s
                  AND skill.project_id IS NOT DISTINCT FROM %s
                  AND skill.skill_key = %s AND version.status = 'ACTIVE'
                ORDER BY version.activated_at DESC LIMIT 1
                """,
                (
                    scope.organization_id,
                    scope.workspace_id,
                    scope.tenant_id,
                    scope.division_id,
                    scope.project_id,
                    skill_key,
                ),
            ).fetchone()
        if row is None:
            raise SkillNotFoundError("an ACTIVE Skill version was not found in scope")
        return SkillVersionRecord(**row)

    def _load(
        self,
        connection: psycopg.Connection[Any],
        skill_id: UUID,
        actor: ActorContext,
        *,
        for_update: bool = False,
    ) -> SkillRecord:
        tenant_condition = (
            "AND (tenant_id IS NULL OR tenant_id = ANY(%s))"
            if actor.tenant_ids
            else "AND tenant_id IS NULL"
        )
        params: list[Any] = [skill_id, actor.organization_id, actor.workspace_ids]
        if actor.tenant_ids:
            params.append(actor.tenant_ids)
        lock = "FOR UPDATE" if for_update else ""
        row = connection.execute(
            f"""
            SELECT skill_id, organization_id, workspace_id, division_id, project_id,
                   tenant_id, skill_key, name, owner_user_id, created_at, updated_at
            FROM skills.skills
            WHERE skill_id = %s AND organization_id = %s AND workspace_id = ANY(%s)
              {tenant_condition} {lock}
            """,
            params,
        ).fetchone()
        if row is None:
            raise SkillNotFoundError("Skill was not found")
        scope = Scope(
            organization_id=row["organization_id"],
            workspace_id=row["workspace_id"],
            division_id=row["division_id"],
            project_id=row["project_id"],
            tenant_id=row["tenant_id"],
        )
        self._authorize_scope(actor, scope)
        self._require_database_scope(connection, actor, scope)
        versions = connection.execute(
            """
            SELECT skill_version_id, semantic_version, status, procedure,
                   required_permissions, digest, created_at, activated_at, updated_at
            FROM skills.versions WHERE skill_id = %s
            ORDER BY created_at, skill_version_id
            """,
            (skill_id,),
        ).fetchall()
        return SkillRecord(
            skill_id=skill_id,
            scope=scope,
            skill_key=row["skill_key"],
            name=row["name"],
            owner_user_id=row["owner_user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            versions=[SkillVersionRecord(**version) for version in versions],
        )

    @staticmethod
    def _authorize_scope(actor: ActorContext, scope: Scope) -> None:
        if scope.organization_id != actor.organization_id:
            raise SkillNotFoundError("Skill scope is outside the organization")
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
            raise SkillNotFoundError("active workspace membership is required")
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
                raise SkillNotFoundError("Skill project is outside the authorized scope")

    @staticmethod
    def _digest(procedure: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(procedure, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

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
            ) VALUES (%s, 'HUMAN', %s, %s, 'SKILL', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_id,
                correlation_id,
                "Governed Skill state changed",
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

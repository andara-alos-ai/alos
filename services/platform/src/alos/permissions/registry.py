"""Version-bound Permission Policy Registry with independent approval."""

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

PermissionEffect = Literal["ALLOW", "DENY"]
PermissionState = Literal["DRAFT", "IN_REVIEW", "APPROVED", "REVOKED"]


class PermissionRegistryError(RuntimeError):
    """A safe Permission Policy Registry failure."""


class PermissionConflictError(PermissionRegistryError):
    """Policy state, scope, or uniqueness forbids the requested change."""


class PermissionNotFoundError(PermissionRegistryError):
    """Policy or Agent Version cannot be found in the supplied workspace."""


class PermissionPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    semantic_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    permission_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    effect: PermissionEffect
    resource_scope: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mvp_read_only_scope(self) -> PermissionPolicyRequest:
        if self.effect == "ALLOW":
            if self.resource_scope.get("access_mode") != "READ_ONLY":
                raise ValueError("an ALLOW permission must be limited to READ_ONLY access")
            if self.resource_scope.get("classification") not in {"PUBLIC", "INTERNAL"}:
                raise ValueError("MVP permission classification must be PUBLIC or INTERNAL")
        return self


class PermissionPolicyRecord(BaseModel):
    permission_policy_id: UUID
    organization_id: UUID
    workspace_id: UUID | None
    agent_version_id: UUID
    permission_key: str
    effect: PermissionEffect
    resource_scope: dict[str, Any]
    approval_required: bool
    lifecycle_status: PermissionState
    created_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    created_at: datetime


class PermissionRegistryRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_draft(
        self,
        request: PermissionPolicyRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> PermissionPolicyRecord:
        with self._transaction() as connection:
            self._require_workspace_actor(
                connection, organization_id, actor_user_id, request.workspace_id
            )
            version = self._agent_version(connection, organization_id, request)
            try:
                row = connection.execute(
                    """
                    INSERT INTO governance.permission_policies (
                        organization_id, workspace_id, agent_version_id, permission_key, effect,
                        resource_scope, approval_required, lifecycle_status, created_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, true, 'DRAFT', %s)
                    RETURNING permission_policy_id, organization_id, workspace_id, agent_version_id,
                              permission_key, effect, resource_scope, approval_required,
                              lifecycle_status, created_by_user_id, approved_by_user_id, created_at
                    """,
                    (
                        organization_id,
                        request.workspace_id,
                        version["agent_version_id"],
                        request.permission_key,
                        request.effect,
                        Jsonb(request.resource_scope),
                        actor_user_id,
                    ),
                ).fetchone()
            except UniqueViolation as error:
                raise PermissionConflictError(
                    "permission key already has a policy for this Agent Version"
                ) from error
            if row is None:
                raise PermissionRegistryError("permission policy could not be created")
            self._audit(
                connection,
                organization_id,
                actor_user_id,
                "PERMISSION_POLICY_DRAFTED",
                row["permission_policy_id"],
                correlation_id,
                "Human registered a version-bound permission policy draft",
                {"permission_key": request.permission_key, "agent_key": request.agent_key},
            )
            return PermissionPolicyRecord(**row)

    def approve(
        self,
        permission_policy_id: UUID,
        *,
        organization_id: UUID,
        approver_user_id: UUID,
        correlation_id: UUID,
    ) -> PermissionPolicyRecord:
        with self._transaction() as connection:
            self._require_org_actor(connection, organization_id, approver_user_id)
            policy = connection.execute(
                """
                SELECT permission_policy_id, organization_id, workspace_id, agent_version_id,
                       permission_key, effect, resource_scope, approval_required, lifecycle_status,
                       created_by_user_id, approved_by_user_id, created_at
                FROM governance.permission_policies
                WHERE permission_policy_id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (permission_policy_id, organization_id),
            ).fetchone()
            if policy is None:
                raise PermissionNotFoundError("permission policy was not found")
            if policy["created_by_user_id"] == approver_user_id:
                raise PermissionConflictError("permission policy maker cannot approve it")
            if policy["lifecycle_status"] != "DRAFT":
                raise PermissionConflictError("only a draft permission policy can be approved")
            PermissionPolicyRequest(
                workspace_id=policy["workspace_id"],
                agent_key=self._agent_key(connection, policy["agent_version_id"]),
                semantic_version=self._semantic_version(connection, policy["agent_version_id"]),
                permission_key=policy["permission_key"],
                effect=policy["effect"],
                resource_scope=policy["resource_scope"],
            )
            row = connection.execute(
                """
                UPDATE governance.permission_policies
                SET lifecycle_status = 'APPROVED', approved_by_user_id = %s
                WHERE permission_policy_id = %s
                RETURNING permission_policy_id, organization_id, workspace_id, agent_version_id,
                          permission_key, effect, resource_scope, approval_required,
                          lifecycle_status, created_by_user_id, approved_by_user_id, created_at
                """,
                (approver_user_id, permission_policy_id),
            ).fetchone()
            if row is None:
                raise PermissionRegistryError("permission policy could not be approved")
            self._audit(
                connection,
                organization_id,
                approver_user_id,
                "PERMISSION_POLICY_APPROVED",
                permission_policy_id,
                correlation_id,
                "Independent human approved a version-bound read-only permission",
                {"permission_key": row["permission_key"]},
            )
            return PermissionPolicyRecord(**row)

    def list_policies(
        self, organization_id: UUID, *, agent_key: str | None = None
    ) -> list[PermissionPolicyRecord]:
        with self._connection() as connection:
            conditions = ["policy.organization_id = %s"]
            parameters: list[Any] = [organization_id]
            if agent_key is not None:
                conditions.append("contract.agent_key = %s")
                parameters.append(agent_key)
            where = " AND ".join(conditions)
            rows = connection.execute(
                f"""
                SELECT policy.permission_policy_id, policy.organization_id, policy.workspace_id,
                       policy.agent_version_id, policy.permission_key, policy.effect,
                       policy.resource_scope, policy.approval_required, policy.lifecycle_status,
                       policy.created_by_user_id, policy.approved_by_user_id, policy.created_at
                FROM governance.permission_policies AS policy
                JOIN agents.versions AS version
                  ON version.agent_version_id = policy.agent_version_id
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = version.agent_contract_id
                WHERE {where}
                ORDER BY policy.created_at DESC, policy.permission_policy_id DESC
                """,
                parameters,
            ).fetchall()
        return [PermissionPolicyRecord(**row) for row in rows]

    @staticmethod
    def _agent_version(
        connection: psycopg.Connection[Any], organization_id: UUID, request: PermissionPolicyRequest
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT version.agent_version_id
            FROM agents.contracts AS contract
            JOIN agents.versions AS version
              ON version.agent_contract_id = contract.agent_contract_id
            WHERE contract.organization_id = %s AND contract.workspace_id = %s
              AND contract.agent_key = %s AND version.semantic_version = %s
            """,
            (organization_id, request.workspace_id, request.agent_key, request.semantic_version),
        ).fetchone()
        if row is None:
            raise PermissionNotFoundError("Agent Version was not found in this workspace")
        return dict(row)

    @staticmethod
    def _agent_key(connection: psycopg.Connection[Any], agent_version_id: UUID) -> str:
        row = connection.execute(
            """
            SELECT contract.agent_key FROM agents.contracts AS contract
            JOIN agents.versions AS version
              ON version.agent_contract_id = contract.agent_contract_id
            WHERE version.agent_version_id = %s
            """,
            (agent_version_id,),
        ).fetchone()
        if row is None:
            raise PermissionNotFoundError("Agent Version was not found")
        return str(row["agent_key"])

    @staticmethod
    def _semantic_version(connection: psycopg.Connection[Any], agent_version_id: UUID) -> str:
        row = connection.execute(
            "SELECT semantic_version FROM agents.versions WHERE agent_version_id = %s",
            (agent_version_id,),
        ).fetchone()
        if row is None:
            raise PermissionNotFoundError("Agent Version was not found")
        return str(row["semantic_version"])

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
            raise PermissionRegistryError("active workspace membership is required")

    @staticmethod
    def _require_org_actor(
        connection: psycopg.Connection[Any], organization_id: UUID, actor_user_id: UUID
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM identity.users WHERE organization_id = %s AND user_id = %s",
            (organization_id, actor_user_id),
        ).fetchone() is None:
            raise PermissionRegistryError("actor does not belong to the organization")

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
            ) VALUES (%s, 'HUMAN', %s, %s, 'PERMISSION_POLICY', %s, %s, %s, %s)
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

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
PermissionAccessMode = Literal[
    "READ", "CREATE_DRAFT", "UPDATE_SCOPED", "REQUEST_APPROVAL", "EXECUTE_APPROVED_ACTION"
]


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
    permission_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:]{2,119}$")
    effect: PermissionEffect
    resource_scope: dict[str, Any] = Field(default_factory=dict)
    capability_key: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
    )
    tool_key: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
    )
    access_mode: PermissionAccessMode = "READ"
    resource_type: str = Field(default="GENERIC", min_length=2, max_length=80)
    division_scope: UUID | None = None
    project_scope: UUID | None = None
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "INTERNAL"
    conditions: dict[str, Any] = Field(default_factory=dict)
    approval_required: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> PermissionPolicyRequest:
        if self.effect == "ALLOW":
            legacy_mode = self.resource_scope.get("access_mode")
            if legacy_mode not in {None, "READ_ONLY", self.access_mode}:
                raise ValueError("resource scope access mode conflicts with permission access mode")
            legacy_classification = self.resource_scope.get("classification")
            if legacy_classification is not None and legacy_classification != self.classification:
                raise ValueError(
                    "resource scope classification conflicts with permission classification"
                )
            if self.access_mode == "EXECUTE_APPROVED_ACTION" and not self.approval_required:
                raise ValueError("direct execution requires approval")
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
    capability_key: str | None = None
    tool_key: str | None = None
    access_mode: PermissionAccessMode = "READ"
    resource_type: str = "GENERIC"
    division_scope: UUID | None = None
    project_scope: UUID | None = None
    classification: str = "INTERNAL"
    conditions: dict[str, Any] = Field(default_factory=dict)
    agent_key: str | None = None
    agent_name: str | None = None
    semantic_version: str | None = None


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
                        resource_scope, approval_required, lifecycle_status, created_by_user_id,
                        capability_key, tool_key, access_mode, resource_type, organization_scope,
                        division_scope, project_scope, classification, conditions
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, 'DRAFT', %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING permission_policy_id, organization_id, workspace_id, agent_version_id,
                              permission_key, effect, resource_scope, approval_required,
                              lifecycle_status, created_by_user_id, approved_by_user_id, created_at,
                              capability_key, tool_key, access_mode, resource_type, division_scope,
                              project_scope, classification, conditions
                    """,
                    (
                        organization_id,
                        request.workspace_id,
                        version["agent_version_id"],
                        request.permission_key,
                        request.effect,
                        Jsonb(request.resource_scope),
                        request.approval_required,
                        actor_user_id,
                        request.capability_key,
                        request.tool_key,
                        request.access_mode,
                        request.resource_type,
                        organization_id,
                        request.division_scope,
                        request.project_scope,
                        request.classification,
                        Jsonb(request.conditions),
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
            agent_key, agent_name, semantic_version = self._agent_info(
                connection, version["agent_version_id"]
            )
            record_data = dict(row)
            record_data["agent_key"] = agent_key
            record_data["agent_name"] = agent_name
            record_data["semantic_version"] = semantic_version
            return PermissionPolicyRecord(**record_data)

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
                       created_by_user_id, approved_by_user_id, created_at, capability_key,
                       tool_key, access_mode, resource_type, division_scope, project_scope,
                       classification, conditions
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
                capability_key=policy["capability_key"],
                tool_key=policy["tool_key"],
                access_mode=policy["access_mode"],
                resource_type=policy["resource_type"],
                division_scope=policy["division_scope"],
                project_scope=policy["project_scope"],
                classification=policy["classification"],
                conditions=policy["conditions"],
                approval_required=policy["approval_required"],
            )
            row = connection.execute(
                """
                UPDATE governance.permission_policies
                SET lifecycle_status = 'APPROVED', approved_by_user_id = %s
                WHERE permission_policy_id = %s
                RETURNING permission_policy_id, organization_id, workspace_id, agent_version_id,
                          permission_key, effect, resource_scope, approval_required,
                          lifecycle_status, created_by_user_id, approved_by_user_id, created_at,
                          capability_key, tool_key, access_mode, resource_type, division_scope,
                          project_scope, classification, conditions
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
                "Independent human approved a version-bound permission",
                {"permission_key": row["permission_key"]},
            )
            agent_key, agent_name, semantic_version = self._agent_info(
                connection, row["agent_version_id"]
            )
            record_data = dict(row)
            record_data["agent_key"] = agent_key
            record_data["agent_name"] = agent_name
            record_data["semantic_version"] = semantic_version
            return PermissionPolicyRecord(**record_data)

    def sync_contract_permissions(
        self, connection: psycopg.Connection[Any], organization_id: UUID
    ) -> None:
        """Ensure all permission_keys defined in Agent Contract snapshots have a DRAFT record."""
        agent_versions = connection.execute(
            """
            SELECT contract.workspace_id, contract.owner_user_id,
                   version.agent_version_id, version.contract_snapshot
            FROM agents.contracts AS contract
            JOIN agents.versions AS version
              ON version.agent_contract_id = contract.agent_contract_id
            WHERE contract.organization_id = %s
            """,
            (organization_id,),
        ).fetchall()
        for row in agent_versions:
            snapshot = row["contract_snapshot"] or {}
            permission_keys = snapshot.get("permission_keys") or []
            for perm_key in permission_keys:
                if not perm_key or not isinstance(perm_key, str):
                    continue
                try:
                    with connection.transaction():
                        connection.execute(
                            """
                            INSERT INTO governance.permission_policies (
                                organization_id, workspace_id, agent_version_id, permission_key,
                                effect, resource_scope, approval_required, lifecycle_status,
                                created_by_user_id, access_mode, resource_type, classification
                            ) VALUES (
                                %s, %s, %s, %s, 'ALLOW',
                                '{"access_mode": "READ_ONLY", "classification": "INTERNAL"}'::jsonb,
                                true, 'DRAFT', %s, 'READ', 'GENERIC', 'INTERNAL'
                            )
                            ON CONFLICT (agent_version_id, permission_key) DO NOTHING
                            """,
                            (
                                organization_id,
                                row["workspace_id"],
                                row["agent_version_id"],
                                perm_key,
                                row["owner_user_id"],
                            ),
                        )
                except Exception:
                    continue

    def list_policies(
        self,
        organization_id: UUID,
        *,
        workspace_id: UUID | None = None,
        agent_key: str | None = None,
    ) -> list[PermissionPolicyRecord]:
        with self._connection() as connection:
            self.sync_contract_permissions(connection, organization_id)
            conditions = ["policy.organization_id = %s"]
            parameters: list[Any] = [organization_id]
            if workspace_id is not None:
                conditions.append(
                    "COALESCE(policy.workspace_id, contract.workspace_id) = %s"
                )
                parameters.append(workspace_id)
            if agent_key is not None:
                conditions.append("contract.agent_key = %s")
                parameters.append(agent_key)
            where = " AND ".join(conditions)
            rows = connection.execute(
                f"""
                SELECT policy.permission_policy_id, policy.organization_id,
                       COALESCE(policy.workspace_id, contract.workspace_id) AS workspace_id,
                       policy.agent_version_id, policy.permission_key, policy.effect,
                       policy.resource_scope, policy.approval_required, policy.lifecycle_status,
                       policy.created_by_user_id, policy.approved_by_user_id, policy.created_at,
                       policy.capability_key, policy.tool_key, policy.access_mode,
                       policy.resource_type, policy.division_scope, policy.project_scope,
                       policy.classification, policy.conditions,
                       contract.agent_key, contract.name AS agent_name,
                       version.semantic_version
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
    def _agent_info(
        connection: psycopg.Connection[Any], agent_version_id: UUID
    ) -> tuple[str, str, str]:
        row = connection.execute(
            """
            SELECT contract.agent_key, contract.name, version.semantic_version
            FROM agents.contracts AS contract
            JOIN agents.versions AS version
              ON version.agent_contract_id = contract.agent_contract_id
            WHERE version.agent_version_id = %s
            """,
            (agent_version_id,),
        ).fetchone()
        if row is None:
            raise PermissionNotFoundError("Agent Version was not found")
        return str(row["agent_key"]), str(row["name"]), str(row["semantic_version"])

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

"""H2 Agent Registry and Model Gateway-backed draft builder.

The builder may ask the configured Model Gateway to draft plain-language
purpose and prompt text, but all security-relevant fields are supplied by the
human/API and validated by ALOS before persistence. Every create, update, and
retirement writes an append-only audit event. Drafts never activate an agent.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, Protocol
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alos.config import Settings
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGatewayError,
    ModelRequest,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.persistence.database import psycopg_url

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DataClassification = Literal["PUBLIC", "INTERNAL"]
_BUILDER_MAX_OUTPUT_TOKENS = 900
_DRAFT_LIFECYCLE = "DRAFT"


class AgentRegistryError(RuntimeError):
    """A safe domain failure that can be reported by the Registry API."""


class AgentNotFoundError(AgentRegistryError):
    """The requested Agent Contract does not exist within the organization."""


class AgentConflictError(AgentRegistryError):
    """The requested draft would violate immutable Registry rules."""


class AgentBuilderRequest(BaseModel):
    """Human-controlled Builder inputs; Gemini never chooses these controls."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=20, max_length=10_000)
    parent_agent_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    risk_level: RiskLevel = "LOW"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    tool_keys: list[str] = Field(default_factory=list)
    permission_keys: list[str] = Field(default_factory=list)
    approval_required: bool = True
    timeout_seconds: int = Field(default=120, ge=1, le=3_600)
    max_steps: int = Field(default=8, ge=1, le=100)
    data_classification: DataClassification = "INTERNAL"
    forbidden_actions: list[str] = Field(min_length=1)
    kpis: list[dict[str, Any]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_risk_controls(self) -> AgentBuilderRequest:
        if self.risk_level in {"HIGH", "CRITICAL"} and not self.approval_required:
            raise ValueError("high and critical draft agents require human approval")
        if self.parent_agent_key == self.agent_key:
            raise ValueError("an agent cannot be its own parent")
        return self


class GeneratedAgentFields(BaseModel):
    """The strictly limited text Gemini is permitted to draft for an agent."""

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=10_000)
    prompt_template: str = Field(min_length=1, max_length=20_000)
    evidence_requirements: list[str] = Field(min_length=1)

    @field_validator("evidence_requirements", mode="before")
    @classmethod
    def normalize_single_evidence_requirement(cls, value: object) -> object:
        """Accept one provider-written evidence statement without weakening controls."""
        if isinstance(value, str):
            return [value]
        return value


class AgentContract(BaseModel):
    """Runtime-neutral, versioned contract for every logical ALOS agent."""

    model_config = ConfigDict(extra="forbid")

    agent_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str = Field(min_length=1, max_length=200)
    workspace_id: UUID
    parent_agent_key: str | None = None
    purpose: str = Field(min_length=1, max_length=10_000)
    risk_level: RiskLevel
    owner_user_id: UUID
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    model_policy: dict[str, Any]
    tool_keys: list[str]
    permission_keys: list[str]
    evidence_requirements: list[str]
    forbidden_actions: list[str]
    kpis: list[dict[str, Any]]
    approval_required: bool
    timeout_seconds: int = Field(ge=1, le=3_600)
    max_steps: int = Field(default=8, ge=1, le=100)
    prompt_template: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def validate_human_controls(self) -> AgentContract:
        if self.risk_level in {"HIGH", "CRITICAL"} and not self.approval_required:
            raise ValueError("high and critical agents require human approval")
        if not self.forbidden_actions:
            raise ValueError("an Agent Contract must define forbidden actions")
        return self


class AgentVersionRecord(BaseModel):
    agent_version_id: UUID
    semantic_version: str
    lifecycle_status: str
    digest: str
    contract_snapshot: dict[str, Any]


class AgentRegistryRecord(BaseModel):
    agent_contract_id: UUID
    agent_key: str
    name: str
    workspace_id: UUID
    parent_agent_key: str | None
    agent_level: int
    risk_level: RiskLevel
    versions: list[AgentVersionRecord]


class AgentDraftResult(BaseModel):
    agent_contract_id: UUID
    agent_version_id: UUID
    agent_key: str
    semantic_version: str
    lifecycle_status: Literal["DRAFT", "RETIRED"]
    agent_level: int
    digest: str
    correlation_id: UUID


class LocalBootstrapRequest(BaseModel):
    """Local-only identity bootstrap so the Registry never bypasses RBAC."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(default="director@alos.local", min_length=3, max_length=320)
    display_name: str = Field(default="ALOS Director", min_length=1, max_length=200)
    workspace_key: str = Field(default="H2_REGISTRY", pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    workspace_name: str = Field(default="ALOS H2 Agent Registry", min_length=1, max_length=200)


class LocalBootstrapContext(BaseModel):
    organization_id: UUID
    user_id: UUID
    workspace_id: UUID


class AgentDraftGenerator(Protocol):
    def generate(self, request: AgentBuilderRequest) -> GeneratedAgentFields:
        """Return a safe, limited Gemini drafting result."""


class ModelGatewayAgentDraftGenerator:
    """Draft contract text through the configured shared Model Gateway only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: AgentBuilderRequest) -> GeneratedAgentFields:
        if self._settings.llm_provider not in {"gemini", "openai"}:
            raise AgentRegistryError("Genesis Builder requires a configured Model Gateway provider")
        delegate, close_gateway = create_model_gateway(self._settings)
        output_limit = min(_BUILDER_MAX_OUTPUT_TOKENS, self._settings.llm_max_output_tokens)
        gateway = GuardedModelGateway(
            delegate,
            self._settings,
            UsageBudget(request_limit=1, output_token_limit=output_limit),
        )
        try:
            response = gateway.generate(
                ModelRequest(
                    instructions=(
                        "You draft text for an internal ALOS Agent Contract. Return JSON only, "
                        "without markdown, with exactly purpose, prompt_template, and "
                        "evidence_requirements. Do not choose a model, tools, permissions, "
                        "risk level, owner, lifecycle, approval, or perform any action. "
                        "The agent must stay read-only and require cited evidence."
                    ),
                    input_text=json.dumps(
                        {
                            "agent_key": request.agent_key,
                            "name": request.name,
                            "objective": request.objective,
                            "risk_level": request.risk_level,
                            "forbidden_actions": request.forbidden_actions,
                            "kpis": request.kpis,
                        },
                        ensure_ascii=False,
                    ),
                    data_classification=request.data_classification,
                    max_output_tokens=output_limit,
                )
            )
        except ModelGatewayError as error:
            raise AgentRegistryError(f"Genesis draft request failed: {error.code}") from error
        finally:
            close_gateway()
        try:
            return GeneratedAgentFields.model_validate_json(_strip_code_fence(response.output_text))
        except ValueError as error:
            raise AgentRegistryError(
                "Gemini draft did not match the required contract text format"
            ) from error


class AgentDraftBuilder:
    def __init__(self, generator: AgentDraftGenerator) -> None:
        self._generator = generator

    def build(self, request: AgentBuilderRequest, owner_user_id: UUID) -> AgentContract:
        generated = self._generator.generate(request)
        return AgentContract(
            agent_key=request.agent_key,
            name=request.name,
            workspace_id=request.workspace_id,
            parent_agent_key=request.parent_agent_key,
            purpose=generated.purpose,
            risk_level=request.risk_level,
            owner_user_id=owner_user_id,
            input_schema=request.input_schema,
            output_schema=request.output_schema,
            model_policy=request.model_policy,
            tool_keys=request.tool_keys,
            permission_keys=request.permission_keys,
            evidence_requirements=generated.evidence_requirements,
            forbidden_actions=request.forbidden_actions,
            kpis=request.kpis,
            approval_required=request.approval_required,
            timeout_seconds=request.timeout_seconds,
            max_steps=request.max_steps,
            prompt_template=generated.prompt_template,
        )


class AgentRegistryRepository:
    """PostgreSQL persistence that preserves Agent Contract version history."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def bootstrap_local_context(
        self, request: LocalBootstrapRequest, correlation_id: UUID
    ) -> LocalBootstrapContext:
        with self._transaction() as connection:
            organization = connection.execute(
                "SELECT organization_id FROM identity.organizations WHERE code = 'ALOS'"
            ).fetchone()
            if organization is None:
                raise AgentRegistryError("ALOS organization seed is unavailable")
            organization_id = organization["organization_id"]
            division = connection.execute(
                """
                SELECT division_id FROM identity.divisions
                WHERE organization_id = %s AND code = 'IT'
                """,
                (organization_id,),
            ).fetchone()
            if division is None:
                raise AgentRegistryError("IT division seed is unavailable")
            user = connection.execute(
                """
                INSERT INTO identity.users (organization_id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (organization_id, email)
                DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING user_id
                """,
                (organization_id, request.email, request.display_name),
            ).fetchone()
            if user is None:
                raise AgentRegistryError("local registry user could not be created")
            workspace = connection.execute(
                """
                INSERT INTO workspace.workspaces (organization_id, division_id, workspace_key, name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (organization_id, workspace_key)
                DO UPDATE SET name = EXCLUDED.name
                RETURNING workspace_id
                """,
                (
                    organization_id,
                    division["division_id"],
                    request.workspace_key,
                    request.workspace_name,
                ),
            ).fetchone()
            if workspace is None:
                raise AgentRegistryError("local registry workspace could not be created")
            user_id = user["user_id"]
            workspace_id = workspace["workspace_id"]
            connection.execute(
                """
                INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
                VALUES (%s, %s, 'OWNER')
                ON CONFLICT (workspace_id, user_id) DO NOTHING
                """,
                (workspace_id, user_id),
            )
            connection.execute(
                """
                INSERT INTO identity.role_assignments (user_id, division_id, role_code)
                SELECT %s, %s, 'DIRECTOR'
                WHERE NOT EXISTS (
                    SELECT 1 FROM identity.role_assignments
                    WHERE user_id = %s AND role_code = 'DIRECTOR' AND revoked_at IS NULL
                )
                """,
                (user_id, division["division_id"], user_id),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=user_id,
                action="LOCAL_REGISTRY_CONTEXT_BOOTSTRAPPED",
                entity_type="WORKSPACE",
                entity_id=workspace_id,
                correlation_id=correlation_id,
                reason="Local H2 Registry bootstrap",
                metadata={"workspace_key": request.workspace_key},
            )
            return LocalBootstrapContext(
                organization_id=organization_id,
                user_id=user_id,
                workspace_id=workspace_id,
            )

    def create_draft(
        self,
        contract: AgentContract,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
    ) -> AgentDraftResult:
        with self._transaction() as connection:
            self._require_actor(connection, organization_id, actor_user_id)
            self._require_workspace_access(
                connection, organization_id, actor_user_id, contract.workspace_id
            )
            parent_id, level = self._resolve_parent(
                connection, organization_id, contract.parent_agent_key
            )
            snapshot = contract.model_dump(mode="json")
            digest = _digest(snapshot)
            try:
                contract_row = connection.execute(
                    """
                    INSERT INTO agents.contracts (
                        organization_id, workspace_id, agent_key, parent_agent_contract_id, name,
                        owner_user_id, risk_level, agent_level
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING agent_contract_id
                    """,
                    (
                        organization_id,
                        contract.workspace_id,
                        contract.agent_key,
                        parent_id,
                        contract.name,
                        contract.owner_user_id,
                        contract.risk_level,
                        level,
                    ),
                ).fetchone()
            except UniqueViolation as error:
                raise AgentConflictError("agent key already exists in this organization") from error
            if contract_row is None:
                raise AgentRegistryError("agent contract could not be created")
            version_row = self._insert_version(
                connection,
                agent_contract_id=contract_row["agent_contract_id"],
                semantic_version="0.1.0",
                lifecycle_status=_DRAFT_LIFECYCLE,
                snapshot=snapshot,
                digest=digest,
            )
            connection.execute(
                "INSERT INTO agents.registry (agent_contract_id) VALUES (%s)",
                (contract_row["agent_contract_id"],),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="AGENT_DRAFT_CREATED",
                entity_type="AGENT_CONTRACT",
                entity_id=contract_row["agent_contract_id"],
                correlation_id=correlation_id,
                reason=reason,
                metadata={"agent_key": contract.agent_key, "semantic_version": "0.1.0"},
            )
            return AgentDraftResult(
                agent_contract_id=contract_row["agent_contract_id"],
                agent_version_id=version_row["agent_version_id"],
                agent_key=contract.agent_key,
                semantic_version="0.1.0",
                lifecycle_status="DRAFT",
                agent_level=level,
                digest=digest,
                correlation_id=correlation_id,
            )

    def update_draft(
        self,
        contract: AgentContract,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
    ) -> AgentDraftResult:
        with self._transaction() as connection:
            self._require_actor(connection, organization_id, actor_user_id)
            self._require_workspace_access(
                connection, organization_id, actor_user_id, contract.workspace_id
            )
            existing = connection.execute(
                """
                SELECT agent_contract_id, workspace_id FROM agents.contracts
                WHERE organization_id = %s AND agent_key = %s
                FOR UPDATE
                """,
                (organization_id, contract.agent_key),
            ).fetchone()
            if existing is None:
                raise AgentNotFoundError("agent contract was not found")
            if existing["workspace_id"] != contract.workspace_id:
                raise AgentConflictError("an agent contract cannot be moved between workspaces")
            parent_id, level = self._resolve_parent(
                connection, organization_id, contract.parent_agent_key
            )
            snapshot = contract.model_dump(mode="json")
            digest = _digest(snapshot)
            connection.execute(
                """
                UPDATE agents.contracts
                SET parent_agent_contract_id = %s, name = %s, owner_user_id = %s,
                    risk_level = %s, agent_level = %s
                WHERE agent_contract_id = %s
                """,
                (
                    parent_id,
                    contract.name,
                    contract.owner_user_id,
                    contract.risk_level,
                    level,
                    existing["agent_contract_id"],
                ),
            )
            semantic_version = self._next_semantic_version(
                connection, existing["agent_contract_id"]
            )
            version_row = self._insert_version(
                connection,
                agent_contract_id=existing["agent_contract_id"],
                semantic_version=semantic_version,
                lifecycle_status=_DRAFT_LIFECYCLE,
                snapshot=snapshot,
                digest=digest,
            )
            connection.execute(
                "UPDATE agents.registry SET updated_at = now() WHERE agent_contract_id = %s",
                (existing["agent_contract_id"],),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="AGENT_DRAFT_UPDATED",
                entity_type="AGENT_CONTRACT",
                entity_id=existing["agent_contract_id"],
                correlation_id=correlation_id,
                reason=reason,
                metadata={"agent_key": contract.agent_key, "semantic_version": semantic_version},
            )
            return AgentDraftResult(
                agent_contract_id=existing["agent_contract_id"],
                agent_version_id=version_row["agent_version_id"],
                agent_key=contract.agent_key,
                semantic_version=semantic_version,
                lifecycle_status="DRAFT",
                agent_level=level,
                digest=digest,
                correlation_id=correlation_id,
            )

    def retire(
        self,
        agent_key: str,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
    ) -> AgentDraftResult:
        """Retire with a final immutable version; physical deletion is prohibited."""
        with self._transaction() as connection:
            self._require_actor(connection, organization_id, actor_user_id)
            agent = connection.execute(
                """
                SELECT agent_contract_id, agent_level FROM agents.contracts
                WHERE organization_id = %s AND agent_key = %s
                FOR UPDATE
                """,
                (organization_id, agent_key),
            ).fetchone()
            if agent is None:
                raise AgentNotFoundError("agent contract was not found")
            current = connection.execute(
                """
                SELECT contract_snapshot, digest FROM agents.versions
                WHERE agent_contract_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (agent["agent_contract_id"],),
            ).fetchone()
            if current is None:
                raise AgentRegistryError("agent contract does not have a version")
            semantic_version = self._next_semantic_version(connection, agent["agent_contract_id"])
            version_row = self._insert_version(
                connection,
                agent_contract_id=agent["agent_contract_id"],
                semantic_version=semantic_version,
                lifecycle_status="RETIRED",
                snapshot=current["contract_snapshot"],
                digest=current["digest"],
            )
            connection.execute(
                """
                UPDATE agents.registry
                SET active_version_id = NULL, released_version_id = NULL, updated_at = now()
                WHERE agent_contract_id = %s
                """,
                (agent["agent_contract_id"],),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="AGENT_RETIRED",
                entity_type="AGENT_CONTRACT",
                entity_id=agent["agent_contract_id"],
                correlation_id=correlation_id,
                reason=reason,
                metadata={"agent_key": agent_key, "semantic_version": semantic_version},
            )
            return AgentDraftResult(
                agent_contract_id=agent["agent_contract_id"],
                agent_version_id=version_row["agent_version_id"],
                agent_key=agent_key,
                semantic_version=semantic_version,
                lifecycle_status="RETIRED",
                agent_level=agent["agent_level"],
                digest=current["digest"],
                correlation_id=correlation_id,
            )

    def list_agents(self, organization_id: UUID) -> list[AgentRegistryRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT agent_key FROM agents.contracts
                WHERE organization_id = %s ORDER BY agent_key
                """,
                (organization_id,),
            ).fetchall()
            return [self._get_agent(connection, organization_id, row["agent_key"]) for row in rows]

    def get_agent(self, organization_id: UUID, agent_key: str) -> AgentRegistryRecord:
        with self._connection() as connection:
            return self._get_agent(connection, organization_id, agent_key)

    def _get_agent(
        self, connection: psycopg.Connection[Any], organization_id: UUID, agent_key: str
    ) -> AgentRegistryRecord:
        agent = connection.execute(
            """
            SELECT child.agent_contract_id, child.agent_key, child.name, child.workspace_id,
                   child.agent_level,
                   child.risk_level, parent.agent_key AS parent_agent_key
            FROM agents.contracts AS child
            LEFT JOIN agents.contracts AS parent
              ON parent.agent_contract_id = child.parent_agent_contract_id
            WHERE child.organization_id = %s AND child.agent_key = %s
            """,
            (organization_id, agent_key),
        ).fetchone()
        if agent is None:
            raise AgentNotFoundError("agent contract was not found")
        versions = connection.execute(
            """
            SELECT agent_version_id, semantic_version, lifecycle_status, digest, contract_snapshot
            FROM agents.versions
            WHERE agent_contract_id = %s
            ORDER BY created_at DESC, agent_version_id DESC
            """,
            (agent["agent_contract_id"],),
        ).fetchall()
        return AgentRegistryRecord(
            agent_contract_id=agent["agent_contract_id"],
            agent_key=agent["agent_key"],
            name=agent["name"],
            workspace_id=agent["workspace_id"],
            parent_agent_key=agent["parent_agent_key"],
            agent_level=agent["agent_level"],
            risk_level=agent["risk_level"],
            versions=[AgentVersionRecord(**version) for version in versions],
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

    @staticmethod
    def _require_actor(
        connection: psycopg.Connection[Any], organization_id: UUID, actor_user_id: UUID
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM identity.users WHERE organization_id = %s AND user_id = %s",
            (organization_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise AgentRegistryError("actor does not belong to the organization")

    @staticmethod
    def _require_workspace_access(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        row = connection.execute(
            """
            SELECT 1
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workspace.workspace_id
            WHERE workspace.workspace_id = %s
              AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
              AND membership.user_id = %s
            """,
            (workspace_id, organization_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise AgentRegistryError("actor does not have active workspace membership")

    @staticmethod
    def _resolve_parent(
        connection: psycopg.Connection[Any], organization_id: UUID, parent_agent_key: str | None
    ) -> tuple[UUID | None, int]:
        if parent_agent_key is None:
            return None, 0
        parent = connection.execute(
            """
            SELECT agent_contract_id, agent_level FROM agents.contracts
            WHERE organization_id = %s AND agent_key = %s
            """,
            (organization_id, parent_agent_key),
        ).fetchone()
        if parent is None:
            raise AgentConflictError("parent agent contract was not found")
        level = parent["agent_level"] + 1
        if level > 2:
            raise AgentConflictError("agent hierarchy cannot exceed level 2")
        return parent["agent_contract_id"], level

    @staticmethod
    def _next_semantic_version(connection: psycopg.Connection[Any], agent_contract_id: UUID) -> str:
        count_row = connection.execute(
            "SELECT count(*) FROM agents.versions WHERE agent_contract_id = %s",
            (agent_contract_id,),
        ).fetchone()
        if count_row is None:
            raise AgentRegistryError("agent version count could not be read")
        count = count_row["count"]
        return f"0.{count + 1}.0"

    @staticmethod
    def _insert_version(
        connection: psycopg.Connection[Any],
        *,
        agent_contract_id: UUID,
        semantic_version: str,
        lifecycle_status: str,
        snapshot: dict[str, Any],
        digest: str,
    ) -> dict[str, UUID]:
        version = connection.execute(
            """
            INSERT INTO agents.versions (
                agent_contract_id, semantic_version, lifecycle_status, contract_snapshot, digest
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING agent_version_id
            """,
            (agent_contract_id, semantic_version, lifecycle_status, Jsonb(snapshot), digest),
        ).fetchone()
        if version is None:
            raise AgentRegistryError("agent version could not be created")
        return {"agent_version_id": version["agent_version_id"]}

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
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


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return stripped

"""Metadata-only router for selecting a small set of ACTIVE logical agents."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from alos.authorization import effective_data_scope
from alos.identity import DataScope
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class AgentCandidate(BaseModel):
    agent_key: str
    name: str
    semantic_version: str
    purpose: str
    risk_level: str
    capability_keys: list[str] = Field(default_factory=list)


class ActiveAgentSummary(BaseModel):
    """Safe discovery metadata; prompts, provider configuration, and credentials stay private."""

    agent_key: str
    name: str
    semantic_version: str
    purpose: str
    risk_level: str
    division_scope: list[str] = Field(default_factory=list)
    capability_keys: list[str] = Field(default_factory=list)


class AgentRouter:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def candidates(
        self,
        actor: ActorContext,
        workspace_id: UUID,
        query: str,
        *,
        capability_keys: list[str],
        limit: int = 5,
    ) -> list[AgentCandidate]:
        if workspace_id not in actor.workspace_ids:
            return []
        term = f"%{query.strip()}%"
        division_codes = [item.value for item in actor.division_codes]
        company_scope = effective_data_scope(actor) == DataScope.COMPANY
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT contract.agent_key, contract.name, version.semantic_version,
                       version.contract_snapshot ->> 'purpose' AS purpose,
                       contract.risk_level,
                       coalesce(
                           version.contract_snapshot -> 'model_policy' -> 'capability_keys',
                           '[]'::jsonb
                       ) AS capability_keys
                FROM agents.registry AS registry
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = registry.agent_contract_id
                JOIN agents.versions AS version
                  ON version.agent_version_id = registry.active_version_id
                WHERE contract.organization_id = %s AND contract.workspace_id = %s
                  AND version.lifecycle_status = 'ACTIVE'
                  AND (
                      contract.name ILIKE %s OR contract.agent_key ILIKE %s
                      OR version.contract_snapshot ->> 'purpose' ILIKE %s
                      OR coalesce(
                          version.contract_snapshot -> 'model_policy' -> 'capability_keys',
                          '[]'::jsonb
                      ) ?| %s
                  )
                  AND (
                      %s OR jsonb_array_length(coalesce(
                          version.contract_snapshot -> 'model_policy' -> 'division_scope',
                          '[]'::jsonb
                      )) = 0 OR coalesce(
                          version.contract_snapshot -> 'model_policy' -> 'division_scope',
                          '[]'::jsonb
                      ) ?| %s
                  )
                ORDER BY contract.risk_level, contract.name
                LIMIT %s
                """,
                (
                    actor.organization_id,
                    workspace_id,
                    term,
                    term,
                    term,
                    capability_keys,
                    company_scope,
                    division_codes,
                    min(limit, 10),
                ),
            ).fetchall()
        return [AgentCandidate(**row) for row in rows]

    def active_agents(
        self,
        actor: ActorContext,
        workspace_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ActiveAgentSummary]:
        if workspace_id not in actor.workspace_ids:
            return []
        division_codes = [item.value for item in actor.division_codes]
        company_scope = effective_data_scope(actor) == DataScope.COMPANY
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT contract.agent_key, contract.name, version.semantic_version,
                       version.contract_snapshot ->> 'purpose' AS purpose,
                       contract.risk_level,
                       coalesce(
                           version.contract_snapshot -> 'model_policy' -> 'division_scope',
                           '[]'::jsonb
                       ) AS division_scope,
                       coalesce(
                           version.contract_snapshot -> 'model_policy' -> 'capability_keys',
                           '[]'::jsonb
                       ) AS capability_keys
                FROM agents.registry AS registry
                JOIN agents.contracts AS contract
                  ON contract.agent_contract_id = registry.agent_contract_id
                JOIN agents.versions AS version
                  ON version.agent_version_id = registry.active_version_id
                WHERE contract.organization_id = %s AND contract.workspace_id = %s
                  AND version.lifecycle_status = 'ACTIVE'
                  AND (
                      %s OR jsonb_array_length(coalesce(
                          version.contract_snapshot -> 'model_policy' -> 'division_scope',
                          '[]'::jsonb
                      )) = 0 OR coalesce(
                          version.contract_snapshot -> 'model_policy' -> 'division_scope',
                          '[]'::jsonb
                      ) ?| %s
                  )
                ORDER BY contract.name, contract.agent_key
                LIMIT %s
                """,
                (
                    actor.organization_id,
                    workspace_id,
                    company_scope,
                    division_codes,
                    min(max(limit, 1), 200),
                ),
            ).fetchall()
        return [ActiveAgentSummary(**row) for row in rows]

    def active_candidate(
        self, actor: ActorContext, workspace_id: UUID, agent_key: str
    ) -> AgentCandidate | None:
        agents = self.candidates(
            actor,
            workspace_id,
            agent_key,
            capability_keys=[],
            limit=10,
        )
        return next((item for item in agents if item.agent_key == agent_key), None)

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

import alos.main as main
from alos.agents.registry import (
    AgentBuilderRequest,
    AgentDraftBuilder,
    AgentRegistryRepository,
    GeneratedAgentFields,
)
from alos.config import get_settings
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


class StubDraftGenerator:
    def generate(self, request: AgentBuilderRequest) -> GeneratedAgentFields:
        return GeneratedAgentFields(
            purpose=f"Read-only research for: {request.objective}",
            prompt_template=(
                "Use registered sources only. Return citations. Do not execute actions."
            ),
            evidence_requirements=["registered source", "citation"],
        )


def _payload(workspace_id: str, agent_key: str, **changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "workspace_id": workspace_id,
        "agent_key": agent_key,
        "name": agent_key.replace("_", " ").title(),
        "objective": "Create a read-only operational brief using registered internal sources.",
        "risk_level": "LOW",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "model_policy": {"provider": "gemini", "mode": "local_test"},
        "tool_keys": [],
        "permission_keys": ["sources.read"],
        "approval_required": True,
        "timeout_seconds": 120,
        "data_classification": "INTERNAL",
        "forbidden_actions": ["No external write or production change."],
        "kpis": [{"name": "citation_coverage", "target": 1}],
    }
    payload.update(changes)
    return payload


def test_registry_builder_api_versions_audits_and_rejects_circular_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h2_registry_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        repository = AgentRegistryRepository(temporary_url)
        builder = AgentDraftBuilder(StubDraftGenerator())
        monkeypatch.setattr(main, "get_agent_registry_repository", lambda: repository)
        monkeypatch.setattr(main, "get_agent_draft_builder", lambda: builder)

        client = TestClient(main.app)
        bootstrap = client.post("/api/v1/local/bootstrap", json={})
        assert bootstrap.status_code == 200
        context = bootstrap.json()
        headers = {"Authorization": f"Bearer {context['access_token']}"}
        workspace_id = context["workspace_id"]

        root = client.post(
            "/api/v1/agents/drafts",
            json=_payload(workspace_id, "PROPERTY_RESEARCH"),
            headers=headers,
        )
        assert root.status_code == 200
        assert root.json()["semantic_version"] == "0.1.0"
        assert root.json()["agent_level"] == 0

        child = client.post(
            "/api/v1/agents/drafts",
            json=_payload(
                workspace_id,
                "PROPERTY_LEAD_SCAN",
                parent_agent_key="PROPERTY_RESEARCH",
            ),
            headers=headers,
        )
        assert child.status_code == 200
        assert child.json()["agent_level"] == 1

        updated = client.put(
            "/api/v1/agents/PROPERTY_RESEARCH/draft",
            json=_payload(
                workspace_id,
                "PROPERTY_RESEARCH",
                name="Property Research Updated",
            ),
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["semantic_version"] == "0.2.0"

        read = client.get("/api/v1/agents/PROPERTY_RESEARCH", headers=headers)
        assert read.status_code == 200
        assert read.json()["workspace_id"] == workspace_id
        assert {version["semantic_version"] for version in read.json()["versions"]} == {
            "0.1.0",
            "0.2.0",
        }

        retired = client.post("/api/v1/agents/PROPERTY_LEAD_SCAN/retire", headers=headers)
        assert retired.status_code == 200
        assert retired.json()["lifecycle_status"] == "RETIRED"

        with psycopg.connect(temporary_url) as connection:
            rows = connection.execute(
                """
                SELECT action FROM audit.events
                WHERE action IN ('AGENT_DRAFT_CREATED', 'AGENT_DRAFT_UPDATED', 'AGENT_RETIRED')
                ORDER BY action
                """
            ).fetchall()
            assert [row[0] for row in rows] == [
                "AGENT_DRAFT_CREATED",
                "AGENT_DRAFT_CREATED",
                "AGENT_DRAFT_UPDATED",
                "AGENT_RETIRED",
            ]
            identifiers = connection.execute(
                """
                SELECT agent_key, agent_contract_id FROM agents.contracts
                WHERE agent_key IN ('PROPERTY_RESEARCH', 'PROPERTY_LEAD_SCAN')
                """
            ).fetchall()
            agent_ids = {
                agent_key: UUID(str(agent_contract_id))
                for agent_key, agent_contract_id in identifiers
            }
            with pytest.raises(psycopg.errors.RaiseException, match="circular agent parent"):
                connection.execute(
                    """
                    UPDATE agents.contracts
                    SET parent_agent_contract_id = %s, agent_level = 2
                    WHERE agent_contract_id = %s
                    """,
                    (agent_ids["PROPERTY_LEAD_SCAN"], agent_ids["PROPERTY_RESEARCH"]),
                )
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))

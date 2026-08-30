import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.main import app
from alos.persistence.migrations import psycopg_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_tia_and_marketing_agent_execute_via_same_audited_runtime() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    finance_headers = _headers(client, organization_id, "FINANCE", "FINANCE")
    sales_headers = _headers(client, organization_id, "SALES", "SALES_MARKETING")
    run_ids: list[str] = []
    try:
        invoice = client.post(
            "/api/v1/agent-runtime/execute",
            headers={**finance_headers, "Idempotency-Key": f"tia-{uuid4().hex}"},
            json={
                "agent_id": "TIA",
                "capability": "validate_invoice_rules",
                "input_references": ["invoice:synthetic-001"],
                "requested_tools": ["deterministic.calculator"],
                "input_payload": {"invoice_number": "SYNTHETIC-001"},
                "data_classification": "INTERNAL",
            },
        )
        assert invoice.status_code == 201, invoice.text
        run_ids.append(invoice.json()["run_id"])
        assert invoice.json()["handler_id"] == "finance.tax-rules.v1"
        assert invoice.json()["production_effect"] is False

        marketing = client.post(
            "/api/v1/agent-runtime/execute",
            headers={**sales_headers, "Idempotency-Key": f"mkt-{uuid4().hex}"},
            json={
                "agent_id": "MCA_MKT",
                "capability": "draft_marketing_content",
                "input_references": ["content-brief:synthetic-001"],
                "requested_tools": ["ai.language.generate"],
                "input_payload": {"brief": "Konten sintetis untuk pengujian"},
                "data_classification": "INTERNAL",
            },
        )
        assert marketing.status_code == 201, marketing.text
        run_ids.append(marketing.json()["run_id"])
        assert marketing.json()["handler_id"] == "ai.structured.v1"
        assert marketing.json()["status"] == "NEEDS_REVIEW"
        assert marketing.json()["verification_status"] == "UNVERIFIED"
        assert marketing.json()["warnings"]

        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                SELECT organization_id, workflow_run_id, handler_id, provider_metadata,
                       capability_version, capability_contract_digest
                FROM agents.agent_runs WHERE agent_run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            ).fetchall()
        assert len(rows) == 2
        assert all(row[0] == organization_id and row[1] is None for row in rows)
        assert any(row[3].get("llm_status") == "DISABLED" for row in rows)
        assert all(row[4] == "1.0.0" and len(row[5]) == 64 for row in rows)
    finally:
        with psycopg.connect(database_url) as connection:
            if run_ids:
                connection.execute(
                    "DELETE FROM audit.entries WHERE entity_id = ANY(%s::text[])", (run_ids,)
                )
                connection.execute(
                    "DELETE FROM agents.agent_runs WHERE agent_run_id = ANY(%s::uuid[])",
                    (run_ids,),
                )


def _headers(
    client: TestClient,
    organization_id: object,
    role: str,
    division: str,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(organization_id),
            "roles": [role],
            "division_codes": [division],
            "project_ids": [],
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

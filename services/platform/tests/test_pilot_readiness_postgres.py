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


def test_pilot_readiness_uses_registry_and_returns_only_aggregate_facts() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]

    client = TestClient(app)
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(organization_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
        },
    )
    assert token_response.status_code == 200
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
    project_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"READY-{uuid4().hex[:8].upper()}",
            "name": "Controlled Pilot Readiness Test",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]

    try:
        forbidden_activation = client.patch(
            f"/api/v1/projects/{project_id}/status",
            headers=headers,
            json={"status": "ACTIVE", "reason": "Aktivasi oleh IT harus ditolak."},
        )
        assert forbidden_activation.status_code == 403
        director_token = client.post(
            "/api/v1/auth/local-token",
            json={
                "user_id": str(uuid4()),
                "organization_id": str(organization_id),
                "roles": ["DIRECTOR"],
            },
        ).json()["access_token"]
        invalid_transition = client.patch(
            f"/api/v1/projects/{project_id}/status",
            headers={"Authorization": f"Bearer {director_token}"},
            json={
                "status": "CLOSED",
                "reason": "DRAFT tidak boleh langsung ditutup.",
            },
        )
        assert invalid_transition.status_code == 409
        activation = client.patch(
            f"/api/v1/projects/{project_id}/status",
            headers={"Authorization": f"Bearer {director_token}"},
            json={
                "status": "ACTIVE",
                "reason": "Mengaktifkan proyek untuk readiness test sintetis.",
            },
        )
        assert activation.status_code == 200, activation.text
        assert activation.json()["status"] == "ACTIVE"
        with psycopg.connect(database_url) as connection:
            audit_action = connection.execute(
                """
                SELECT action FROM audit.entries
                WHERE entity_id = %s AND action = 'project.status_changed'
                ORDER BY occurred_at DESC LIMIT 1
                """,
                (str(project_id),),
            ).fetchone()
            assert audit_action == ("project.status_changed",)

        response = client.get(
            "/api/v1/system/pilot-readiness",
            headers=headers,
            params={"project_id": project_id},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        checks = {item["check_id"]: item for item in payload["checks"]}
        assert checks["PILOT-PROJECT-ACTIVE"]["status"] == "PASS"
        assert checks["PILOT-AGENT-REGISTRY"]["actual_count"] == 18
        assert checks["PILOT-WORKFLOW-REGISTRY"]["actual_count"] == 6
        assert payload["overall_status"] in {"ATTENTION", "BLOCKED"}
        serialized = response.text.lower()
        assert "email" not in serialized
        assert "display_name" not in serialized
        assert "user_id" not in serialized
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM audit.entries WHERE entity_id = %s", (str(project_id),)
            )
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (project_id,)
            )

import os
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from alos.config import Settings, get_settings
from alos.entrypoints.api import validate_released_principal
from alos.main import app
from alos.persistence.migrations import psycopg_url
from alos.security import AuthenticationError, Principal, Role

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_operational_queries_and_identity_access_are_scoped_and_audited() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_id = uuid4()
    admin_headers = _headers(client, organization_id, admin_id, ["IT_ADMIN"], ["IT"])
    created: dict[str, Any] = {"assignment_ids": []}

    try:
        user_response = client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": f"query-sales-{uuid4().hex[:8]}@example.test",
                "display_name": "Sales Query Sintetis",
                "division_code": "SALES_MARKETING",
                "role": "SALES",
            },
        )
        assert user_response.status_code == 201, user_response.text
        user_id = user_response.json()["user_id"]
        created["user_id"] = user_id

        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"QUERY-{uuid4().hex[:8].upper()}", "name": "Query Pilot"},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id

        project_assignment = client.post(
            f"/api/v1/users/{user_id}/project-assignments",
            headers=admin_headers,
            json={
                "project_id": project_id,
                "reason": "Akses untuk pengujian query operasional",
            },
        )
        assert project_assignment.status_code == 201, project_assignment.text
        project_assignment_id = project_assignment.json()["assignment_id"]
        created["assignment_ids"].append(project_assignment_id)
        duplicate_project_assignment = client.post(
            f"/api/v1/users/{user_id}/project-assignments",
            headers=admin_headers,
            json={
                "project_id": project_id,
                "reason": "Duplikasi akses untuk pengujian konflik",
            },
        )
        assert duplicate_project_assignment.status_code == 409

        head_assignment = client.post(
            f"/api/v1/users/{user_id}/role-assignments",
            headers=admin_headers,
            json={
                "role": "DIVISION_HEAD",
                "division_code": "SALES_MARKETING",
                "reason": "Penugasan tambahan untuk pengujian akses",
            },
        )
        assert head_assignment.status_code == 201, head_assignment.text
        role_assignment_id = head_assignment.json()["assignment_id"]
        created["assignment_ids"].append(role_assignment_id)
        duplicate_role_assignment = client.post(
            f"/api/v1/users/{user_id}/role-assignments",
            headers=admin_headers,
            json={
                "role": "DIVISION_HEAD",
                "division_code": "SALES_MARKETING",
                "reason": "Duplikasi role untuk pengujian konflik",
            },
        )
        assert duplicate_role_assignment.status_code == 409

        directory = client.get(
            "/api/v1/users",
            headers=admin_headers,
            params={"search": "Sales Query", "role": "SALES"},
        )
        assert directory.status_code == 200, directory.text
        assert directory.json()["total"] == 1
        assert directory.json()["items"][0]["projects"][0]["project_id"] == project_id

        sales_headers = _headers(
            client,
            organization_id,
            user_id,
            ["SALES"],
            ["SALES_MARKETING"],
            [project_id],
        )
        lead_response = client.post(
            "/api/v1/leads",
            headers={**sales_headers, "Idempotency-Key": f"query-{uuid4().hex}"},
            json={
                "project_id": project_id,
                "full_name": "Lead Query Sintetis",
                "phone": "081234567890",
                "source": "integration-test",
                "consent_recorded": True,
            },
        )
        assert lead_response.status_code == 201, lead_response.text
        lead = lead_response.json()
        created["lead"] = lead

        assignment_response = client.post(
            f"/api/v1/workflow-runs/{lead['workflow_run_id']}/sales-assignment",
            headers={**sales_headers, "Idempotency-Key": f"assign-{uuid4().hex}"},
            json={"sales_pic_user_id": user_id},
        )
        assert assignment_response.status_code == 200, assignment_response.text

        interaction_response = client.post(
            f"/api/v1/workflow-runs/{lead['workflow_run_id']}/interactions",
            headers={**sales_headers, "Idempotency-Key": f"interact-{uuid4().hex}"},
            json={
                "channel": "phone",
                "outcome": "qualified",
                "notes": "Lead memenuhi kriteria dasar sintetis",
            },
        )
        assert interaction_response.status_code == 200, interaction_response.text

        leads = client.get(
            "/api/v1/leads",
            headers=sales_headers,
            params={"project_id": project_id, "search": "Lead Query", "sort_by": "full_name"},
        )
        assert leads.status_code == 200, leads.text
        assert leads.json()["total"] == 1
        assert leads.json()["items"][0]["lead_id"] == lead["lead_id"]

        lead_detail = client.get(f"/api/v1/leads/{lead['lead_id']}", headers=sales_headers)
        assert lead_detail.status_code == 200, lead_detail.text
        assert lead_detail.json()["status"] == "QUALIFIED"

        interactions = client.get(
            f"/api/v1/leads/{lead['lead_id']}/interactions", headers=sales_headers
        )
        assert interactions.status_code == 200, interactions.text
        assert interactions.json()["total"] == 1

        workflow = client.get(
            f"/api/v1/workflow-runs/{lead['workflow_run_id']}", headers=sales_headers
        )
        assert workflow.status_code == 200, workflow.text
        transitions = client.get(
            f"/api/v1/workflow-runs/{lead['workflow_run_id']}/transitions",
            headers=sales_headers,
        )
        assert transitions.status_code == 200, transitions.text
        assert transitions.json()["total"] == 3

        agents = client.get(
            "/api/v1/agent-runs", headers=sales_headers, params={"project_id": project_id}
        )
        assert agents.status_code == 200, agents.text
        assert agents.json()["total"] == 2

        foreign_scope_headers = _headers(
            client,
            organization_id,
            user_id,
            ["SALES"],
            ["SALES_MARKETING"],
            [uuid4()],
        )
        hidden = client.get("/api/v1/leads", headers=foreign_scope_headers)
        assert hidden.status_code == 200
        assert hidden.json()["total"] == 0

        finance_headers = _headers(
            client,
            organization_id,
            uuid4(),
            ["FINANCE"],
            ["FINANCE"],
            [project_id],
        )
        forbidden = client.get("/api/v1/leads", headers=finance_headers)
        assert forbidden.status_code == 403

        audit = client.get(
            "/api/v1/audit-entries",
            headers=admin_headers,
            params={"search": "identity.project_assigned"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] >= 1
        assert audit.json()["items"][0]["reason"] == ("Akses untuk pengujian query operasional")

        released_settings = Settings(
            environment="staging",
            database_url=get_settings().database_url,
            auth_signing_secret="staging-IAM-validation-secret-9X7q2L",
            oidc_provider="disabled",
        )
        released_principal = Principal(
            user_id=user_id,
            organization_id=organization_id,
            roles=frozenset({Role.SALES}),
            division_codes=frozenset({"SALES_MARKETING"}),
            project_ids=frozenset({project_id}),
        )
        validate_released_principal(released_principal, released_settings)

        role_revoke = client.post(
            f"/api/v1/users/{user_id}/role-assignments/{role_assignment_id}/revoke",
            headers=admin_headers,
            json={"reason": "Penugasan tambahan selesai diuji"},
        )
        assert role_revoke.status_code == 204, role_revoke.text

        project_revoke = client.post(
            f"/api/v1/users/{user_id}/project-assignments/{project_assignment_id}/revoke",
            headers=admin_headers,
            json={"reason": "Akses proyek selesai diuji"},
        )
        assert project_revoke.status_code == 204, project_revoke.text
        with pytest.raises(AuthenticationError, match="proyek"):
            validate_released_principal(released_principal, released_settings)

        suspended = client.patch(
            f"/api/v1/users/{user_id}/status",
            headers=admin_headers,
            json={"status": "SUSPENDED", "reason": "Akun sintetis selesai diuji"},
        )
        assert suspended.status_code == 200, suspended.text
        assert suspended.json()["status"] == "SUSPENDED"
    finally:
        _cleanup(database_url, created, admin_id)


def _headers(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
    project_ids: list[object] | None = None,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": roles,
            "division_codes": divisions,
            "project_ids": [str(item) for item in project_ids or []],
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cleanup(database_url: str, created: dict[str, Any], admin_id: object) -> None:
    with psycopg.connect(database_url) as connection:
        lead = created.get("lead")
        if lead:
            workflow_run_id = lead["workflow_run_id"]
            for table in (
                "sales.interactions",
                "sales.follow_up_tasks",
                "workflow.transition_events",
                "agents.agent_runs",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE workflow_run_id = %s",  # noqa: S608
                    (workflow_run_id,),
                )
            connection.execute(
                "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s",
                (workflow_run_id,),
            )
            connection.execute("DELETE FROM sales.leads WHERE lead_id = %s", (lead["lead_id"],))
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s",
                (lead["work_item_id"],),
            )
        user_id = created.get("user_id")
        if user_id:
            connection.execute(
                "DELETE FROM identity.project_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
        entity_ids = [
            str(value)
            for value in (
                created.get("project_id"),
                created.get("user_id"),
                *(created.get("assignment_ids") or []),
                lead["lead_id"] if lead else None,
            )
            if value
        ]
        if entity_ids:
            connection.execute(
                "DELETE FROM audit.entries WHERE entity_id = ANY(%s) OR actor_id = %s",
                (entity_ids, str(admin_id)),
            )
        if created.get("project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
            )
        if user_id:
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))

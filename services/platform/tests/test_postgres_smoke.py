import hashlib
import os
from typing import Any
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


def test_sales_workflow_is_persisted_from_lead_to_reservation() -> None:
    settings = get_settings()
    database_url = psycopg_url(settings.database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]

    client = TestClient(app)
    admin_token = _local_token(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_code = f"SYN-{uuid4().hex[:8].upper()}"
    project_id: str | None = None
    sales_user_id: str | None = None
    result: dict[str, Any] | None = None
    document: dict[str, Any] | None = None

    try:
        user_response = client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": f"sales-{uuid4().hex[:8]}@example.test",
                "display_name": "Sales Smoke Test",
                "division_code": "SALES_MARKETING",
                "role": "SALES",
            },
        )
        assert user_response.status_code == 201
        sales_user_id = user_response.json()["user_id"]

        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": project_code, "name": "Project Smoke Test Sintetis"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        sales_token = _local_token(
            client,
            organization_id,
            sales_user_id,
            ["SALES"],
            ["SALES_MARKETING"],
            [project_id],
        )
        sales_headers = {"Authorization": f"Bearer {sales_token}"}

        lead_response = client.post(
            "/api/v1/leads",
            headers={**sales_headers, "Idempotency-Key": f"smoke-{uuid4().hex}"},
            json={
                "project_id": project_id,
                "full_name": "Lead Smoke Test",
                "phone": "081234567890",
                "source": "automated-smoke-test",
                "consent_recorded": True,
            },
        )
        assert lead_response.status_code == 201
        result = lead_response.json()
        assert result["current_step"] == "sales-assignment"

        duplicate_response = client.post(
            "/api/v1/leads",
            headers={**sales_headers, "Idempotency-Key": f"duplicate-{uuid4().hex}"},
            json={
                "project_id": project_id,
                "full_name": "Lead Duplikat",
                "phone": "0812-3456-7890",
                "source": "manual-duplicate-test",
                "consent_recorded": True,
            },
        )
        assert duplicate_response.status_code == 422
        assert "sudah terdaftar" in duplicate_response.json()["detail"]

        assignment_response = client.post(
            f"/api/v1/workflow-runs/{result['workflow_run_id']}/sales-assignment",
            headers={**sales_headers, "Idempotency-Key": f"assign-{uuid4().hex}"},
            json={"sales_pic_user_id": sales_user_id},
        )
        assert assignment_response.status_code == 200
        assert assignment_response.json()["current_step"] == "interaction-review"

        follow_up_response = client.post(
            f"/api/v1/workflow-runs/{result['workflow_run_id']}/interactions",
            headers={**sales_headers, "Idempotency-Key": f"follow-{uuid4().hex}"},
            json={
                "outcome": "follow_up",
                "channel": "phone",
                "notes": "Lead meminta dihubungi kembali setelah berdiskusi dengan keluarga.",
            },
        )
        assert follow_up_response.status_code == 200
        assert follow_up_response.json()["current_step"] == "interaction-review"
        assert follow_up_response.json()["terminal"] is False

        content = f"synthetic-reservation-{uuid4()}".encode()
        document_response = client.post(
            "/api/v1/documents",
            headers=sales_headers,
            json={
                "project_id": project_id,
                "logical_name": "Form Reservasi Sintetis",
                "classification": "INTERNAL",
                "object_key": f"synthetic/reservation/{uuid4()}.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "media_type": "application/pdf",
                "size_bytes": len(content),
            },
        )
        assert document_response.status_code == 201
        document = document_response.json()

        reservation_reference = f"RSV-{uuid4().hex[:12].upper()}"
        reservation_response = client.post(
            f"/api/v1/workflow-runs/{result['workflow_run_id']}/interactions",
            headers={**sales_headers, "Idempotency-Key": f"reserve-{uuid4().hex}"},
            json={
                "outcome": "reserved",
                "channel": "site-visit",
                "notes": "Sales Human mencatat reservasi setelah konfirmasi pelanggan.",
                "evidence_reference": "synthetic-evidence:reservation-form",
                "evidence_document_version_id": document["document_version_id"],
                "reservation_reference": reservation_reference,
            },
        )
        assert reservation_response.status_code == 200
        assert reservation_response.json()["current_step"] == "pipeline-result"
        assert reservation_response.json()["terminal"] is True
        assert reservation_response.json()["work_item_status"] == "COMPLETED"

        queue_response = client.get(
            "/api/v1/work-items",
            headers=sales_headers,
            params={"project_id": project_id},
        )
        assert queue_response.status_code == 200
        assert queue_response.json()[0]["owner_user_id"] == sales_user_id
        assert queue_response.json()[0]["status"] == "COMPLETED"

        with psycopg.connect(database_url) as connection:
            workflow_run_id = result["workflow_run_id"]
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM agents.agent_runs WHERE workflow_run_id = %s",
                    workflow_run_id,
                )
                == 3
            )
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM workflow.transition_events WHERE workflow_run_id = %s",
                    workflow_run_id,
                )
                == 5
            )
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM sales.follow_up_tasks WHERE workflow_run_id = %s",
                    workflow_run_id,
                )
                == 2
            )
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM sales.reservations WHERE workflow_run_id = %s",
                    workflow_run_id,
                )
                == 1
            )
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM platform.evidence WHERE work_item_id = %s",
                    result["work_item_id"],
                )
                == 1
            )
    finally:
        _cleanup(database_url, project_id, sales_user_id, result, document)


def _local_token(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
    project_ids: list[object] | None = None,
) -> str:
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
    assert response.status_code == 200
    return response.json()["access_token"]


def _count(connection: Any, query: str, value: object) -> int:
    return int(connection.execute(query, (value,)).fetchone()[0])


def _cleanup(
    database_url: str,
    project_id: str | None,
    sales_user_id: str | None,
    result: dict[str, Any] | None,
    document: dict[str, Any] | None,
) -> None:
    with psycopg.connect(database_url) as connection:
        entity_ids = [item for item in [project_id, sales_user_id] if item]
        if result is not None:
            entity_ids.append(result["lead_id"])
            workflow_run_id = result["workflow_run_id"]
            for table in (
                "sales.reservations",
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
            connection.execute("DELETE FROM sales.leads WHERE lead_id = %s", (result["lead_id"],))
            connection.execute(
                "DELETE FROM platform.evidence WHERE work_item_id = %s",
                (result["work_item_id"],),
            )
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s",
                (result["work_item_id"],),
            )
        if document is not None:
            entity_ids.extend([document["document_id"], document["document_version_id"]])
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s",
                (document["document_id"],),
            )
        if entity_ids:
            connection.execute("DELETE FROM audit.entries WHERE entity_id = ANY(%s)", (entity_ids,))
        if project_id:
            connection.execute("DELETE FROM platform.projects WHERE project_id = %s", (project_id,))
        if sales_user_id:
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s",
                (sales_user_id,),
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (sales_user_id,))

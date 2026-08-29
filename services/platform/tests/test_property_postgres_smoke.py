import hashlib
import os
from datetime import date
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


def test_site_evidence_updates_kpi_or_opens_capa() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_token = _token(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created: dict[str, Any] = {"documents": [], "cases": []}

    try:
        submitter = _create_property_user(client, admin_headers, "submitter")
        reviewer = _create_property_user(client, admin_headers, "reviewer")
        created["user_ids"] = [submitter, reviewer]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"PROP-{uuid4().hex[:8].upper()}", "name": "Property Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        submitter_token = _token(
            client, organization_id, submitter, ["PROPERTY"], ["PROPERTY"], [project_id]
        )
        reviewer_token = _token(
            client, organization_id, reviewer, ["PROPERTY"], ["PROPERTY"], [project_id]
        )
        submitter_headers = {"Authorization": f"Bearer {submitter_token}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

        accepted_document = _create_document(
            client, submitter_headers, project_id, "Foto Progres Diterima"
        )
        variance_document = _create_document(
            client, submitter_headers, project_id, "Foto Progres Variance"
        )
        created["documents"].extend([accepted_document, variance_document])

        accepted = _submit_evidence(
            client,
            submitter_headers,
            project_id,
            accepted_document["document_version_id"],
            "WP-FOUNDATION",
            "40.00",
            "38.00",
        )
        created["cases"].append(accepted)
        assert accepted["current_step"] == "human-review"
        assert accepted["variance"] == "-2.00"
        self_review = client.post(
            f"/api/v1/property/site-evidence/{accepted['site_evidence_id']}/review",
            headers={**submitter_headers, "Idempotency-Key": f"review-{uuid4().hex}"},
            json={
                "decision": "ACCEPTED",
                "verified_progress": "38.00",
                "notes": "Percobaan review oleh pengunggah.",
            },
        )
        assert self_review.status_code == 403
        accepted_review = client.post(
            f"/api/v1/property/site-evidence/{accepted['site_evidence_id']}/review",
            headers={**reviewer_headers, "Idempotency-Key": f"review-{uuid4().hex}"},
            json={
                "decision": "ACCEPTED",
                "verified_progress": "38.00",
                "notes": "Pengukuran dan bukti lapangan diterima.",
            },
        )
        assert accepted_review.status_code == 200, accepted_review.text
        accepted_result = accepted_review.json()
        accepted.update(accepted_result)
        assert accepted_result["current_step"] == "kpi-updated"
        assert accepted_result["kpi_snapshot_id"] is not None
        assert accepted_result["exception_id"] is None

        foreign_project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"ISOL-{uuid4().hex[:8].upper()}", "name": "Isolation Test"},
        )
        assert foreign_project_response.status_code == 201
        foreign_project_id = foreign_project_response.json()["project_id"]
        created["foreign_project_id"] = foreign_project_id
        foreign_token = _token(
            client,
            organization_id,
            reviewer,
            ["PROPERTY"],
            ["PROPERTY"],
            [foreign_project_id],
        )
        foreign_headers = {"Authorization": f"Bearer {foreign_token}"}
        foreign_document = _create_document(
            client, foreign_headers, foreign_project_id, "Dokumen Proyek Berbeda"
        )
        created["documents"].append(foreign_document)
        cross_project_evidence = client.post(
            "/api/v1/evidence",
            headers=admin_headers,
            json={
                "work_item_id": accepted["work_item_id"],
                "document_version_id": foreign_document["document_version_id"],
                "claim_type": "CROSS_PROJECT_TEST",
            },
        )
        assert cross_project_evidence.status_code == 404

        variance = _submit_evidence(
            client,
            submitter_headers,
            project_id,
            variance_document["document_version_id"],
            "WP-STRUCTURE",
            "50.00",
            "43.00",
        )
        created["cases"].append(variance)
        variance_review = client.post(
            f"/api/v1/property/site-evidence/{variance['site_evidence_id']}/review",
            headers={**reviewer_headers, "Idempotency-Key": f"review-{uuid4().hex}"},
            json={
                "decision": "VARIANCE",
                "verified_progress": "41.00",
                "notes": "Pengukuran ulang menunjukkan variance material.",
            },
        )
        assert variance_review.status_code == 200, variance_review.text
        variance_result = variance_review.json()
        variance.update(variance_result)
        assert variance_result["current_step"] == "capa-open"
        assert variance_result["exception_id"] is not None
        assert variance_result["capa_id"] is not None
        assert variance_result["kpi_snapshot_id"] is None

        evidence_query = client.get(
            "/api/v1/property/site-evidence",
            headers=reviewer_headers,
            params={"project_id": project_id},
        )
        assert evidence_query.status_code == 200, evidence_query.text
        assert evidence_query.json()["total"] == 2
        kpi_query = client.get(
            f"/api/v1/kpi-snapshots/{accepted_result['kpi_snapshot_id']}",
            headers=reviewer_headers,
        )
        assert kpi_query.status_code == 200, kpi_query.text
        assert kpi_query.json()["verification_status"] == "VERIFIED"
        exception_query = client.get(
            f"/api/v1/exceptions/{variance_result['exception_id']}",
            headers=reviewer_headers,
        )
        assert exception_query.status_code == 200, exception_query.text
        capa_query = client.get(
            f"/api/v1/capas/{variance_result['capa_id']}", headers=reviewer_headers
        )
        assert capa_query.status_code == 200, capa_query.text
        assert capa_query.json()["status"] == "OPEN"

        with psycopg.connect(database_url) as connection:
            snapshot = connection.execute(
                """
                SELECT value, verification_status FROM executive.kpi_snapshots
                WHERE kpi_snapshot_id = %s
                """,
                (accepted_result["kpi_snapshot_id"],),
            ).fetchone()
            assert snapshot is not None
            assert str(snapshot[0]) == "38.0000"
            assert snapshot[1] == "VERIFIED"
            capa = connection.execute(
                """
                SELECT c.status, e.status FROM governance.capas c
                JOIN governance.exceptions e ON e.exception_id = c.exception_id
                WHERE c.capa_id = %s
                """,
                (variance_result["capa_id"],),
            ).fetchone()
            assert capa == ("OPEN", "CAPA_REQUIRED")
    finally:
        _cleanup(database_url, created)


def _create_property_user(client: TestClient, headers: dict[str, str], label: str) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"property-{label}-{uuid4().hex[:8]}@example.test",
            "display_name": f"Property {label.title()} Sintetis",
            "division_code": "PROPERTY",
            "role": "PROPERTY",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def _create_document(
    client: TestClient, headers: dict[str, str], project_id: str, name: str
) -> dict[str, Any]:
    content = f"synthetic-site-evidence-{uuid4()}".encode()
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "project_id": project_id,
            "logical_name": name,
            "classification": "INTERNAL",
            "object_key": f"synthetic/property/{uuid4()}.jpg",
            "sha256": hashlib.sha256(content).hexdigest(),
            "media_type": "image/jpeg",
            "size_bytes": len(content),
        },
    )
    assert response.status_code == 201
    return response.json()


def _submit_evidence(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    document_version_id: str,
    work_package_code: str,
    claimed_progress: str,
    measured_progress: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/property/site-evidence",
        headers={**headers, "Idempotency-Key": f"site-{uuid4().hex}"},
        json={
            "project_id": project_id,
            "document_version_id": document_version_id,
            "work_package_code": work_package_code,
            "claim_date": date.today().isoformat(),
            "claimed_progress": claimed_progress,
            "measured_progress": measured_progress,
            "measurement_note": "Pengukuran progres sintetis untuk integration test.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _token(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
    projects: list[object] | None = None,
) -> str:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": roles,
            "division_codes": divisions,
            "project_ids": [str(item) for item in projects or []],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _cleanup(database_url: str, created: dict[str, Any]) -> None:
    with psycopg.connect(database_url) as connection:
        for case in created.get("cases", []):
            site_id = case.get("site_evidence_id")
            work_item_id = case.get("work_item_id")
            workflow_id = case.get("workflow_run_id")
            if site_id:
                connection.execute(
                    "DELETE FROM executive.kpi_snapshots WHERE source_entity_id = %s", (site_id,)
                )
            if case.get("capa_id"):
                connection.execute(
                    "DELETE FROM governance.capas WHERE capa_id = %s", (case["capa_id"],)
                )
            if case.get("exception_id"):
                connection.execute(
                    "DELETE FROM governance.exceptions WHERE exception_id = %s",
                    (case["exception_id"],),
                )
            if site_id:
                connection.execute(
                    "DELETE FROM property.site_evidence WHERE site_evidence_id = %s", (site_id,)
                )
            if work_item_id:
                connection.execute(
                    "DELETE FROM platform.evidence WHERE work_item_id = %s", (work_item_id,)
                )
            if workflow_id:
                connection.execute(
                    "DELETE FROM workflow.transition_events WHERE workflow_run_id = %s",
                    (workflow_id,),
                )
                connection.execute(
                    "DELETE FROM agents.agent_runs WHERE workflow_run_id = %s", (workflow_id,)
                )
                connection.execute(
                    "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s", (workflow_id,)
                )
            if work_item_id:
                connection.execute(
                    "DELETE FROM platform.work_items WHERE work_item_id = %s", (work_item_id,)
                )
        for document in created.get("documents", []):
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s", (document["document_id"],)
            )
        entity_ids = [
            str(value)
            for case in created.get("cases", [])
            for key, value in case.items()
            if key.endswith("_id") and value
        ]
        entity_ids.extend(
            str(document[key])
            for document in created.get("documents", [])
            for key in ("document_id", "document_version_id")
        )
        if created.get("project_id"):
            entity_ids.append(str(created["project_id"]))
        if created.get("foreign_project_id"):
            entity_ids.append(str(created["foreign_project_id"]))
        if entity_ids:
            connection.execute("DELETE FROM audit.entries WHERE entity_id = ANY(%s)", (entity_ids,))
        if created.get("project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
            )
        if created.get("foreign_project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s",
                (created["foreign_project_id"],),
            )
        for user_id in created.get("user_ids", []):
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))

import hashlib
import os
from datetime import date, timedelta
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


def test_permit_and_contract_reach_controlled_legal_review() -> None:
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
        submitter = _create_legal_user(client, admin_headers, "submitter")
        reviewer = _create_legal_user(client, admin_headers, "reviewer")
        created["user_ids"] = [submitter, reviewer]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"LEGAL-{uuid4().hex[:8].upper()}", "name": "Legal Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        submitter_token = _token(
            client, organization_id, submitter, ["LEGAL"], ["LEGAL"], [project_id]
        )
        reviewer_token = _token(
            client, organization_id, reviewer, ["LEGAL"], ["LEGAL"], [project_id]
        )
        submitter_headers = {"Authorization": f"Bearer {submitter_token}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

        permit_document = _create_document(client, submitter_headers, project_id, "Izin Sintetis")
        contract_document = _create_document(
            client, submitter_headers, project_id, "Kontrak Sintetis"
        )
        created["documents"].extend([permit_document, contract_document])

        permit = _submit_legal_document(
            client,
            submitter_headers,
            {
                "project_id": project_id,
                "document_version_id": permit_document["document_version_id"],
                "document_type": "PERMIT",
                "reference_code": f"PERMIT-{uuid4().hex[:8].upper()}",
                "title": "Izin Operasional Sintetis",
                "source_authority": "Instansi Resmi Sintetis",
                "effective_date": date.today().isoformat(),
                "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            },
        )
        created["cases"].append(permit)
        assert permit["current_step"] == "legal-review"
        self_review = client.post(
            f"/api/v1/legal/documents/{permit['legal_case_id']}/review",
            headers=submitter_headers,
            json={
                "decision": "APPROVED",
                "legal_status": "VERIFIED",
                "official_source_verified": True,
                "notes": "Percobaan review oleh pengaju.",
            },
        )
        assert self_review.status_code == 403
        unverified_source = client.post(
            f"/api/v1/legal/documents/{permit['legal_case_id']}/review",
            headers=reviewer_headers,
            json={
                "decision": "APPROVED",
                "legal_status": "VERIFIED",
                "official_source_verified": False,
                "notes": "Sumber resmi belum diperiksa.",
            },
        )
        assert unverified_source.status_code == 409
        permit_review = client.post(
            f"/api/v1/legal/documents/{permit['legal_case_id']}/review",
            headers=reviewer_headers,
            json={
                "decision": "APPROVED",
                "legal_status": "VERIFIED",
                "official_source_verified": True,
                "notes": "Sumber resmi dan dokumen telah diverifikasi Legal Human.",
            },
        )
        assert permit_review.status_code == 200, permit_review.text
        permit_result = permit_review.json()
        permit.update(permit_result)
        assert permit_result["current_step"] == "legal-approved"
        assert permit_result["exception_id"] is None

        contract = _submit_legal_document(
            client,
            submitter_headers,
            {
                "project_id": project_id,
                "document_version_id": contract_document["document_version_id"],
                "document_type": "CONTRACT",
                "reference_code": f"CONTRACT-{uuid4().hex[:8].upper()}",
                "title": "Kontrak Vendor Sintetis",
                "counterparty": "Vendor Sintetis",
                "effective_date": date.today().isoformat(),
            },
        )
        created["cases"].append(contract)
        contract_review = client.post(
            f"/api/v1/legal/documents/{contract['legal_case_id']}/review",
            headers=reviewer_headers,
            json={
                "decision": "REVISION_REQUESTED",
                "legal_status": "CONDITIONAL",
                "official_source_verified": False,
                "notes": "Klausul kewajiban memerlukan revisi oleh pemilik dokumen.",
            },
        )
        assert contract_review.status_code == 200, contract_review.text
        contract_result = contract_review.json()
        contract.update(contract_result)
        assert contract_result["current_step"] == "exception-open"
        assert contract_result["exception_id"] is not None

        with psycopg.connect(database_url) as connection:
            agent_ids = connection.execute(
                """
                SELECT ar.definition->>'agent_id'
                FROM agents.agent_runs run
                JOIN agents.agent_releases ar
                  ON ar.agent_release_id = run.agent_release_id
                WHERE run.workflow_run_id = %s
                ORDER BY run.started_at
                """,
                (permit["workflow_run_id"],),
            ).fetchall()
            assert {row[0] for row in agent_ids} == {"DIA", "LPA", "CEA"}
            exception = connection.execute(
                """
                SELECT category, status FROM governance.exceptions
                WHERE exception_id = %s
                """,
                (contract_result["exception_id"],),
            ).fetchone()
            assert exception == ("CONTRACT_REVIEW_NOT_APPROVED", "OPEN")
    finally:
        _cleanup(database_url, created)


def _create_legal_user(client: TestClient, headers: dict[str, str], label: str) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"legal-{label}-{uuid4().hex[:8]}@example.test",
            "display_name": f"Legal {label.title()} Sintetis",
            "division_code": "LEGAL",
            "role": "LEGAL",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def _create_document(
    client: TestClient, headers: dict[str, str], project_id: str, name: str
) -> dict[str, Any]:
    content = f"synthetic-legal-document-{uuid4()}".encode()
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "project_id": project_id,
            "logical_name": name,
            "classification": "CONFIDENTIAL",
            "object_key": f"synthetic/legal/{uuid4()}.pdf",
            "sha256": hashlib.sha256(content).hexdigest(),
            "media_type": "application/pdf",
            "size_bytes": len(content),
        },
    )
    assert response.status_code == 201
    return response.json()


def _submit_legal_document(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/legal/documents",
        headers={**headers, "Idempotency-Key": f"legal-{uuid4().hex}"},
        json=payload,
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
            work_item_id = case.get("work_item_id")
            workflow_id = case.get("workflow_run_id")
            if case.get("exception_id"):
                connection.execute(
                    "DELETE FROM governance.exceptions WHERE exception_id = %s",
                    (case["exception_id"],),
                )
            if case.get("legal_case_id"):
                connection.execute(
                    "DELETE FROM legal.cases WHERE legal_case_id = %s", (case["legal_case_id"],)
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
        if entity_ids:
            connection.execute("DELETE FROM audit.entries WHERE entity_id = ANY(%s)", (entity_ids,))
        if created.get("project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
            )
        for user_id in created.get("user_ids", []):
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))

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


def test_recruitment_decision_controls_personnel_checklist() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_token = _token(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created: dict[str, Any] = {"documents": [], "requests": []}

    try:
        submitter = _create_hr_user(client, admin_headers, "submitter")
        reviewer = _create_hr_user(client, admin_headers, "reviewer")
        created["user_ids"] = [submitter, reviewer]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"HR-{uuid4().hex[:8].upper()}", "name": "HR Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        submitter_token = _token(client, organization_id, submitter, ["HR"], ["HR"], [project_id])
        reviewer_token = _token(client, organization_id, reviewer, ["HR"], ["HR"], [project_id])
        submitter_headers = {"Authorization": f"Bearer {submitter_token}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

        selected_document = _create_document(
            client, submitter_headers, project_id, "CV Sanitasi Kandidat A"
        )
        rejected_document = _create_document(
            client, submitter_headers, project_id, "CV Sanitasi Kandidat B"
        )
        created["documents"].extend([selected_document, rejected_document])

        selected = _submit_recruitment(
            client,
            submitter_headers,
            project_id,
            selected_document["document_version_id"],
            "KANDIDAT-A",
            "Staf Administrasi",
            ["CV", "EDUCATION_CERTIFICATE", "WORK_SAMPLE"],
            ["CV", "WORK_SAMPLE"],
        )
        created["requests"].append(selected)
        assert selected["current_step"] == "hr-review"
        assert selected["recruitment_status"] == "PENDING_HR_REVIEW"
        assert selected["screening_status"] == "INCOMPLETE"
        assert selected["missing_criteria"] == ["EDUCATION_CERTIFICATE"]

        self_decision = client.post(
            f"/api/v1/hr/recruitment-requests/{selected['recruitment_request_id']}/decision",
            headers={**submitter_headers, "Idempotency-Key": f"decision-{uuid4().hex}"},
            json={
                "decision": "SELECTED",
                "notes": "Percobaan keputusan oleh pengaju.",
                "personnel_requirements": ["IDENTITY_DOCUMENT"],
            },
        )
        assert self_decision.status_code == 403
        selected_decision = client.post(
            f"/api/v1/hr/recruitment-requests/{selected['recruitment_request_id']}/decision",
            headers={**reviewer_headers, "Idempotency-Key": f"decision-{uuid4().hex}"},
            json={
                "decision": "SELECTED",
                "notes": "HR Human memilih kandidat setelah review administratif.",
                "personnel_requirements": [
                    "IDENTITY_DOCUMENT",
                    "BANK_ACCOUNT",
                    "TAX_ID",
                ],
            },
        )
        assert selected_decision.status_code == 200, selected_decision.text
        selected_result = selected_decision.json()
        selected.update(selected_result)
        assert selected_result["current_step"] == "onboarding-checklist"
        assert selected_result["personnel_checklist_id"] is not None

        rejected = _submit_recruitment(
            client,
            submitter_headers,
            project_id,
            rejected_document["document_version_id"],
            "KANDIDAT-B",
            "Staf Operasional",
            ["CV", "WORK_EXPERIENCE"],
            ["CV", "WORK_EXPERIENCE"],
        )
        created["requests"].append(rejected)
        rejected_decision = client.post(
            f"/api/v1/hr/recruitment-requests/{rejected['recruitment_request_id']}/decision",
            headers={**reviewer_headers, "Idempotency-Key": f"decision-{uuid4().hex}"},
            json={
                "decision": "REJECTED",
                "notes": "HR Human menutup kandidat setelah proses review.",
                "personnel_requirements": [],
            },
        )
        assert rejected_decision.status_code == 200, rejected_decision.text
        rejected_result = rejected_decision.json()
        rejected.update(rejected_result)
        assert rejected_result["current_step"] == "request-closed"
        assert rejected_result["personnel_checklist_id"] is None

        with psycopg.connect(database_url) as connection:
            requirements = connection.execute(
                """
                SELECT requirement_code, status FROM hr.personnel_requirements
                WHERE personnel_checklist_id = %s ORDER BY requirement_code
                """,
                (selected_result["personnel_checklist_id"],),
            ).fetchall()
            assert requirements == [
                ("BANK_ACCOUNT", "MISSING"),
                ("IDENTITY_DOCUMENT", "MISSING"),
                ("TAX_ID", "MISSING"),
            ]
            agent_ids = connection.execute(
                """
                SELECT ar.definition->>'agent_id'
                FROM agents.agent_runs run
                JOIN agents.agent_releases ar
                  ON ar.agent_release_id = run.agent_release_id
                WHERE run.workflow_run_id = %s
                """,
                (selected["workflow_run_id"],),
            ).fetchall()
            assert {row[0] for row in agent_ids} == {"SEA", "HRA", "HPA"}
    finally:
        _cleanup(database_url, created)


def _create_hr_user(client: TestClient, headers: dict[str, str], label: str) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"hr-{label}-{uuid4().hex[:8]}@example.test",
            "display_name": f"HR {label.title()} Sintetis",
            "division_code": "HR",
            "role": "HR",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def _create_document(
    client: TestClient, headers: dict[str, str], project_id: str, name: str
) -> dict[str, Any]:
    content = f"synthetic-sanitized-candidate-{uuid4()}".encode()
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "project_id": project_id,
            "logical_name": name,
            "classification": "CONFIDENTIAL",
            "object_key": f"synthetic/hr/{uuid4()}.pdf",
            "sha256": hashlib.sha256(content).hexdigest(),
            "media_type": "application/pdf",
            "size_bytes": len(content),
        },
    )
    assert response.status_code == 201
    return response.json()


def _submit_recruitment(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    document_version_id: str,
    candidate_alias: str,
    position_title: str,
    required_criteria: list[str],
    met_criteria: list[str],
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/hr/recruitment-requests",
        headers={**headers, "Idempotency-Key": f"recruit-{uuid4().hex}"},
        json={
            "project_id": project_id,
            "candidate_document_version_id": document_version_id,
            "position_title": position_title,
            "requesting_division_code": "HR",
            "employment_type": "CONTRACT",
            "headcount": 1,
            "justification": "Kebutuhan tenaga tambahan untuk pengujian workflow internal.",
            "criteria_version": "0.1.0",
            "candidate_alias": candidate_alias,
            "required_criteria": required_criteria,
            "met_criteria": met_criteria,
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
        for request in created.get("requests", []):
            request_id = request.get("recruitment_request_id")
            work_item_id = request.get("work_item_id")
            workflow_id = request.get("workflow_run_id")
            checklist_id = request.get("personnel_checklist_id")
            if checklist_id:
                connection.execute(
                    "DELETE FROM hr.personnel_requirements WHERE personnel_checklist_id = %s",
                    (checklist_id,),
                )
                connection.execute(
                    "DELETE FROM hr.personnel_checklists WHERE personnel_checklist_id = %s",
                    (checklist_id,),
                )
            if request_id:
                connection.execute(
                    "DELETE FROM hr.candidates WHERE recruitment_request_id = %s", (request_id,)
                )
                connection.execute(
                    "DELETE FROM hr.recruitment_requests WHERE recruitment_request_id = %s",
                    (request_id,),
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
            for request in created.get("requests", [])
            for key, value in request.items()
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

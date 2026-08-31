import os
from uuid import UUID, uuid4

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


def _token(
    client: TestClient,
    organization_id: UUID,
    role: str,
    *,
    division: str | None = None,
    project_id: UUID | None = None,
) -> str:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(organization_id),
            "roles": [role],
            "division_codes": [division] if division else [],
            "project_ids": [str(project_id)] if project_id else [],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_controlled_pilot_uat_requires_evidence_and_all_human_signoffs() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]

    client = TestClient(app)
    it_token = _token(client, organization_id, "IT_ADMIN", division="IT")
    director_token = _token(client, organization_id, "DIRECTOR")
    project_response = client.post(
        "/api/v1/projects",
        headers=_headers(it_token),
        json={
            "code": f"UAT-{uuid4().hex[:8].upper()}",
            "name": "UAT Controlled Pilot Sintetis",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = UUID(project_response.json()["project_id"])
    run_id: UUID | None = None
    audited_entity_ids: set[str] = {str(project_id)}

    try:
        activation = client.patch(
            f"/api/v1/projects/{project_id}/status",
            headers=_headers(director_token),
            json={
                "status": "ACTIVE",
                "reason": "Aktivasi proyek untuk UAT sintetis terkontrol.",
            },
        )
        assert activation.status_code == 200, activation.text
        created = client.post(
            "/api/v1/uat/runs",
            headers=_headers(it_token),
            json={"project_id": str(project_id), "title": "Siklus UAT Sintetis"},
        )
        assert created.status_code == 201, created.text
        run_id = UUID(created.json()["uat_run_id"])
        audited_entity_ids.add(str(run_id))
        assert len(created.json()["scenarios"]) == 8
        assert created.json()["status"] == "DRAFT"
        duplicate_cycle = client.post(
            "/api/v1/uat/runs",
            headers=_headers(it_token),
            json={"project_id": str(project_id), "title": "Siklus Paralel Ditolak"},
        )
        assert duplicate_cycle.status_code == 409
        assert "state" in duplicate_cycle.json()["detail"].lower()

        started = client.post(
            f"/api/v1/uat/runs/{run_id}/start", headers=_headers(it_token)
        )
        assert started.status_code == 200, started.text

        scenario_actors = {
            "UAT-01": _token(
                client,
                organization_id,
                "SALES",
                division="SALES_MARKETING",
                project_id=project_id,
            ),
            "UAT-02": _token(
                client,
                organization_id,
                "FINANCE",
                division="FINANCE",
                project_id=project_id,
            ),
            "UAT-03": _token(
                client,
                organization_id,
                "PROPERTY",
                division="PROPERTY",
                project_id=project_id,
            ),
            "UAT-04": _token(
                client,
                organization_id,
                "LEGAL",
                division="LEGAL",
                project_id=project_id,
            ),
            "UAT-05": _token(
                client,
                organization_id,
                "HR",
                division="HR",
                project_id=project_id,
            ),
            "UAT-06": _token(client, organization_id, "AI_EXECUTIVE"),
            "UAT-07": it_token,
            "UAT-08": it_token,
        }
        latest = started.json()
        for scenario_id, actor_token in scenario_actors.items():
            response = client.put(
                f"/api/v1/uat/runs/{run_id}/scenarios/{scenario_id}",
                headers=_headers(actor_token),
                json={
                    "status": "PASSED",
                    "actual_result": f"{scenario_id} berhasil sesuai acceptance criteria.",
                    "evidence": [{"reference": f"SYNTHETIC-EVIDENCE-{scenario_id}"}],
                },
            )
            assert response.status_code == 200, response.text
            latest = response.json()
            scenario = next(
                item for item in latest["scenarios"] if item["scenario_id"] == scenario_id
            )
            audited_entity_ids.add(scenario["scenario_result_id"])
        assert latest["status"] == "READY_FOR_SIGNOFF"

        sales_operator_signoff = client.post(
            f"/api/v1/uat/runs/{run_id}/signoffs",
            headers=_headers(scenario_actors["UAT-01"]),
            json={
                "signoff_scope": "SALES_MARKETING",
                "decision": "ACCEPTED",
                "notes": "Operator tidak boleh menandatangani sebagai business owner.",
            },
        )
        assert sales_operator_signoff.status_code == 403

        signers = {
            "SALES_MARKETING": _token(
                client,
                organization_id,
                "DIVISION_HEAD",
                division="SALES_MARKETING",
                project_id=project_id,
            ),
            "FINANCE": _token(
                client,
                organization_id,
                "DIVISION_HEAD",
                division="FINANCE",
                project_id=project_id,
            ),
            "PROPERTY": _token(
                client,
                organization_id,
                "DIVISION_HEAD",
                division="PROPERTY",
                project_id=project_id,
            ),
            "HR": _token(
                client,
                organization_id,
                "DIVISION_HEAD",
                division="HR",
                project_id=project_id,
            ),
            "LEGAL": _token(
                client,
                organization_id,
                "DIVISION_HEAD",
                division="LEGAL",
                project_id=project_id,
            ),
            "IT": it_token,
            "AI_EXECUTIVE": scenario_actors["UAT-06"],
            "DIRECTOR": director_token,
        }
        for scope, signer_token in signers.items():
            response = client.post(
                f"/api/v1/uat/runs/{run_id}/signoffs",
                headers=_headers(signer_token),
                json={
                    "signoff_scope": scope,
                    "decision": "ACCEPTED",
                    "notes": f"Scope {scope} menerima hasil UAT sintetis.",
                },
            )
            assert response.status_code == 200, response.text
            latest = response.json()
        assert latest["status"] == "ACCEPTED"
        assert latest["completed_at"] is not None
        assert len(latest["signoffs"]) == 8
        audited_entity_ids.update(item["signoff_id"] for item in latest["signoffs"])

        gate = client.get(
            "/api/v1/system/go-live-readiness",
            headers=_headers(it_token),
            params={"project_id": str(project_id)},
        )
        assert gate.status_code == 200, gate.text
        checks = {item["check_id"]: item for item in gate.json()["checks"]}
        assert checks["PILOT-UAT-SCENARIOS"]["status"] == "PASS"
        assert checks["PILOT-UAT-SIGNOFFS"]["status"] == "PASS"
        assert checks["PILOT-UAT-ACCEPTANCE"]["status"] == "PASS"
        assert checks["PILOT-RECOVERY-DRILL"]["status"] == "PASS"
    finally:
        with psycopg.connect(database_url) as connection:
            if audited_entity_ids:
                connection.execute(
                    "DELETE FROM audit.entries WHERE entity_id = ANY(%s)",
                    (list(audited_entity_ids),),
                )
            if run_id is not None:
                connection.execute("DELETE FROM uat.runs WHERE uat_run_id = %s", (run_id,))
            connection.execute("DELETE FROM platform.projects WHERE project_id = %s", (project_id,))

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


def test_system_facts_become_director_reviewed_executive_brief() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_token = _token(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created: dict[str, Any] = {}

    try:
        ai_executive = _create_organization_user(
            client, admin_headers, "AI_EXECUTIVE", "AI Executive Sintetis"
        )
        director = _create_organization_user(client, admin_headers, "DIRECTOR", "Direktur Sintetis")
        created["user_ids"] = [ai_executive, director]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"EXEC-{uuid4().hex[:8].upper()}", "name": "Executive Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        _seed_governance_facts(database_url, organization_id, project_id, ai_executive, created)
        executive_headers = {
            "Authorization": (
                f"Bearer {_token(client, organization_id, ai_executive, ['AI_EXECUTIVE'], [])}"
            )
        }
        director_headers = {
            "Authorization": f"Bearer {_token(client, organization_id, director, ['DIRECTOR'], [])}"
        }
        response = client.post(
            "/api/v1/executive/briefs",
            headers={**executive_headers, "Idempotency-Key": f"brief-{uuid4().hex}"},
            json={
                "title": "Brief Eksekutif Sintetis",
                "period_start": (date.today() - timedelta(days=1)).isoformat(),
                "period_end": (date.today() + timedelta(days=1)).isoformat(),
                "project_id": project_id,
            },
        )
        assert response.status_code == 201, response.text
        brief = response.json()
        created.update(brief)
        assert brief["current_step"] == "brief-review"
        assert brief["brief_status"] == "PENDING_REVIEW"
        assert brief["summary_counts"]["active_work_items"] >= 1
        assert brief["summary_counts"]["pending_approvals"] >= 1
        assert brief["summary_counts"]["open_exceptions"] >= 1
        assert brief["summary_counts"]["critical_exceptions"] >= 1
        assert brief["summary_counts"]["active_capas"] >= 1
        assert brief["decision_item_count"] == 3
        assert len(brief["source_references"]) == len(brief["summary_counts"])
        assert "seluruh angka berasal dari snapshot alos" in brief["narrative"].lower()

        unauthorized_review = client.post(
            f"/api/v1/executive/briefs/{brief['executive_brief_id']}/review",
            headers=executive_headers,
            json={"decision": "PUBLISHED", "notes": "Percobaan publish non-Direktur."},
        )
        assert unauthorized_review.status_code == 403
        review = client.post(
            f"/api/v1/executive/briefs/{brief['executive_brief_id']}/review",
            headers=director_headers,
            json={
                "decision": "PUBLISHED",
                "notes": "Direktur telah memeriksa sumber dan menerbitkan brief.",
            },
        )
        assert review.status_code == 200, review.text
        result = review.json()
        assert result["current_step"] == "brief-published"
        assert result["brief_status"] == "PUBLISHED"
        assert result["terminal"] is True

        with psycopg.connect(database_url) as connection:
            agent_ids = connection.execute(
                """
                SELECT ar.definition->>'agent_id'
                FROM agents.agent_runs run
                JOIN agents.agent_releases ar
                  ON ar.agent_release_id = run.agent_release_id
                WHERE run.workflow_run_id = %s
                """,
                (brief["workflow_run_id"],),
            ).fetchall()
            assert {row[0] for row in agent_ids} == {"KDA", "CRA", "ARA", "MCA"}
            snapshot = connection.execute(
                """
                SELECT source_hash, jsonb_array_length(source_references)
                FROM executive.snapshots s
                JOIN executive.briefs b
                  ON b.executive_snapshot_id = s.executive_snapshot_id
                WHERE b.executive_brief_id = %s
                """,
                (brief["executive_brief_id"],),
            ).fetchone()
            assert snapshot is not None
            assert len(snapshot[0]) == 64
            assert snapshot[1] == len(brief["source_references"])
    finally:
        _cleanup(database_url, created)


def _create_organization_user(
    client: TestClient, headers: dict[str, str], role: str, name: str
) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"{role.lower()}-{uuid4().hex[:8]}@example.test",
            "display_name": name,
            "division_code": None,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["division_code"] is None
    return response.json()["user_id"]


def _seed_governance_facts(
    database_url: str,
    organization_id: object,
    project_id: str,
    requester_id: str,
    created: dict[str, Any],
) -> None:
    work_item_id, exception_id, capa_id, approval_id = uuid4(), uuid4(), uuid4(), uuid4()
    created.update(
        {
            "synthetic_work_item_id": str(work_item_id),
            "synthetic_exception_id": str(exception_id),
            "synthetic_capa_id": str(capa_id),
            "synthetic_approval_id": str(approval_id),
        }
    )
    with psycopg.connect(database_url) as connection:
        division_id = connection.execute(
            """
            SELECT division_id FROM identity.divisions
            WHERE organization_id = %s AND code = 'PROPERTY'
            """,
            (organization_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO platform.work_items
                (work_item_id, organization_id, project_id, division_id, title,
                 work_type, priority, status, correlation_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'Executive Fact Sintetis',
                    'EXECUTIVE_TEST_FACT', 'CRITICAL', 'BLOCKED', %s, now(), now())
            """,
            (work_item_id, organization_id, project_id, division_id, uuid4()),
        )
        connection.execute(
            """
            INSERT INTO governance.exceptions
                (exception_id, organization_id, work_item_id, category, severity,
                 status, created_at)
            VALUES (%s, %s, %s, 'EXECUTIVE_TEST_RISK', 'CRITICAL',
                    'CAPA_REQUIRED', now())
            """,
            (exception_id, organization_id, work_item_id),
        )
        connection.execute(
            """
            INSERT INTO governance.capas
                (capa_id, exception_id, status, root_cause, corrective_action,
                 preventive_action, created_at)
            VALUES (%s, %s, 'OPEN', 'Penyebab sintetis', 'Tindakan sintetis',
                    'Pencegahan sintetis', now())
            """,
            (capa_id, exception_id),
        )
        connection.execute(
            """
            INSERT INTO governance.approval_requests
                (approval_request_id, work_item_id, requester_user_id, policy_code,
                 policy_version, status, material_fingerprint, created_at)
            VALUES (%s, %s, %s, 'EXECUTIVE_TEST', '0.1.0', 'PENDING', %s, now())
            """,
            (approval_id, work_item_id, requester_id, "a" * 64),
        )


def _token(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
) -> str:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": roles,
            "division_codes": divisions,
            "project_ids": [],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _cleanup(database_url: str, created: dict[str, Any]) -> None:
    with psycopg.connect(database_url) as connection:
        brief_id = created.get("executive_brief_id")
        snapshot_id = created.get("executive_snapshot_id")
        workflow_id = created.get("workflow_run_id")
        if brief_id:
            connection.execute(
                "DELETE FROM executive.decision_items WHERE executive_brief_id = %s", (brief_id,)
            )
            connection.execute(
                "DELETE FROM executive.briefs WHERE executive_brief_id = %s", (brief_id,)
            )
        if snapshot_id:
            connection.execute(
                "DELETE FROM executive.snapshots WHERE executive_snapshot_id = %s", (snapshot_id,)
            )
        if workflow_id:
            connection.execute(
                "DELETE FROM workflow.transition_events WHERE workflow_run_id = %s", (workflow_id,)
            )
            connection.execute(
                "DELETE FROM agents.agent_runs WHERE workflow_run_id = %s", (workflow_id,)
            )
            connection.execute(
                "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s", (workflow_id,)
            )
        if created.get("synthetic_approval_id"):
            connection.execute(
                "DELETE FROM governance.approval_requests WHERE approval_request_id = %s",
                (created["synthetic_approval_id"],),
            )
        if created.get("synthetic_capa_id"):
            connection.execute(
                "DELETE FROM governance.capas WHERE capa_id = %s", (created["synthetic_capa_id"],)
            )
        if created.get("synthetic_exception_id"):
            connection.execute(
                "DELETE FROM governance.exceptions WHERE exception_id = %s",
                (created["synthetic_exception_id"],),
            )
        if created.get("synthetic_work_item_id"):
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s",
                (created["synthetic_work_item_id"],),
            )
        entity_ids = [str(value) for key, value in created.items() if key.endswith("_id") and value]
        entity_ids.extend(str(user_id) for user_id in created.get("user_ids", []))
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

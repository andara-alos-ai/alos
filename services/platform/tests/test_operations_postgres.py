import os
from datetime import UTC, datetime, timedelta
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


def test_operational_queue_approval_exception_and_capa_lifecycle() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]

    client = TestClient(app)
    admin_headers = _headers(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    project_id: str | None = None
    work_item_id: str | None = None
    workflow_run_id: str | None = None
    lead_id: str | None = None
    user_ids: list[str] = []
    approval_id: str | None = None
    exception_id: str | None = None
    capa_id: str | None = None
    document_id: str | None = None

    try:
        project = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={
                "code": f"OPS-{uuid4().hex[:8].upper()}",
                "name": "Project Uji Operasional Sintetis",
            },
        )
        assert project.status_code == 201
        project_id = project.json()["project_id"]

        sales_one = _create_user(
            client, admin_headers, "SALES", "SALES_MARKETING", "Sales Operasional Satu"
        )
        sales_two = _create_user(
            client, admin_headers, "SALES", "SALES_MARKETING", "Sales Operasional Dua"
        )
        head_one = _create_user(
            client,
            admin_headers,
            "DIVISION_HEAD",
            "SALES_MARKETING",
            "Kepala Divisi Operasional Satu",
        )
        head_two = _create_user(
            client,
            admin_headers,
            "DIVISION_HEAD",
            "SALES_MARKETING",
            "Kepala Divisi Operasional Dua",
        )
        user_ids.extend([sales_one, sales_two, head_one, head_two])
        for user_id in user_ids:
            assignment = client.post(
                f"/api/v1/users/{user_id}/project-assignments",
                headers=admin_headers,
                json={
                    "project_id": project_id,
                    "reason": "Penugasan untuk pengujian operasional sintetis",
                },
            )
            assert assignment.status_code == 201

        sales_one_headers = _headers(
            client,
            organization_id,
            sales_one,
            ["SALES"],
            ["SALES_MARKETING"],
            [project_id],
        )
        sales_two_headers = _headers(
            client,
            organization_id,
            sales_two,
            ["SALES"],
            ["SALES_MARKETING"],
            [project_id],
        )
        head_one_headers = _headers(
            client,
            organization_id,
            head_one,
            ["DIVISION_HEAD"],
            ["SALES_MARKETING"],
            [project_id],
        )
        head_two_headers = _headers(
            client,
            organization_id,
            head_two,
            ["DIVISION_HEAD"],
            ["SALES_MARKETING"],
            [project_id],
        )

        lead = client.post(
            "/api/v1/leads",
            headers={**sales_one_headers, "Idempotency-Key": f"ops-{uuid4().hex}"},
            json={
                "project_id": project_id,
                "full_name": "Lead Operasional Sintetis",
                "phone": "081234567891",
                "source": "phase-four-smoke-test",
                "consent_recorded": True,
            },
        )
        assert lead.status_code == 201
        lead_result = lead.json()
        work_item_id = lead_result["work_item_id"]
        workflow_run_id = lead_result["workflow_run_id"]
        lead_id = lead_result["lead_id"]
        with psycopg.connect(database_url) as connection:
            agent_run = connection.execute(
                """
                SELECT handler_id, verification_status, output_reference, evidence_references
                FROM agents.agent_runs WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        assert agent_run[0] == "sales.lead-validation.v1"
        assert agent_run[1] == "VERIFIED"
        assert agent_run[2]["_runtime"]["result"]["valid"] is True
        assert isinstance(agent_run[3], list)

        unassigned = client.get(
            "/api/v1/operational/work-queue",
            headers=sales_one_headers,
            params={"scope": "unassigned", "project_id": project_id},
        )
        assert unassigned.status_code == 200
        assert work_item_id in {item["work_item_id"] for item in unassigned.json()}

        claimed = client.post(
            f"/api/v1/operational/work-items/{work_item_id}/claim",
            headers=sales_one_headers,
            json={"reason": "Mengambil tindak lanjut lead untuk diproses"},
        )
        assert claimed.status_code == 200
        assert claimed.json()["owner_user_id"] == sales_one

        delegated = client.post(
            f"/api/v1/operational/work-items/{work_item_id}/delegate",
            headers=sales_one_headers,
            json={
                "target_user_id": sales_two,
                "reason": "Delegasi kepada PIC yang sedang bertugas",
            },
        )
        assert delegated.status_code == 200
        assert delegated.json()["owner_user_id"] == sales_two

        released = client.post(
            f"/api/v1/operational/work-items/{work_item_id}/release",
            headers=sales_two_headers,
            json={"reason": "Melepas tugas agar dapat dialokasikan ulang"},
        )
        assert released.status_code == 200
        assert released.json()["owner_user_id"] is None

        forbidden = client.post(
            f"/api/v1/operational/work-items/{work_item_id}/claim",
            headers=admin_headers,
            json={"reason": "IT tidak boleh mengambil pekerjaan bisnis"},
        )
        assert forbidden.status_code == 403
        legacy_queue = client.get("/api/v1/work-items", headers=admin_headers)
        assert legacy_queue.status_code == 200
        assert work_item_id not in {item["work_item_id"] for item in legacy_queue.json()}

        deadline = client.patch(
            f"/api/v1/operational/work-items/{work_item_id}/deadline",
            headers=head_one_headers,
            json={
                "due_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                "reason": "Menetapkan ulang batas waktu tindak lanjut",
            },
        )
        assert deadline.status_code == 200
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.work_items SET due_at = now() - interval '5 minutes' "
                "WHERE work_item_id = %s",
                (work_item_id,),
            )

        evaluated = client.post(
            "/api/v1/operational/deadlines/evaluate",
            headers=admin_headers,
            json={"horizon_minutes": 60},
        )
        assert evaluated.status_code == 200
        assert evaluated.json()["work_items_overdue"] >= 1
        assert evaluated.json()["reminders_created"] >= 1
        evaluated_again = client.post(
            "/api/v1/operational/deadlines/evaluate",
            headers=admin_headers,
            json={"horizon_minutes": 60},
        )
        assert evaluated_again.status_code == 200
        assert evaluated_again.json()["reminders_created"] == 0

        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.work_items "
                "SET last_reminded_at = now() - interval '20 minutes' "
                "WHERE work_item_id = %s",
                (work_item_id,),
            )
        escalated = client.post(
            "/api/v1/operational/deadlines/evaluate",
            headers=admin_headers,
            json={"horizon_minutes": 60, "escalation_interval_minutes": 15},
        )
        assert escalated.status_code == 200
        assert escalated.json()["reminders_created"] >= 1

        reminders = client.get("/api/v1/operational/reminders", headers=sales_one_headers)
        assert reminders.status_code == 200
        assert work_item_id in {item["work_item_id"] for item in reminders.json()}
        assert any(
            item["work_item_id"] == work_item_id
            and item["reminder_type"] == "ESCALATION"
            and item["escalation_level"] == 2
            for item in reminders.json()
        )

        approval = client.post(
            "/api/v1/approvals",
            headers=head_one_headers,
            json={
                "work_item_id": work_item_id,
                "policy_code": "OPS-SYNTHETIC-01",
                "material_fingerprint": "a" * 64,
                "due_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )
        assert approval.status_code == 201
        approval_id = approval.json()["approval_request_id"]
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE governance.approval_requests "
                "SET due_at = now() - interval '5 minutes' "
                "WHERE approval_request_id = %s",
                (approval_id,),
            )
        approval_deadline = client.post(
            "/api/v1/operational/deadlines/evaluate",
            headers=admin_headers,
            json={"horizon_minutes": 60},
        )
        assert approval_deadline.status_code == 200
        assert approval_deadline.json()["approvals_overdue"] >= 1
        approval_claim = client.post(
            f"/api/v1/approvals/{approval_id}/claim",
            headers=head_two_headers,
            json={"reason": "Mengambil review approval operasional"},
        )
        assert approval_claim.status_code == 200
        assert approval_claim.json()["assigned_approver_user_id"] == head_two
        requester_decision = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=head_one_headers,
            json={"decision": "APPROVED", "reason": "Tidak boleh self approval"},
        )
        assert requester_decision.status_code == 403
        approval_decision = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=head_two_headers,
            json={"decision": "APPROVED", "reason": "Evidence dan scope telah sesuai"},
        )
        assert approval_decision.status_code == 200
        with psycopg.connect(database_url) as connection:
            pending_reminders = connection.execute(
                "SELECT count(*) FROM platform.reminders "
                "WHERE approval_request_id = %s AND status = 'PENDING'",
                (approval_id,),
            ).fetchone()[0]
        assert pending_reminders == 0

        exception = client.post(
            "/api/v1/exceptions",
            headers=head_one_headers,
            json={
                "work_item_id": work_item_id,
                "category": "PROCESS_DEVIATION",
                "severity": "MEDIUM",
            },
        )
        assert exception.status_code == 201
        exception_id = exception.json()["exception_id"]
        investigating = client.post(
            f"/api/v1/exceptions/{exception_id}/transition",
            headers=head_one_headers,
            json={
                "target_status": "INVESTIGATING",
                "reason": "Penyimpangan sedang dianalisis oleh kepala divisi",
            },
        )
        assert investigating.status_code == 200

        capa = client.post(
            "/api/v1/capas",
            headers=head_one_headers,
            json={
                "exception_id": exception_id,
                "root_cause": "Distribusi tugas belum memiliki PIC aktif",
                "corrective_action": "Menetapkan PIC dan memeriksa antrean harian",
                "preventive_action": "Menambahkan pemeriksaan owner pada briefing harian",
            },
        )
        assert capa.status_code == 201
        capa_id = capa.json()["capa_id"]
        assigned_capa = client.post(
            f"/api/v1/capas/{capa_id}/assign",
            headers=head_one_headers,
            json={
                "owner_user_id": sales_one,
                "reason": "Menugaskan tindakan korektif kepada PIC proses",
            },
        )
        assert assigned_capa.status_code == 200
        assert assigned_capa.json()["owner_user_id"] == sales_one
        for target in ("ANALYSIS", "ACTION_IN_PROGRESS", "VERIFICATION"):
            transition = client.post(
                f"/api/v1/capas/{capa_id}/transition",
                headers=sales_one_headers,
                json={
                    "target_status": target,
                    "reason": f"Memproses tahapan CAPA menuju {target}",
                },
            )
            assert transition.status_code == 200

        document = client.post(
            "/api/v1/documents",
            headers=head_one_headers,
            json={
                "project_id": project_id,
                "logical_name": "Evidence Verifikasi CAPA Sintetis",
                "classification": "INTERNAL",
                "object_key": f"synthetic/operations/{uuid4().hex}.txt",
                "sha256": uuid4().hex * 2,
                "media_type": "text/plain",
                "size_bytes": 128,
            },
        )
        assert document.status_code == 201
        document_id = document.json()["document_id"]
        document_version_id = document.json()["document_version_id"]
        closed = client.post(
            f"/api/v1/capas/{capa_id}/transition",
            headers=head_one_headers,
            json={
                "target_status": "CLOSED",
                "reason": "Verifikasi independen telah diselesaikan",
                "verification_notes": "Tindakan telah diterapkan dan bukti diperiksa",
                "evidence_document_version_id": document_version_id,
            },
        )
        assert closed.status_code == 200
        assert closed.json()["reviewer_user_id"] == head_one
        resolved = client.post(
            f"/api/v1/exceptions/{exception_id}/transition",
            headers=head_one_headers,
            json={
                "target_status": "RESOLVED",
                "reason": "CAPA selesai dan evidence telah diverifikasi",
                "resolution_document_version_id": document_version_id,
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "RESOLVED"
    finally:
        _cleanup(
            database_url,
            project_id=project_id,
            work_item_id=work_item_id,
            workflow_run_id=workflow_run_id,
            lead_id=lead_id,
            user_ids=user_ids,
            approval_id=approval_id,
            exception_id=exception_id,
            capa_id=capa_id,
            document_id=document_id,
        )


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    role: str,
    division_code: str,
    display_name: str,
) -> str:
    response = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": f"ops-{uuid4().hex[:12]}@example.test",
            "display_name": display_name,
            "division_code": division_code,
            "role": role,
        },
    )
    assert response.status_code == 201
    return str(response.json()["user_id"])


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
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cleanup(
    database_url: str,
    *,
    project_id: str | None,
    work_item_id: str | None,
    workflow_run_id: str | None,
    lead_id: str | None,
    user_ids: list[str],
    approval_id: str | None,
    exception_id: str | None,
    capa_id: str | None,
    document_id: str | None,
) -> None:
    with psycopg.connect(database_url) as connection:
        if approval_id:
            connection.execute(
                "DELETE FROM governance.approval_decisions WHERE approval_request_id = %s",
                (approval_id,),
            )
        if work_item_id:
            connection.execute(
                "DELETE FROM platform.reminders WHERE work_item_id = %s "
                "OR approval_request_id = %s",
                (work_item_id, approval_id),
            )
        if capa_id:
            connection.execute("DELETE FROM governance.capas WHERE capa_id = %s", (capa_id,))
        if exception_id:
            connection.execute(
                "DELETE FROM governance.exceptions WHERE exception_id = %s", (exception_id,)
            )
        if approval_id:
            connection.execute(
                "DELETE FROM governance.approval_requests WHERE approval_request_id = %s",
                (approval_id,),
            )
        if document_id:
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_id = %s",
                (document_id,),
            )
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s", (document_id,)
            )
        if work_item_id:
            connection.execute(
                "DELETE FROM platform.work_item_assignments WHERE work_item_id = %s",
                (work_item_id,),
            )
        if workflow_run_id:
            for table in ("workflow.transition_events", "agents.agent_runs"):
                connection.execute(
                    f"DELETE FROM {table} WHERE workflow_run_id = %s",  # noqa: S608
                    (workflow_run_id,),
                )
            connection.execute(
                "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s",
                (workflow_run_id,),
            )
        if lead_id:
            connection.execute("DELETE FROM sales.leads WHERE lead_id = %s", (lead_id,))
        if work_item_id:
            connection.execute(
                "DELETE FROM platform.work_items WHERE work_item_id = %s", (work_item_id,)
            )
        entity_ids: list[Any] = [
            item
            for item in [
                project_id,
                work_item_id,
                lead_id,
                approval_id,
                exception_id,
                capa_id,
                document_id,
                *user_ids,
            ]
            if item
        ]
        if entity_ids:
            connection.execute(
                "DELETE FROM audit.entries WHERE entity_id = ANY(%s::text[])",
                (entity_ids,),
            )
        if user_ids:
            connection.execute(
                "DELETE FROM identity.project_assignments WHERE user_id = ANY(%s::uuid[])",
                (user_ids,),
            )
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = ANY(%s::uuid[])",
                (user_ids,),
            )
            connection.execute(
                "DELETE FROM identity.users WHERE user_id = ANY(%s::uuid[])", (user_ids,)
            )
        if project_id:
            connection.execute("DELETE FROM platform.projects WHERE project_id = %s", (project_id,))

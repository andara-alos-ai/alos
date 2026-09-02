import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from alos.config import get_settings
from alos.main import app
from alos.persistence import Database

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_genesis_governance_pipeline_sod_and_release_flow() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT organization_id FROM identity.organizations WHERE code = 'ARM'")
        ).fetchone()
        assert row is not None
        org_id = row[0]

    client = TestClient(app)

    # 1. Bootstrap header
    bootstrap_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    bootstrap_token = bootstrap_res.json()["access_token"]
    bootstrap_headers = {"Authorization": f"Bearer {bootstrap_token}"}

    # 2. Create 4 separate users for SoD verification
    # User A: Director (Requester who also has business review role)
    res_a = client.post(
        "/api/v1/users",
        headers=bootstrap_headers,
        json={
            "email": f"requester-{uuid4().hex[:8]}@example.test",
            "display_name": "Director Requester",
            "division_code": None,
            "role": "DIRECTOR",
        },
    )
    user_a_id = res_a.json()["user_id"]
    token_a = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_a_id),
            "organization_id": str(org_id),
            "roles": ["DIRECTOR"],
            "division_codes": [],
            "project_ids": [],
        },
    ).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User B: Division Head (Business Reviewer)
    res_b = client.post(
        "/api/v1/users",
        headers=bootstrap_headers,
        json={
            "email": f"biz-{uuid4().hex[:8]}@example.test",
            "display_name": "Finance Division Head",
            "division_code": "FINANCE",
            "role": "DIVISION_HEAD",
        },
    )
    user_b_id = res_b.json()["user_id"]
    token_b = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_b_id),
            "organization_id": str(org_id),
            "roles": ["DIVISION_HEAD"],
            "division_codes": ["FINANCE"],
            "project_ids": [],
        },
    ).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User C: IT Admin (Technical Custodian & Stager)
    res_c = client.post(
        "/api/v1/users",
        headers=bootstrap_headers,
        json={
            "email": f"tech-{uuid4().hex[:8]}@example.test",
            "display_name": "IT Admin Custodian",
            "division_code": "IT",
            "role": "IT_ADMIN",
        },
    )
    user_c_id = res_c.json()["user_id"]
    token_c = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_c_id),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    ).json()["access_token"]
    headers_c = {"Authorization": f"Bearer {token_c}"}

    # User D: Director (Releaser)
    res_d = client.post(
        "/api/v1/users",
        headers=bootstrap_headers,
        json={
            "email": f"dir-{uuid4().hex[:8]}@example.test",
            "display_name": "Direktur Utama Releaser",
            "division_code": None,
            "role": "DIRECTOR",
        },
    )
    user_d_id = res_d.json()["user_id"]
    token_d = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_d_id),
            "organization_id": str(org_id),
            "roles": ["DIRECTOR"],
            "division_codes": [],
            "project_ids": [],
        },
    ).json()["access_token"]
    headers_d = {"Authorization": f"Bearer {token_d}"}

    # 3. User A submits a Genesis proposal (strategy: EXTEND on FRA)
    submit_res = client.post(
        "/api/v1/genesis/requests",
        headers=headers_a,
        json={
            "strategy": "EXTEND",
            "justification": "Penambahan validasi invoice vendor otomatis pada modul FRA finance.",
            "source_references": ["ALOS-SP-SYNTHETIC-PILOT@1.0.0"],
            "base": {"agent_id": "FRA", "version": "0.1.0"},
            "candidate": {
                "contract_version": "1.0.0",
                "agent_id": "SUB_FRA_VENDOR",
                "name": "Vendor Invoice Checker",
                "purpose": "Verifikasi invoice dan evidence vendor secara teliti dan akurat.",
                "version": "0.1.0",
                "agent_kind": "SUB_AGENT",
                "parent_agent_id": "FRA",
                "parent_agent_version": "0.1.0",
                "extends": {"agent_id": "FRA", "version": "0.1.0"},
                "domain": "FINANCE",
                "human_owner": "FINANCE_HEAD",
                "triggers": ["ON_INVOICE_SUBMITTED"],
                "inputs": ["invoice_doc"],
                "outputs": ["verification_result"],
                "source_of_truth": ["RAB"],
                "capabilities": [
                    "match_transactions_deterministically",
                    "detect_duplicate_payment",
                    "open_reconciliation_case",
                ],
                "tools_allowed": [
                    "alos.finance.read",
                    "alos.reconciliation.create",
                    "deterministic.calculator",
                ],
                "approval_boundary": ["Persetujuan pembayaran oleh Kadiv Finance"],
                "evidence_requirement": ["Faktur pajak asli"],
                "forbidden_actions": ["Transfer dana mandiri"],
                "metrics": ["Akurasi verifikasi"],
                "escalation": ["Eskalasi ke Kadiv Keuangan"],
                "status": "DRAFT",
            },
        },
    )
    assert submit_res.status_code == 201
    pipeline_data = submit_res.json()
    request_id = pipeline_data["request_id"]
    assert pipeline_data["status"] == "AWAITING_HUMAN_REVIEW"
    assert pipeline_data["next_allowed_action"] == "HUMAN_REVIEW"

    # 4. List requests via GET /api/v1/genesis/requests
    list_res = client.get("/api/v1/genesis/requests", headers=headers_a)
    assert list_res.status_code == 200
    assert any(r["request_id"] == request_id for r in list_res.json())

    # 5. SoD Prevention: Requester (User A) cannot self-approve on Business Gate
    self_review_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/reviews",
        headers=headers_a,
        json={
            "gate": "BUSINESS",
            "decision": "APPROVED",
            "notes": "Saya approve sendiri",
        },
    )
    assert self_review_res.status_code == 403
    assert "Pemohon Genesis tidak boleh mereview" in self_review_res.json()["detail"]

    # 6. Business Gate Approval by User B (Division Head)
    biz_review_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/reviews",
        headers=headers_b,
        json={
            "gate": "BUSINESS",
            "decision": "APPROVED",
            "notes": "Kebutuhan bisnis diverifikasi sesuai SOP Finance.",
        },
    )
    assert biz_review_res.status_code == 200
    assert biz_review_res.json()["status"] == "AWAITING_HUMAN_REVIEW"

    # 7. SoD Prevention: User B cannot also review Technical Gate
    dual_gate_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/reviews",
        headers=headers_b,
        json={
            "gate": "TECHNICAL",
            "decision": "APPROVED",
            "notes": "Saya isi technical gate juga",
        },
    )
    assert dual_gate_res.status_code == 403

    # 8. Technical Gate Approval by User C (IT Admin)
    tech_review_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/reviews",
        headers=headers_c,
        json={
            "gate": "TECHNICAL",
            "decision": "APPROVED",
            "notes": "Kontrak capabilities dan tools aman, tidak mengubah Core Agent.",
        },
    )
    assert tech_review_res.status_code == 200
    assert tech_review_res.json()["status"] == "APPROVED"
    assert tech_review_res.json()["next_allowed_action"] == "STAGE_PACKAGE"

    # 9. SoD Prevention: Requester cannot self-stage
    self_stage_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/stage",
        headers=headers_a,
    )
    assert self_stage_res.status_code == 403

    # 10. Stage Package by User C (IT Admin)
    stage_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/stage",
        headers=headers_c,
    )
    assert stage_res.status_code == 200
    staged_data = stage_res.json()
    assert staged_data["status"] == "STAGED"
    assert staged_data["release"]["status"] == "STAGED"
    assert staged_data["release"]["production_effect"] is False

    # 11. SoD Prevention: Stager (User C) cannot release the package
    stager_release_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/release",
        headers=headers_c,
    )
    assert stager_release_res.status_code == 403

    # 12. Release Package by User D (Director)
    release_res = client.post(
        f"/api/v1/genesis/requests/{request_id}/release",
        headers=headers_d,
    )
    assert release_res.status_code == 200
    released_data = release_res.json()
    assert released_data["status"] == "RELEASED"
    assert released_data["release"]["status"] == "RELEASED"
    assert released_data["release"]["released_by_user_id"] == str(user_d_id)
    assert released_data["release"]["production_effect"] is False
    assert released_data["next_allowed_action"] == "SEPARATE_DEPLOYMENT_APPROVAL"

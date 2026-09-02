import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
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


def test_payment_request_is_approved_paid_and_reconciled() -> None:
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
        requester = _create_finance_user(client, admin_headers, "requester")
        approver = _create_finance_user(client, admin_headers, "approver")
        director = _create_organization_user(
            client, admin_headers, "DIRECTOR", "Direktur Finance Sintetis"
        )
        created["user_ids"] = [requester, approver, director]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"FIN-{uuid4().hex[:8].upper()}", "name": "Finance Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        requester_token = _token(
            client, organization_id, requester, ["FINANCE"], ["FINANCE"], [project_id]
        )
        approver_token = _token(
            client, organization_id, approver, ["FINANCE"], ["FINANCE"], [project_id]
        )
        requester_headers = {"Authorization": f"Bearer {requester_token}"}
        approver_headers = {"Authorization": f"Bearer {approver_token}"}
        budget_response = client.post(
            "/api/v1/finance/budgets",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "code": "OPERASIONAL",
                "name": "Anggaran Operasional Sintetis",
                "allocated_amount": "500000000.00",
            },
        )
        assert budget_response.status_code == 201
        budget_id = budget_response.json()["budget_id"]
        created["budget_id"] = budget_id
        content = f"synthetic-invoice-{uuid4()}".encode()
        document_response = client.post(
            "/api/v1/documents",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "logical_name": "Invoice Sintetis",
                "classification": "INTERNAL",
                "object_key": f"synthetic/{uuid4()}.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "media_type": "application/pdf",
                "size_bytes": len(content),
            },
        )
        assert document_response.status_code == 201
        document = document_response.json()
        created.update(document)
        payment_key = f"pay-{uuid4().hex}"
        payment_payload = {
            "project_id": project_id,
            "budget_id": budget_id,
            "document_version_id": document["document_version_id"],
            "payee_name": "Vendor Sintetis",
            "vendor_reference": "VENDOR-TEST-001",
            "category_code": "MATERIAL",
            "purpose": "Pembelian material pengujian",
            "amount": "100000.00",
            "requested_payment_date": date.today().isoformat(),
        }
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.document_versions SET scan_status = 'REJECTED' "
                "WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
        rejected_document_request = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"rejected-{uuid4().hex}"},
            json=payment_payload,
        )
        assert rejected_document_request.status_code == 404
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.document_versions SET scan_status = 'NOT_CONFIGURED' "
                "WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_requests = [
                executor.submit(
                    client.post,
                    "/api/v1/finance/payment-requests",
                    headers={**requester_headers, "Idempotency-Key": payment_key},
                    json=payment_payload,
                )
                for _ in range(2)
            ]
            concurrent_responses = [request.result() for request in concurrent_requests]
        assert all(response.status_code == 201 for response in concurrent_responses), [
            response.text for response in concurrent_responses
        ]
        assert len(
            {response.json()["payment_request_id"] for response in concurrent_responses}
        ) == 1
        payment = concurrent_responses[0].json()
        created.update(payment)
        assert payment["current_step"] == "finance-approval"
        assert payment["budget_available"] is True
        assert payment["evidence_complete"] is True
        assert payment["approval_route"] == "FINANCE_REVIEWER"
        repeated_request = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": payment_key},
            json=payment_payload,
        )
        assert repeated_request.status_code == 201
        assert repeated_request.json()["payment_request_id"] == payment["payment_request_id"]

        wrong_project_headers = {
            "Authorization": (
                "Bearer "
                + _token(
                    client,
                    organization_id,
                    uuid4(),
                    ["FINANCE"],
                    ["FINANCE"],
                    [uuid4()],
                )
            )
        }
        project_hidden = client.get(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}",
            headers=wrong_project_headers,
        )
        assert project_hidden.status_code == 404
        foreign_organization_headers = {
            "Authorization": (
                "Bearer "
                + _token(
                    client,
                    uuid4(),
                    uuid4(),
                    ["FINANCE"],
                    ["FINANCE"],
                    [project_id],
                )
            )
        }
        tenant_hidden = client.get(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}",
            headers=foreign_organization_headers,
        )
        assert tenant_hidden.status_code == 404
        sales_headers = {
            "Authorization": (
                "Bearer "
                + _token(
                    client,
                    organization_id,
                    uuid4(),
                    ["SALES"],
                    ["SALES_MARKETING"],
                    [project_id],
                )
            )
        }
        division_forbidden = client.post(
            "/api/v1/finance/payment-requests",
            headers={**sales_headers, "Idempotency-Key": f"forbidden-{uuid4().hex}"},
            json=payment_payload,
        )
        assert division_forbidden.status_code == 403
        self_decision_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers={**requester_headers, "Idempotency-Key": f"self-{uuid4().hex}"},
            json={"decision": "APPROVED", "reason": "Percobaan approval oleh requester."},
        )
        assert self_decision_response.status_code == 403
        assert "sendiri" in self_decision_response.json()["detail"]
        decision_key = f"decision-{uuid4().hex}"
        decision_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers={**approver_headers, "Idempotency-Key": decision_key},
            json={"decision": "APPROVED", "reason": "Bukti dan anggaran sesuai."},
        )
        assert decision_response.status_code == 200, decision_response.text
        assert decision_response.json()["current_step"] == "payment-action"
        repeated_decision = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers={**approver_headers, "Idempotency-Key": decision_key},
            json={"decision": "APPROVED", "reason": "Bukti dan anggaran sesuai."},
        )
        assert repeated_decision.status_code == 200
        assert repeated_decision.json() == decision_response.json()
        unauthorized_replay = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers={**requester_headers, "Idempotency-Key": decision_key},
            json={"decision": "APPROVED", "reason": "Bukti dan anggaran sesuai."},
        )
        assert unauthorized_replay.status_code == 403
        reference = f"TRX-{uuid4().hex[:12].upper()}"
        invalid_amount_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers={**approver_headers, "Idempotency-Key": f"invalid-{uuid4().hex}"},
            json={
                "payment_reference": f"INVALID-{reference}",
                "amount": "99999.00",
                "paid_at": datetime.now(UTC).isoformat(),
                "evidence_document_version_id": document["document_version_id"],
            },
        )
        assert invalid_amount_response.status_code == 409
        assert "berbeda" in invalid_amount_response.json()["detail"]
        payment_record_key = f"record-{uuid4().hex}"
        paid_payload = {
            "payment_reference": reference,
            "amount": "100000.00",
            "paid_at": datetime.now(UTC).isoformat(),
            "evidence_document_version_id": document["document_version_id"],
        }
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.document_versions SET verification_status = 'REJECTED' "
                "WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
        rejected_payment_evidence = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers={**approver_headers, "Idempotency-Key": f"bad-proof-{uuid4().hex}"},
            json=paid_payload,
        )
        assert rejected_payment_evidence.status_code == 404
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE platform.document_versions SET verification_status = 'UNVERIFIED' "
                "WHERE document_version_id = %s",
                (document["document_version_id"],),
            )
        paid_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers={**approver_headers, "Idempotency-Key": payment_record_key},
            json=paid_payload,
        )
        assert paid_response.status_code == 200, paid_response.text
        assert paid_response.json()["current_step"] == "reconciliation"
        repeated_payment = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/payment",
            headers={**approver_headers, "Idempotency-Key": payment_record_key},
            json=paid_payload,
        )
        assert repeated_payment.status_code == 200
        assert repeated_payment.json() == paid_response.json()
        reconciliation_key = f"recon-{uuid4().hex}"
        reconciliation_payload = {
            "transaction_reference": reference,
            "transaction_amount": "100000.00",
            "currency": "IDR",
        }
        reconcile_response = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/reconciliation",
            headers={**approver_headers, "Idempotency-Key": reconciliation_key},
            json=reconciliation_payload,
        )
        assert reconcile_response.status_code == 200, reconcile_response.text
        result = reconcile_response.json()
        assert result["current_step"] == "reconciled"
        assert result["reconciliation_status"] == "MATCHED"
        assert result["terminal"] is True
        repeated_reconciliation = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/reconciliation",
            headers={**approver_headers, "Idempotency-Key": reconciliation_key},
            json=reconciliation_payload,
        )
        assert repeated_reconciliation.status_code == 200
        assert repeated_reconciliation.json() == result
        budgets_query = client.get(
            "/api/v1/finance/budgets",
            headers=requester_headers,
            params={"project_id": project_id, "status": "ACTIVE"},
        )
        assert budgets_query.status_code == 200, budgets_query.text
        assert budgets_query.json()["items"][0]["available_amount"] == "499900000.00"
        payment_query = client.get(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}",
            headers=requester_headers,
        )
        assert payment_query.status_code == 200, payment_query.text
        assert payment_query.json()["status"] == "RECONCILED"
        approval_query = client.get(
            "/api/v1/approvals",
            headers=requester_headers,
            params={"project_id": project_id, "status": "APPROVED"},
        )
        assert approval_query.status_code == 200, approval_query.text
        assert approval_query.json()["total"] == 1

        high_value_response = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"director-{uuid4().hex}"},
            json={
                **payment_payload,
                "payee_name": "Vendor Nilai Besar Sintetis",
                "vendor_reference": "VENDOR-DIRECTOR-001",
                "purpose": "Pengujian jalur approval Direktur",
                "amount": "300000000.00",
            },
        )
        assert high_value_response.status_code == 201, high_value_response.text
        high_value = high_value_response.json()
        created["extra_payments"] = [high_value]
        assert high_value["approval_route"] == "DIRECTOR"
        wrong_route_decision = client.post(
            f"/api/v1/finance/payment-requests/{high_value['payment_request_id']}/decision",
            headers={**approver_headers, "Idempotency-Key": f"wrong-route-{uuid4().hex}"},
            json={"decision": "APPROVED", "reason": "Approver Finance biasa ditolak."},
        )
        assert wrong_route_decision.status_code == 403
        director_headers = {
            "Authorization": (
                "Bearer "
                + _token(client, organization_id, director, ["DIRECTOR"], [], [])
            )
        }
        director_decision = client.post(
            f"/api/v1/finance/payment-requests/{high_value['payment_request_id']}/decision",
            headers={**director_headers, "Idempotency-Key": f"director-approve-{uuid4().hex}"},
            json={"decision": "APPROVED", "reason": "Approval Direktur sintetis sesuai route."},
        )
        assert director_decision.status_code == 200, director_decision.text
        assert director_decision.json()["current_step"] == "payment-action"
        director_cancel = client.post(
            f"/api/v1/finance/payment-requests/{high_value['payment_request_id']}/cancel",
            headers={**director_headers, "Idempotency-Key": f"director-cancel-{uuid4().hex}"},
            json={"reason": "Selesai menguji jalur approval Direktur sintetis."},
        )
        assert director_cancel.status_code == 200, director_cancel.text
        assert director_cancel.json()["payment_status"] == "CANCELLED"
        mismatch_request_response = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"mismatch-{uuid4().hex}"},
            json={
                **payment_payload,
                "payee_name": "Vendor Rekonsiliasi Sintetis",
                "vendor_reference": "VENDOR-RECON-MISMATCH",
                "purpose": "Pengujian exception rekonsiliasi FRA",
                "amount": "2000.00",
            },
        )
        assert mismatch_request_response.status_code == 201, mismatch_request_response.text
        mismatch_payment = mismatch_request_response.json()
        created["extra_payments"].append(mismatch_payment)
        mismatch_approval = client.post(
            f"/api/v1/finance/payment-requests/{mismatch_payment['payment_request_id']}/decision",
            headers={**approver_headers, "Idempotency-Key": f"mismatch-approve-{uuid4().hex}"},
            json={"decision": "APPROVED", "reason": "Dokumen mismatch test sesuai."},
        )
        assert mismatch_approval.status_code == 200, mismatch_approval.text
        mismatch_reference = f"TRX-MISMATCH-{uuid4().hex[:8].upper()}"
        mismatch_record = client.post(
            f"/api/v1/finance/payment-requests/{mismatch_payment['payment_request_id']}/payment",
            headers={**approver_headers, "Idempotency-Key": f"mismatch-record-{uuid4().hex}"},
            json={
                "payment_reference": mismatch_reference,
                "amount": "2000.00",
                "paid_at": datetime.now(UTC).isoformat(),
                "evidence_document_version_id": document["document_version_id"],
            },
        )
        assert mismatch_record.status_code == 200, mismatch_record.text
        mismatch_reconciliation = client.post(
            f"/api/v1/finance/payment-requests/"
            f"{mismatch_payment['payment_request_id']}/reconciliation",
            headers={**approver_headers, "Idempotency-Key": f"mismatch-recon-{uuid4().hex}"},
            json={
                "transaction_reference": f"BANK-{uuid4().hex[:8].upper()}",
                "transaction_amount": "2000.00",
                "currency": "IDR",
            },
        )
        assert mismatch_reconciliation.status_code == 200, mismatch_reconciliation.text
        assert mismatch_reconciliation.json()["reconciliation_status"] == "MISMATCH"
        assert mismatch_reconciliation.json()["payment_status"] == "EXCEPTION"
        with psycopg.connect(database_url) as connection:
            mismatch_deadline = connection.execute(
                """
                SELECT ex.due_at, wi.due_at, wi.owner_user_id
                FROM finance.payment_requests pr
                JOIN governance.exceptions ex ON ex.work_item_id = pr.work_item_id
                JOIN platform.work_items wi ON wi.work_item_id = pr.work_item_id
                WHERE pr.payment_request_id = %s
                  AND ex.category = 'RECONCILIATION_MISMATCH'
                """,
                (mismatch_payment["payment_request_id"],),
            ).fetchone()
        assert mismatch_deadline[0] is not None
        assert mismatch_deadline[1] is not None
        assert str(mismatch_deadline[2]) == approver
        incomplete_tax_response = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"tax-incomplete-{uuid4().hex}"},
            json={
                **payment_payload,
                "payee_name": "Vendor Pajak Sintetis",
                "vendor_reference": "VENDOR-TAX-INCOMPLETE",
                "category_code": "TAX",
                "purpose": "Pengujian deterministic evidence completeness",
                "amount": "1000.00",
            },
        )
        assert incomplete_tax_response.status_code == 201, incomplete_tax_response.text
        incomplete_tax = incomplete_tax_response.json()
        created["extra_payments"].append(incomplete_tax)
        assert incomplete_tax["status"] == "EXCEPTION"
        assert incomplete_tax["current_step"] == "exception-open"
        assert incomplete_tax["evidence_complete"] is False
        with psycopg.connect(database_url) as connection:
            property_division_id = connection.execute(
                """
                SELECT division_id FROM identity.divisions
                WHERE organization_id = %s AND code = 'PROPERTY'
                """,
                (organization_id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE platform.documents SET division_id = %s WHERE document_id = %s",
                (property_division_id, document["document_id"]),
            )
        cross_division_document = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"cross-division-{uuid4().hex}"},
            json={
                **payment_payload,
                "payee_name": "Vendor Evidence Lintas Divisi",
                "vendor_reference": "VENDOR-CROSS-DIVISION",
                "purpose": "Evidence Property tidak boleh dipakai oleh Finance",
                "amount": "1000.00",
            },
        )
        assert cross_division_document.status_code == 404
        with psycopg.connect(database_url) as connection:
            amounts = connection.execute(
                "SELECT committed_amount, spent_amount FROM finance.budgets WHERE budget_id = %s",
                (budget_id,),
            ).fetchone()
            assert amounts == (Decimal("2000.00"), Decimal("100000.00"))
            check_rows = connection.execute(
                """
                SELECT check_type, agent_id, status
                FROM finance.payment_checks
                WHERE payment_request_id = %s AND revision_number = 0
                """,
                (payment["payment_request_id"],),
            ).fetchall()
            assert set(check_rows) == {
                ("DOCUMENT", "DIA", "PASSED"),
                ("EVIDENCE", "CEA", "PASSED"),
                ("BUDGET", "BCA", "PASSED"),
                ("APPROVAL_ROUTE", "ARA", "PASSED"),
            }
            agent_ids = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT ar.agent_id
                    FROM agents.agent_runs run
                    JOIN agents.agent_releases ar
                      ON ar.agent_release_id = run.agent_release_id
                    WHERE run.workflow_run_id = %s
                    """,
                    (payment["workflow_run_id"],),
                ).fetchall()
            }
            assert agent_ids == {"DIA", "CEA", "BCA", "ARA", "FRA"}
            dia_execution = connection.execute(
                """
                SELECT run.handler_id, run.verification_status, run.provider_metadata
                FROM agents.agent_runs run
                JOIN agents.agent_releases release
                  ON release.agent_release_id = run.agent_release_id
                WHERE run.workflow_run_id = %s AND release.agent_id = 'DIA'
                ORDER BY run.started_at
                LIMIT 1
                """,
                (payment["workflow_run_id"],),
            ).fetchone()
            assert dia_execution == ("document.metadata.v1", "VERIFIED", {})
            audit_count = connection.execute(
                """
                SELECT count(*) FROM audit.entries
                WHERE entity_type = 'payment_request' AND entity_id = %s
                """,
                (payment["payment_request_id"],),
            ).fetchone()[0]
            assert audit_count >= 4
            tax_exception = connection.execute(
                """
                SELECT ex.category, ex.severity, ex.status
                FROM governance.exceptions ex
                WHERE ex.work_item_id = %s
                """,
                (incomplete_tax["work_item_id"],),
            ).fetchone()
            assert tax_exception == ("EVIDENCE_INCOMPLETE", "HIGH", "OPEN")
            reconciliation_exception = connection.execute(
                """
                SELECT ex.category, ex.severity, ex.status
                FROM governance.exceptions ex
                WHERE ex.work_item_id = %s
                """,
                (mismatch_payment["work_item_id"],),
            ).fetchone()
            assert reconciliation_exception == (
                "RECONCILIATION_MISMATCH",
                "HIGH",
                "CAPA_REQUIRED",
            )
    finally:
        _cleanup(database_url, created)


def test_payment_request_can_be_returned_revised_and_cancelled() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    admin_headers = {
        "Authorization": f"Bearer {_token(client, organization_id, uuid4(), ['IT_ADMIN'], ['IT'])}"
    }
    created: dict[str, Any] = {}
    try:
        requester = _create_finance_user(client, admin_headers, "revision-requester")
        approver = _create_finance_user(client, admin_headers, "revision-approver")
        created["user_ids"] = [requester, approver]
        project_response = client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"code": f"REV-{uuid4().hex[:8].upper()}", "name": "Finance Revision Pilot"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        created["project_id"] = project_id
        requester_token = _token(
            client, organization_id, requester, ["FINANCE"], ["FINANCE"], [project_id]
        )
        approver_token = _token(
            client, organization_id, approver, ["FINANCE"], ["FINANCE"], [project_id]
        )
        requester_headers = {"Authorization": f"Bearer {requester_token}"}
        approver_headers = {"Authorization": f"Bearer {approver_token}"}
        budget_response = client.post(
            "/api/v1/finance/budgets",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "code": "REVISION",
                "name": "Anggaran Revisi Sintetis",
                "allocated_amount": "1000000.00",
            },
        )
        assert budget_response.status_code == 201
        budget_id = budget_response.json()["budget_id"]
        created["budget_id"] = budget_id
        content = f"synthetic-revision-{uuid4()}".encode()
        document_response = client.post(
            "/api/v1/documents",
            headers=requester_headers,
            json={
                "project_id": project_id,
                "logical_name": "Dokumen Revisi Sintetis",
                "classification": "INTERNAL",
                "object_key": f"synthetic/revision/{uuid4()}.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "media_type": "application/pdf",
                "size_bytes": len(content),
            },
        )
        assert document_response.status_code == 201
        document = document_response.json()
        created.update(document)
        payload = {
            "project_id": project_id,
            "budget_id": budget_id,
            "document_version_id": document["document_version_id"],
            "payee_name": "Vendor Revisi Sintetis",
            "category_code": "OPERATIONS",
            "purpose": "Permintaan untuk pengujian return dan cancel",
            "amount": "125000.00",
            "requested_payment_date": date.today().isoformat(),
        }
        request_response = client.post(
            "/api/v1/finance/payment-requests",
            headers={**requester_headers, "Idempotency-Key": f"revision-{uuid4().hex}"},
            json=payload,
        )
        assert request_response.status_code == 201, request_response.text
        payment = request_response.json()
        created.update(payment)
        returned = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/decision",
            headers={**approver_headers, "Idempotency-Key": f"return-{uuid4().hex}"},
            json={
                "decision": "REVISION_REQUESTED",
                "reason": "Lengkapi penjelasan tujuan pembayaran sintetis.",
            },
        )
        assert returned.status_code == 200, returned.text
        assert returned.json()["current_step"] == "revision-required"
        revised = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/revision",
            headers={**requester_headers, "Idempotency-Key": f"resubmit-{uuid4().hex}"},
            json={
                **payload,
                "purpose": "Tujuan pembayaran sintetis telah diperjelas untuk pengujian.",
                "reason": "Pemohon memperbaiki tujuan sesuai catatan approver.",
            },
        )
        assert revised.status_code == 200, revised.text
        assert revised.json()["current_step"] == "finance-approval"
        cancelled = client.post(
            f"/api/v1/finance/payment-requests/{payment['payment_request_id']}/cancel",
            headers={**requester_headers, "Idempotency-Key": f"cancel-{uuid4().hex}"},
            json={"reason": "Kebutuhan sintetis tidak lagi diperlukan."},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["payment_status"] == "CANCELLED"
        with psycopg.connect(database_url) as connection:
            committed = connection.execute(
                "SELECT committed_amount FROM finance.budgets WHERE budget_id = %s",
                (budget_id,),
            ).fetchone()[0]
            assert committed == Decimal("0.00")
    finally:
        _cleanup(database_url, created)


def _create_finance_user(client: TestClient, headers: dict[str, str], label: str) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"finance-{label}-{uuid4().hex[:8]}@example.test",
            "display_name": f"Finance {label.title()} Sintetis",
            "division_code": "FINANCE",
            "role": "FINANCE",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def _create_organization_user(
    client: TestClient, headers: dict[str, str], role: str, display_name: str
) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"{role.lower()}-{uuid4().hex[:8]}@example.test",
            "display_name": display_name,
            "division_code": None,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user_id"]


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
        payment_records = [created, *created.get("extra_payments", [])]
        for payment_record in payment_records:
            payment_id = payment_record.get("payment_request_id")
            workflow_id = payment_record.get("workflow_run_id")
            work_item_id = payment_record.get("work_item_id")
            approval_id = payment_record.get("approval_request_id")
            if payment_id:
                connection.execute(
                    "DELETE FROM finance.reconciliations WHERE payment_request_id = %s",
                    (payment_id,),
                )
                connection.execute(
                    "DELETE FROM finance.payment_records WHERE payment_request_id = %s",
                    (payment_id,),
                )
                connection.execute(
                    "DELETE FROM finance.payment_requests WHERE payment_request_id = %s",
                    (payment_id,),
                )
                connection.execute(
                    "DELETE FROM platform.command_receipts WHERE entity_type = 'payment_request' "
                    "AND entity_id = %s",
                    (payment_id,),
                )
            if approval_id:
                connection.execute(
                    "DELETE FROM governance.approval_decisions WHERE approval_request_id = %s",
                    (approval_id,),
                )
                connection.execute(
                    "DELETE FROM governance.approval_requests WHERE approval_request_id = %s",
                    (approval_id,),
                )
            if workflow_id:
                for table in ("workflow.transition_events", "agents.agent_runs"):
                    connection.execute(
                        f"DELETE FROM {table} WHERE workflow_run_id = %s", (workflow_id,)
                    )  # noqa: S608
                connection.execute(
                    "DELETE FROM workflow.workflow_runs WHERE workflow_run_id = %s",
                    (workflow_id,),
                )
            if work_item_id:
                connection.execute(
                    "DELETE FROM governance.approval_decisions WHERE approval_request_id IN "
                    "(SELECT approval_request_id FROM governance.approval_requests "
                    "WHERE work_item_id = %s)",
                    (work_item_id,),
                )
                connection.execute(
                    "DELETE FROM governance.approval_requests WHERE work_item_id = %s",
                    (work_item_id,),
                )
                connection.execute(
                    "DELETE FROM platform.evidence WHERE work_item_id = %s", (work_item_id,)
                )
                connection.execute(
                    "DELETE FROM governance.exceptions WHERE work_item_id = %s", (work_item_id,)
                )
                connection.execute(
                    "DELETE FROM platform.work_items WHERE work_item_id = %s", (work_item_id,)
                )
        if created.get("document_version_id"):
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_version_id = %s",
                (created["document_version_id"],),
            )
        if created.get("document_id"):
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s", (created["document_id"],)
            )
        if created.get("budget_id"):
            connection.execute(
                "DELETE FROM finance.budgets WHERE budget_id = %s", (created["budget_id"],)
            )
        entity_ids = [str(value) for key, value in created.items() if key.endswith("_id") and value]
        entity_ids.extend(
            str(value)
            for payment_record in created.get("extra_payments", [])
            for key, value in payment_record.items()
            if key.endswith("_id") and value
        )
        if created.get("project_id"):
            connection.execute(
                "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
            )
        for user_id in created.get("user_ids", []):
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))

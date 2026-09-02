import hashlib
import os
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.entrypoints.document_api import document_storage
from alos.main import app
from alos.persistence.migrations import psycopg_url
from alos.platform.documents import FilesystemObjectStorage

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_document_upload_version_download_and_scope(tmp_path) -> None:
    database_url = psycopg_url(get_settings().database_url)
    project_id = uuid4()
    created: dict[str, Any] = {"project_id": project_id, "object_keys": []}
    storage = FilesystemObjectStorage(tmp_path, "test-documents")
    app.dependency_overrides[document_storage] = lambda: storage

    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO platform.projects
                (project_id, organization_id, code, name, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'Document Storage Pilot', 'ACTIVE', now(), now())
            """,
            (project_id, organization_id, f"DOC-{uuid4().hex[:8].upper()}"),
        )

    client = TestClient(app)
    finance_headers = _headers(
        client, organization_id, ["FINANCE"], ["FINANCE"], [project_id]
    )
    sales_headers = _headers(
        client,
        organization_id,
        ["SALES"],
        ["SALES_MARKETING"],
        [project_id],
    )
    it_headers = _headers(client, organization_id, ["IT_ADMIN"], ["IT"])
    director_headers = _headers(client, organization_id, ["DIRECTOR"], [])
    ai_headers = _headers(client, organization_id, ["AI_EXECUTIVE"], [])
    first_payload = b"%PDF-1.7\nsynthetic-finance-evidence-v1"
    second_payload = b"%PDF-1.7\nsynthetic-finance-evidence-v2"

    try:
        upload = client.post(
            "/api/v1/documents/upload",
            headers=finance_headers,
            data={
                "logical_name": "Bukti Pembayaran Sintetis",
                "classification": "RESTRICTED",
                "division_code": "FINANCE",
                "project_id": str(project_id),
            },
            files={"file": ("bukti-v1.pdf", first_payload, "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        document = upload.json()
        document_id = UUID(document["document_id"])
        created["document_id"] = document_id
        created["document_ids"] = [document_id]
        assert document["version_number"] == 1
        assert document["sha256"] == hashlib.sha256(first_payload).hexdigest()
        assert "object_key" not in document

        duplicate_version = client.post(
            f"/api/v1/documents/{document_id}/versions",
            headers=finance_headers,
            files={"file": ("bukti-v1-copy.pdf", first_payload, "application/pdf")},
        )
        assert duplicate_version.status_code == 409

        new_version = client.post(
            f"/api/v1/documents/{document_id}/versions",
            headers=finance_headers,
            files={"file": ("bukti-v2.pdf", second_payload, "application/pdf")},
        )
        assert new_version.status_code == 201, new_version.text
        assert new_version.json()["version_number"] == 2

        shared_upload = client.post(
            "/api/v1/documents/upload",
            headers=director_headers,
            data={
                "logical_name": "Dokumen Bersama Rahasia",
                "classification": "CONFIDENTIAL",
                "project_id": str(project_id),
            },
            files={
                "file": ("shared-confidential.pdf", first_payload, "application/pdf")
            },
        )
        assert shared_upload.status_code == 201, shared_upload.text
        shared_document_id = UUID(shared_upload.json()["document_id"])
        created["document_ids"].append(shared_document_id)

        latest = client.get(
            f"/api/v1/documents/{document_id}/content", headers=finance_headers
        )
        assert latest.status_code == 200, latest.text
        assert latest.content == second_payload
        assert latest.headers["x-document-version"] == "2"
        assert latest.headers["x-content-sha256"] == hashlib.sha256(second_payload).hexdigest()

        first = client.get(
            f"/api/v1/documents/{document_id}/content",
            headers=director_headers,
            params={"version_number": 1},
        )
        assert first.status_code == 200
        assert first.content == first_payload

        assert (
            client.get(
                f"/api/v1/documents/{document_id}/content", headers=sales_headers
            ).status_code
            == 403
        )
        assert (
            client.get(f"/api/v1/documents/{document_id}/content", headers=it_headers).status_code
            == 403
        )
        assert (
            client.get(f"/api/v1/documents/{document_id}/content", headers=ai_headers).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/v1/documents/{shared_document_id}/content",
                headers=finance_headers,
            ).status_code
            == 403
        )

        finance_list = client.get(
            "/api/v1/documents", headers=finance_headers, params={"project_id": project_id}
        )
        assert finance_list.status_code == 200
        assert finance_list.json()["total"] == 1
        assert finance_list.json()["items"][0]["version_number"] == 2
        sales_list = client.get(
            "/api/v1/documents", headers=sales_headers, params={"project_id": project_id}
        )
        assert sales_list.status_code == 200
        assert sales_list.json()["total"] == 0
        ai_list = client.get("/api/v1/documents", headers=ai_headers)
        assert ai_list.status_code == 200
        assert all(item["document_id"] != str(document_id) for item in ai_list.json()["items"])

        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                SELECT object_key, scan_status, storage_provider
                FROM platform.document_versions
                WHERE document_id = %s ORDER BY version_number
                """,
                (document_id,),
            ).fetchall()
            created["object_keys"] = [row[0] for row in rows]
            assert [(row[1], row[2]) for row in rows] == [
                ("NOT_CONFIGURED", "FILESYSTEM"),
                ("NOT_CONFIGURED", "FILESYSTEM"),
            ]
            audit_actions = {
                row[0]
                for row in connection.execute(
                    "SELECT action FROM audit.entries WHERE entity_id = %s", (str(document_id),)
                ).fetchall()
            }
            assert {
                "document.uploaded",
                "document.version_uploaded",
                "document.downloaded",
            }.issubset(audit_actions)
            shared_object_key = connection.execute(
                "SELECT object_key FROM platform.document_versions WHERE document_id = %s",
                (shared_document_id,),
            ).fetchone()[0]
            created["object_keys"].append(shared_object_key)
    finally:
        app.dependency_overrides.pop(document_storage, None)
        _cleanup(database_url, created, storage)


def _headers(
    client: TestClient,
    organization_id: object,
    roles: list[str],
    divisions: list[str],
    projects: list[object] | None = None,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(organization_id),
            "roles": roles,
            "division_codes": divisions,
            "project_ids": [str(project) for project in projects or []],
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cleanup(
    database_url: str,
    created: dict[str, Any],
    storage: FilesystemObjectStorage,
) -> None:
    for object_key in created.get("object_keys", []):
        storage.delete(object_key)
    with psycopg.connect(database_url) as connection:
        for document_id in created.get("document_ids", []):
            connection.execute(
                "DELETE FROM platform.document_versions WHERE document_id = %s", (document_id,)
            )
            connection.execute(
                "DELETE FROM platform.documents WHERE document_id = %s", (document_id,)
            )
        connection.execute(
            "DELETE FROM platform.projects WHERE project_id = %s", (created["project_id"],)
        )

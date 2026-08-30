import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import errors

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


def test_genesis_release_package_is_audited_immutable_and_not_deployed() -> None:
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url) as connection:
        organization_id = connection.execute(
            "SELECT organization_id FROM identity.organizations WHERE code = 'ARM'"
        ).fetchone()[0]
    client = TestClient(app)
    bootstrap = _headers(client, organization_id, uuid4(), ["IT_ADMIN"], ["IT"])
    users: list[str] = []
    request_id: str | None = None
    try:
        requester = _create_user(client, bootstrap, "AI_EXECUTIVE", None)
        business = _create_user(client, bootstrap, "DIRECTOR", None)
        technical = _create_user(client, bootstrap, "IT_ADMIN", "IT")
        releaser = _create_user(client, bootstrap, "DIRECTOR", None)
        users.extend((requester, business, technical, releaser))

        submitted = client.post(
            "/api/v1/genesis/requests",
            headers=_headers(client, organization_id, requester, ["AI_EXECUTIVE"], []),
            json={
                "strategy": "REUSE",
                "justification": "Menggunakan BCA untuk pengujian release package Genesis.",
                "source_references": ["specification:genesis-postgres-test"],
                "target": {"agent_id": "BCA", "version": "0.1.0"},
            },
        )
        assert submitted.status_code == 201, submitted.text
        request_id = submitted.json()["request_id"]

        for gate, reviewer, role, division in (
            ("BUSINESS", business, "DIRECTOR", []),
            ("TECHNICAL", technical, "IT_ADMIN", ["IT"]),
        ):
            reviewed = client.post(
                f"/api/v1/genesis/requests/{request_id}/reviews",
                headers=_headers(client, organization_id, reviewer, [role], division),
                json={
                    "gate": gate,
                    "decision": "APPROVED",
                    "notes": f"Gate {gate} telah diperiksa dengan data sintetis.",
                },
            )
            assert reviewed.status_code == 200, reviewed.text

        staged = client.post(
            f"/api/v1/genesis/requests/{request_id}/stage",
            headers=_headers(client, organization_id, technical, ["IT_ADMIN"], ["IT"]),
        )
        assert staged.status_code == 200, staged.text
        released = client.post(
            f"/api/v1/genesis/requests/{request_id}/release",
            headers=_headers(client, organization_id, releaser, ["DIRECTOR"], []),
        )
        assert released.status_code == 200, released.text
        body = released.json()
        assert body["status"] == "RELEASED"
        assert body["production_effect"] is False
        assert body["next_allowed_action"] == "SEPARATE_DEPLOYMENT_APPROVAL"

        with psycopg.connect(database_url) as connection:
            production_effect, event_count = connection.execute(
                """
                SELECT rp.production_effect,
                       (SELECT count(*) FROM genesis.stage_events se
                        WHERE se.request_id = rp.request_id)
                FROM genesis.release_packages rp WHERE rp.request_id = %s
                """,
                (request_id,),
            ).fetchone()
            assert production_effect is False
            assert event_count == 10
        with (
            psycopg.connect(database_url, autocommit=True) as connection,
            pytest.raises(errors.RaiseException, match="immutable"),
        ):
            connection.execute(
                """
                UPDATE genesis.release_packages
                SET contract_snapshot = jsonb_set(
                    contract_snapshot, '{purpose}', '"tampered"'::jsonb
                )
                WHERE request_id = %s
                """,
                (request_id,),
            )
    finally:
        with psycopg.connect(database_url) as connection:
            if request_id:
                connection.execute(
                    "DELETE FROM genesis.stage_events WHERE request_id = %s", (request_id,)
                )
                connection.execute(
                    "DELETE FROM genesis.reviews WHERE request_id = %s", (request_id,)
                )
                connection.execute(
                    "DELETE FROM genesis.release_packages WHERE request_id = %s", (request_id,)
                )
                connection.execute(
                    "DELETE FROM genesis.change_requests WHERE request_id = %s", (request_id,)
                )
            if users:
                connection.execute(
                    "DELETE FROM identity.role_assignments WHERE user_id = ANY(%s::uuid[])",
                    (users,),
                )
                connection.execute(
                    "DELETE FROM identity.users WHERE user_id = ANY(%s::uuid[])", (users,)
                )


def _create_user(
    client: TestClient,
    headers: dict[str, str],
    role: str,
    division_code: str | None,
) -> str:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"genesis-{uuid4().hex[:12]}@example.test",
            "display_name": f"Genesis {role} Synthetic",
            "division_code": division_code,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user_id"]


def _headers(
    client: TestClient,
    organization_id: object,
    user_id: object,
    roles: list[str],
    divisions: list[str],
) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

from uuid import uuid4

from fastapi.testclient import TestClient

from alos.main import app


def test_health_returns_platform_identity() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "alos"


def test_local_token_carries_human_scope() -> None:
    client = TestClient(app)
    token_response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["IT_LEAD"],
            "division_codes": ["IT"],
            "workspace_ids": [str(uuid4())],
        },
    )
    assert token_response.status_code == 200
    response = client.get(
        "/api/v1/whoami",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["roles"] == ["IT_LEAD"]
    assert response.json()["division_codes"] == ["IT"]


def test_whoami_requires_a_bearer_token() -> None:
    assert TestClient(app).get("/api/v1/whoami").status_code == 401

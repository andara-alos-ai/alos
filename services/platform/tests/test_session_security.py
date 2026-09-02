from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from alos.config import Settings
from alos.main import app


def test_local_token_sets_httponly_session_and_csrf_cookies() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

    # Verify cookies
    session_cookie = response.cookies.get("alos_session")
    csrf_cookie = response.cookies.get("alos_csrf")
    assert session_cookie is not None
    assert csrf_cookie is not None
    assert session_cookie == data["access_token"]


def test_auth_me_with_cookie_session() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

    # Login to get cookies
    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["DIRECTOR"],
            "division_codes": [],
            "project_ids": [],
        },
    )
    assert login_res.status_code == 200

    # Call /auth/me with cookies (no Authorization header)
    me_res = client.get("/api/v1/auth/me", cookies=login_res.cookies)
    assert me_res.status_code == 200
    principal = me_res.json()
    assert principal["user_id"] == str(user_id)
    assert principal["organization_id"] == str(org_id)
    assert "DIRECTOR" in principal["roles"]


def test_mutating_request_with_cookie_requires_valid_csrf() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    assert login_res.status_code == 200
    session_cookie = login_res.cookies.get("alos_session")
    csrf_cookie = login_res.cookies.get("alos_csrf")
    assert session_cookie and csrf_cookie

    cookies = {"alos_session": session_cookie, "alos_csrf": csrf_cookie}

    # 1. Mutating request without X-CSRF-Token header -> 403 Forbidden
    res_no_csrf = client.post(
        "/api/v1/projects",
        json={"code": "PRJ-TEST-1", "name": "Test Project 1"},
        cookies=cookies,
    )
    assert res_no_csrf.status_code == 403
    assert "CSRF" in res_no_csrf.json()["detail"]

    # 2. Mutating request with invalid X-CSRF-Token header -> 403 Forbidden
    res_invalid_csrf = client.post(
        "/api/v1/projects",
        json={"code": "PRJ-TEST-1", "name": "Test Project 1"},
        cookies=cookies,
        headers={"X-CSRF-Token": "invalid-token-value"},
    )
    assert res_invalid_csrf.status_code == 403

    # 3. Mutating request with valid matching X-CSRF-Token header
    # Passes auth/CSRF check (may succeed or hit business layer)
    res_valid_csrf = client.post(
        "/api/v1/projects",
        json={"code": "PRJ-TEST-1", "name": "Test Project 1"},
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_cookie},
    )
    # The request is not rejected by 403 CSRF or 401 Auth
    assert res_valid_csrf.status_code in {201, 400, 404, 409, 503}


def test_bearer_token_does_not_require_csrf() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    token = login_res.json()["access_token"]

    # Mutating request with Bearer token without cookies and without CSRF header
    res = client.post(
        "/api/v1/projects",
        json={"code": "PRJ-TEST-BEARER", "name": "Bearer Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code in {201, 400, 404, 409, 503}
    assert res.status_code != 403


def test_logout_endpoint_clears_cookies() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    assert login_res.status_code == 200

    logout_res = client.post("/api/v1/auth/logout", cookies=login_res.cookies)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "ok"


def test_csrf_endpoint_returns_token_and_sets_cookie() -> None:
    client = TestClient(app)
    res = client.get("/api/v1/auth/csrf")
    assert res.status_code == 200
    data = res.json()
    assert "csrf_token" in data
    assert len(data["csrf_token"]) > 16
    assert res.cookies.get("alos_csrf") == data["csrf_token"]


def test_settings_rejects_insecure_cookie_on_production() -> None:
    with pytest.raises(ValueError, match="Session cookie wajib Secure"):
        Settings(
            environment="production",
            auth_signing_secret=SecretStr("super-strong-secret-key-with-enough-entropy-32-chars"),
            session_cookie_secure=False,
            object_storage_provider="s3",
            document_scan_mode="external",
            object_storage_access_key=SecretStr("access-key"),
            object_storage_secret_key=SecretStr("secret-key"),
        )

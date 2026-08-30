from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from alos.config import Settings, get_settings
from alos.entrypoints.oidc_api import oidc_service, router
from alos.platform.identity.oidc import OIDCLoginAttempt
from alos.security import Principal, Role, TokenCodec


class FakeOIDCLoginService:
    def __init__(self) -> None:
        self.principal = Principal(
            user_id=uuid4(),
            organization_id=uuid4(),
            roles=frozenset({Role.IT_ADMIN}),
            division_codes=frozenset({"IT"}),
        )
        self.completed = False

    def begin_login(self) -> OIDCLoginAttempt:
        return OIDCLoginAttempt(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth?state=test-state",
            state="test-state",
            max_age_seconds=600,
        )

    async def complete_login(self, *, code: str, state: str) -> str:
        assert code == "google-authorization-code"
        assert state == "test-state"
        self.completed = True
        return "x" * 43

    def exchange_login_code(self, code: str) -> Principal:
        assert code == "x" * 43
        return self.principal


def _client() -> tuple[TestClient, FakeOIDCLoginService, Settings]:
    settings = Settings(
        oidc_provider="google",
        oidc_client_id="client.apps.googleusercontent.com",
        oidc_client_secret="synthetic-client-secret",
    )
    service = FakeOIDCLoginService()
    application = FastAPI()
    application.include_router(router, prefix=settings.api_prefix)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[oidc_service] = lambda: service
    return TestClient(application), service, settings


def test_oidc_browser_flow_uses_http_only_state_and_one_time_code() -> None:
    client, service, settings = _client()

    login = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert login.status_code == 302
    assert login.headers["location"].startswith("https://accounts.google.com/")
    cookie = login.headers["set-cookie"]
    assert "alos_oidc_state=test-state" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    callback = client.get(
        "/api/v1/auth/oidc/callback/google",
        params={"code": "google-authorization-code", "state": "test-state"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:3000/login#oidc_code=" + "x" * 43
    assert service.completed is True

    exchange = client.post("/api/v1/auth/oidc/exchange", json={"code": "x" * 43})
    assert exchange.status_code == 200
    token = exchange.json()["access_token"]
    verified = TokenCodec(
        settings.auth_signing_secret.get_secret_value(),
        settings.auth_issuer,
        settings.auth_audience,
    ).verify(token)
    assert verified == service.principal
    assert exchange.headers["cache-control"] == "no-store"


def test_oidc_callback_rejects_state_mismatch_before_provider_exchange() -> None:
    client, service, _ = _client()
    client.get("/api/v1/auth/oidc/login", follow_redirects=False)

    callback = client.get(
        "/api/v1/auth/oidc/callback/google",
        params={"code": "google-authorization-code", "state": "attacker-state"},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"].endswith("#oidc_error=invalid_state")
    assert service.completed is False

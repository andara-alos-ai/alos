from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from alos.security.response_headers import SecurityHeadersMiddleware


def test_security_headers_are_applied_without_overwriting_endpoint_policy() -> None:
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware, hsts_enabled=False)

    @application.get("/example")
    def example() -> Response:
        return Response(content="ok", headers={"Cache-Control": "private, max-age=60"})

    response = TestClient(application).get("/example")

    assert response.headers["cache-control"] == "private, max-age=60"
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )
    assert response.headers["cross-origin-resource-policy"] == "same-site"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers


def test_hsts_is_enabled_only_when_requested() -> None:
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware, hsts_enabled=True)

    @application.get("/example")
    def example() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(application).get("/example")

    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert response.headers["cache-control"] == "no-store"

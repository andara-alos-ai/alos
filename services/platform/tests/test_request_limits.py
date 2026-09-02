from fastapi import FastAPI
from fastapi.testclient import TestClient

from alos.security.request_limits import RateLimitMiddleware


def test_rate_limit_rejects_excess_requests_with_retry_header() -> None:
    application = FastAPI()
    application.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=2,
        auth_requests_per_minute=1,
    )

    @application.get("/api/v1/example")
    def example() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(application, client=("198.51.100.10", 50000))
    assert client.get("/api/v1/example").status_code == 200
    assert client.get("/api/v1/example").status_code == 200

    blocked = client.get("/api/v1/example")

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"

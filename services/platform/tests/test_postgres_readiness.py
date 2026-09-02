import os

import pytest
from fastapi.testclient import TestClient

from alos.config import get_settings
from alos.main import app

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_readiness_reports_a_disposable_postgres_database() -> None:
    get_settings.cache_clear()
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}

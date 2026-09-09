from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

import alos.main as main
from alos.identity import HumanRole
from alos.main import app
from alos.portfolio import DivisionsOverviewSnapshot, ProjectPortfolioSnapshot
from alos.security.tokens import ActorContext, get_current_actor


def _actor() -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[uuid4()],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _divisions_snapshot() -> DivisionsOverviewSnapshot:
    return DivisionsOverviewSnapshot.model_validate(
        {
            "generated_at": "2026-09-08T03:24:00Z",
            "divisions": [],
            "comparison": [],
            "issues": [],
            "attention": [],
        }
    )


def _projects_snapshot() -> ProjectPortfolioSnapshot:
    return ProjectPortfolioSnapshot.model_validate(
        {
            "generated_at": "2026-09-08T03:24:00Z",
            "metrics": {
                "total": 0,
                "on_track": 0,
                "at_risk": 0,
                "critical": 0,
                "completed": 0,
            },
            "progress": [],
            "distribution": [],
            "projects": [],
            "milestones": [],
            "risk_summary": [],
            "filter_options": {"divisions": [], "categories": [], "statuses": []},
            "pagination": {"page": 1, "page_size": 20, "total_items": 0, "total_pages": 1},
        }
    )


def test_divisions_overview_uses_actor_scope(monkeypatch) -> None:
    actor = _actor()
    calls: list[dict[str, object]] = []

    class Repository:
        def divisions_overview(self, **kwargs):
            calls.append(kwargs)
            return _divisions_snapshot()

    monkeypatch.setattr(main, "get_portfolio_repository", Repository)
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        response = TestClient(app).get("/api/v1/divisions/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert calls == [
        {"organization_id": actor.organization_id, "workspace_ids": actor.workspace_ids}
    ]


def test_project_portfolio_passes_validated_filters(monkeypatch) -> None:
    actor = _actor()
    calls: list[dict[str, object]] = []

    class Repository:
        def project_portfolio(self, **kwargs):
            calls.append(kwargs)
            return _projects_snapshot()

    monkeypatch.setattr(main, "get_portfolio_repository", Repository)
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        response = TestClient(app).get(
            "/api/v1/projects/portfolio",
            params={
                "division_code": "IT",
                "status": "AT_RISK",
                "category": "Technology",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "search": "ALOS",
                "page": 2,
                "page_size": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls[0]["organization_id"] == actor.organization_id
    assert calls[0]["workspace_ids"] == actor.workspace_ids
    assert calls[0]["division_code"] == "IT"
    assert calls[0]["project_status"] == "AT_RISK"
    assert str(calls[0]["date_from"]) == "2026-01-01"
    assert calls[0]["page"] == 2


def test_project_portfolio_rejects_reversed_date_range(monkeypatch) -> None:
    called = False

    class Repository:
        def project_portfolio(self, **_kwargs):
            nonlocal called
            called = True
            return _projects_snapshot()

    monkeypatch.setattr(main, "get_portfolio_repository", Repository)
    app.dependency_overrides[get_current_actor] = _actor
    try:
        response = TestClient(app).get(
            "/api/v1/projects/portfolio?date_from=2026-12-31&date_to=2026-01-01"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "date_to must be on or after date_from"
    assert called is False

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

import alos.main as main
from alos.executive_dashboard import ExecutiveDashboardSnapshot
from alos.identity import HumanRole
from alos.main import app
from alos.security.tokens import ActorContext, get_current_actor


def dashboard_snapshot() -> ExecutiveDashboardSnapshot:
    return ExecutiveDashboardSnapshot.model_validate(
        {
            "generated_at": "2026-09-08T03:24:00Z",
            "profile": {
                "display_name": "Arief Budiman",
                "organization_name": "PT Andara Rejo Makmur",
            },
            "metrics": [
                {
                    "key": "active_projects",
                    "label": "Total Proyek Aktif",
                    "value": None,
                    "unit": "COUNT",
                    "tone": "SUCCESS",
                    "state": "NOT_CONNECTED",
                    "context": "Sumber proyek belum terhubung",
                },
                {
                    "key": "average_progress",
                    "label": "Progress Rata-rata",
                    "value": None,
                    "unit": "PERCENT",
                    "tone": "WARNING",
                    "state": "NOT_CONNECTED",
                    "context": "Milestone proyek belum terhubung",
                },
                {
                    "key": "overdue_tasks",
                    "label": "Task Overdue",
                    "value": None,
                    "unit": "COUNT",
                    "tone": "DANGER",
                    "state": "NOT_CONNECTED",
                    "context": "Sumber task belum terhubung",
                },
                {
                    "key": "pending_approvals",
                    "label": "Approval Pending",
                    "value": 2,
                    "unit": "COUNT",
                    "tone": "INFO",
                    "state": "LIVE",
                    "context": "Dokumen dan release agent yang menunggu keputusan",
                },
            ],
            "performance": {
                "title": "Rasio keputusan yang disetujui",
                "context": "Berdasarkan review terdaftar.",
                "points": [
                    {
                        "period": "2026-09",
                        "label": "Sep",
                        "value": 65.4,
                        "decision_count": 3,
                    }
                ],
            },
            "project_distribution": {
                "available": False,
                "total": 0,
                "context": "Sumber proyek belum terhubung.",
                "items": [
                    {"key": "COMPLETED", "label": "Selesai", "count": 0, "tone": "BLUE"},
                    {"key": "ON_TRACK", "label": "On Track", "count": 0, "tone": "GREEN"},
                    {"key": "AT_RISK", "label": "At Risk", "count": 0, "tone": "AMBER"},
                    {"key": "CRITICAL", "label": "Critical", "count": 0, "tone": "RED"},
                ],
            },
            "divisions": [],
            "attention_projects": [],
            "pending_approvals": [],
        }
    )


def actor(role: HumanRole) -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[role],
        workspace_ids=[uuid4()],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_director_receives_access_scoped_executive_snapshot(monkeypatch) -> None:
    director = actor(HumanRole.DIRECTOR)
    expected = dashboard_snapshot()
    calls: list[dict[str, object]] = []

    class Repository:
        def snapshot(self, **kwargs):
            calls.append(kwargs)
            return expected

    monkeypatch.setattr(main, "get_executive_dashboard_repository", Repository)
    app.dependency_overrides[get_current_actor] = lambda: director
    try:
        response = TestClient(app).get("/api/v1/executive-dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["profile"]["display_name"] == "Arief Budiman"
    assert response.json()["metrics"][3]["value"] == 2
    assert calls == [
        {
            "organization_id": director.organization_id,
            "actor_user_id": director.user_id,
            "workspace_ids": director.workspace_ids,
        }
    ]


def test_non_director_cannot_read_executive_snapshot(monkeypatch) -> None:
    called = False

    class Repository:
        def snapshot(self, **_kwargs):
            nonlocal called
            called = True
            return dashboard_snapshot()

    monkeypatch.setattr(main, "get_executive_dashboard_repository", Repository)
    app.dependency_overrides[get_current_actor] = lambda: actor(HumanRole.IT_LEAD)
    try:
        response = TestClient(app).get("/api/v1/executive-dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Director authority required for executive dashboard"
    assert called is False

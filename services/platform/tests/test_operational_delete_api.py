from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from alos.entrypoints import operational_api, projects_api
from alos.identity import HumanRole
from alos.main import app
from alos.security.tokens import ActorContext, get_current_actor


def test_dashboard_delete_endpoints_delegate_to_scoped_repository(monkeypatch) -> None:
    calls: list[tuple[str, UUID, UUID]] = []

    class Repository:
        def delete_task(self, _actor, record_id, *, correlation_id) -> None:
            calls.append(("task", record_id, correlation_id))

        def delete_finding(self, _actor, record_id, *, correlation_id) -> None:
            calls.append(("finding", record_id, correlation_id))

        def delete_report_definition(self, _actor, record_id, *, correlation_id) -> None:
            calls.append(("definition", record_id, correlation_id))

        def delete_report(self, _actor, record_id, *, correlation_id) -> None:
            calls.append(("report", record_id, correlation_id))

    class ProjectRepository:
        def delete_project(self, _actor, record_id, correlation_id) -> None:
            calls.append(("project", record_id, correlation_id))

    now = datetime.now(UTC)
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[uuid4()],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    monkeypatch.setattr(operational_api, "get_operational_repository", Repository)
    monkeypatch.setattr(projects_api, "repository", ProjectRepository)
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        client = TestClient(app)
        expected = [
            ("task", f"/api/v1/tasks/{uuid4()}"),
            ("finding", f"/api/v1/findings/{uuid4()}"),
            ("definition", f"/api/v1/report-definitions/{uuid4()}"),
            ("report", f"/api/v1/reports/{uuid4()}"),
            ("project", f"/api/v1/projects/{uuid4()}"),
        ]
        for kind, path in expected:
            response = client.delete(path)
            assert response.status_code == 204
            assert calls[-1][0] == kind
    finally:
        app.dependency_overrides.clear()

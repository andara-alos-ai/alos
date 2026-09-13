from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

import alos.main as main
from alos.entrypoints.genesis_factory_api import get_genesis_factory_service
from alos.genesis.factory.persistence import (
    FactoryRequestPage,
    FactoryRequestRecord,
    FactoryStatus,
)
from alos.identity import DataScope, HumanRole
from alos.security.tokens import ActorContext, get_current_actor


def _actor(workspace_id, organization_id, user_id):
    now = datetime.now(UTC)
    return ActorContext(
        user_id=user_id,
        organization_id=organization_id,
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[workspace_id],
        data_scope=DataScope.COMPANY,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _record(workspace_id, organization_id, user_id):
    now = datetime.now(UTC)
    return FactoryRequestRecord(
        factory_request_id=uuid4(),
        organization_id=organization_id,
        workspace_id=workspace_id,
        division_id=None,
        project_id=None,
        tenant_id=None,
        requirement="Analyze records every day and prepare governed owner tasks.",
        source_type="DIRECT",
        source_research_id=None,
        status=FactoryStatus.REQUEST,
        requirement_understanding=None,
        implementation_decision=None,
        dependency_resolution=None,
        factory_proposal=None,
        blockers=[],
        agent_contract_id=None,
        agent_version_id=None,
        release_change_request_id=None,
        requested_by_user_id=user_id,
        owner_user_id=user_id,
        reviewer_user_id=None,
        idempotency_key="api-test",
        correlation_id=uuid4(),
        last_error_code=None,
        created_at=now,
        analyzed_at=None,
        updated_at=now,
    )


class Service:
    def __init__(self, record):
        self.record = record

    def create(self, request, actor, *, correlation_id):
        return self.record

    def get(self, request_id, actor):
        return self.record

    def list_requests(self, actor, **kwargs):
        return FactoryRequestPage(
            items=[self.record], limit=kwargs["limit"], offset=kwargs["offset"], has_more=False
        )

    def analyze(self, request_id, actor, **kwargs):
        return self.record.model_copy(update={"status": FactoryStatus.DRAFT})


def test_factory_api_is_authenticated_typed_and_paginated() -> None:
    workspace_id, organization_id, user_id = uuid4(), uuid4(), uuid4()
    actor = _actor(workspace_id, organization_id, user_id)
    record = _record(workspace_id, organization_id, user_id)
    service = Service(record)
    main.app.dependency_overrides[get_current_actor] = lambda: actor
    main.app.dependency_overrides[get_genesis_factory_service] = lambda: service
    try:
        client = TestClient(main.app)
        created = client.post(
            "/api/v1/genesis/factory/requests",
            json={
                "workspace_id": str(workspace_id),
                "requirement": record.requirement,
                "idempotency_key": "api-test",
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "REQUEST"

        listed = client.get(
            f"/api/v1/genesis/factory/requests?workspace_id={workspace_id}&limit=10"
        )
        assert listed.status_code == 200
        assert listed.json()["limit"] == 10
        assert listed.json()["has_more"] is False

        fetched = client.get(
            f"/api/v1/genesis/factory/requests/{record.factory_request_id}"
        )
        assert fetched.status_code == 200

        analyzed = client.post(
            f"/api/v1/genesis/factory/requests/{record.factory_request_id}/analyze",
            json={"agent_key": "GENERIC_DAILY_REVIEW"},
        )
        assert analyzed.status_code == 200
        assert analyzed.json()["status"] == "DRAFT"
    finally:
        main.app.dependency_overrides.clear()


def test_factory_api_rejects_unauthenticated_request() -> None:
    workspace_id, organization_id, user_id = uuid4(), uuid4(), uuid4()
    service = Service(_record(workspace_id, organization_id, user_id))
    main.app.dependency_overrides[get_genesis_factory_service] = lambda: service
    try:
        response = TestClient(main.app).get("/api/v1/genesis/factory/requests")
        assert response.status_code == 401
    finally:
        main.app.dependency_overrides.clear()

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.genesis.governed_foundations import Scope, SkillStatus
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.security.tokens import ActorContext
from alos.skills import SkillDraftRequest, SkillRegistry
from alos.skills.repository import SkillConflictError, SkillNotFoundError

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _actor(context, tenant_id):
    now = datetime.now(UTC)
    return ActorContext(
        user_id=context.user_id,
        organization_id=context.organization_id,
        roles=[HumanRole.IT_LEAD],
        division_codes=[DivisionCode.IT],
        workspace_ids=[context.workspace_id],
        tenant_ids=[tenant_id],
        data_scope=DataScope.DIVISION,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_skill_lifecycle_is_persistent_active_only_and_tenant_scoped() -> None:
    from alos.config import get_settings

    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_skills_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, root / "infra" / "database")
        context = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        tenant_a, tenant_b = uuid4(), uuid4()
        actor_a, actor_b = _actor(context, tenant_a), _actor(context, tenant_b)
        scope = Scope(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            tenant_id=tenant_a,
        )
        registry = SkillRegistry(temporary_url)
        skill = registry.create_draft(
            SkillDraftRequest(
                scope=scope,
                skill_key="records.verify",
                name="Verify Records",
                semantic_version="1.0.0",
                procedure={"steps": [{"type": "TOOL", "tool_key": "records.verify"}]},
                required_permissions=("records.verify",),
            ),
            actor_a,
            correlation_id=uuid4(),
        )
        with pytest.raises(SkillConflictError):
            registry.transition(
                skill.skill_id,
                "1.0.0",
                SkillStatus.ACTIVE,
                actor_a,
                correlation_id=uuid4(),
            )
        for target in (
            SkillStatus.TEST,
            SkillStatus.REVIEW,
            SkillStatus.APPROVED,
            SkillStatus.ACTIVE,
        ):
            skill = registry.transition(
                skill.skill_id,
                "1.0.0",
                target,
                actor_a,
                correlation_id=uuid4(),
            )
        active = SkillRegistry(temporary_url).resolve_active(
            "records.verify", scope, actor_a
        )
        assert active.status == SkillStatus.ACTIVE
        assert active.semantic_version == "1.0.0"
        assert active.activated_at is not None

        other_scope = scope.model_copy(update={"tenant_id": tenant_b})
        with pytest.raises((HTTPException, SkillNotFoundError)):
            registry.resolve_active("records.verify", other_scope, actor_b)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))

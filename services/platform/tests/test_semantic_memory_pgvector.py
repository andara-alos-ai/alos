import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.genesis.governed_foundations import MemoryKind, Scope
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.memory import (
    EmbeddingResponse,
    MemoryCreateRequest,
    MemoryNotFoundError,
    MemoryRepository,
    SemanticMemoryQuery,
)
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.security.tokens import ActorContext

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


class FakeEmbeddingGateway:
    def embed(self, request):
        vector = (1.0, 0.0, 0.0) if "finance" in request.text.casefold() else (0.0, 1.0, 0.0)
        return EmbeddingResponse(provider="test", model="fixture-v1", vector=vector)


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


def test_semantic_memory_filters_tenant_before_pgvector_ranking() -> None:
    from alos.config import get_settings

    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_memory_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        context = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        tenant_a, tenant_b = uuid4(), uuid4()
        actor_a, actor_b = _actor(context, tenant_a), _actor(context, tenant_b)
        memory = MemoryRepository(temporary_url, FakeEmbeddingGateway())
        expires = datetime.now(UTC) + timedelta(days=1)
        scope_a = Scope(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            tenant_id=tenant_a,
        )
        scope_b = scope_a.model_copy(update={"tenant_id": tenant_b})

        finance_a = memory.create(
            MemoryCreateRequest(
                kind=MemoryKind.PROJECT,
                scope=scope_a,
                content="Finance approval evidence for tenant A.",
                source_reference="source://tenant-a/finance",
                lineage={"source_type": "TEST"},
                retention_until=expires,
                idempotency_key="tenant-a-finance",
            ),
            actor_a,
            correlation_id=uuid4(),
        )
        memory.create(
            MemoryCreateRequest(
                kind=MemoryKind.PROJECT,
                scope=scope_b,
                content="Finance approval evidence for tenant B.",
                source_reference="source://tenant-b/finance",
                lineage={"source_type": "TEST"},
                retention_until=expires,
                idempotency_key="tenant-b-finance",
            ),
            actor_b,
            correlation_id=uuid4(),
        )

        results = memory.semantic_search(
            SemanticMemoryQuery(scope=scope_a, query="finance approval evidence"),
            actor_a,
            correlation_id=uuid4(),
        )
        assert [item.memory.memory_id for item in results] == [finance_a.memory_id]
        assert results[0].memory.content_trust == "UNTRUSTED"

        with pytest.raises((HTTPException, MemoryNotFoundError)):
            memory.semantic_search(
                SemanticMemoryQuery(scope=scope_b, query="finance approval evidence"),
                actor_a,
                correlation_id=uuid4(),
            )

        expired = memory.expire(finance_a.memory_id, actor_a, correlation_id=uuid4())
        assert expired.expired_at is not None
        assert memory.semantic_search(
            SemanticMemoryQuery(scope=scope_a, query="finance approval evidence"),
            actor_a,
            correlation_id=uuid4(),
        ) == []
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))

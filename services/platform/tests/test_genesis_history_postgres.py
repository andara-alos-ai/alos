import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.audit.reader import AuditReader
from alos.config import get_settings
from alos.genesis.history import (
    GenesisConversationRequest,
    GenesisHistoryRepository,
    GenesisMessageRequest,
)
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_genesis_history_preserves_human_requirement_and_system_artifacts() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_genesis_history_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        history = GenesisHistoryRepository(temporary_url)
        conversation = history.create_conversation(
            GenesisConversationRequest(workspace_id=context.workspace_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        message = history.add_human_message(
            conversation.conversation_id,
            GenesisMessageRequest(content="Please research a read-only daily property brief."),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        requirement = history.record_requirement(
            conversation.conversation_id,
            "Create a low-risk read-only daily property brief with verified citations.",
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        blueprint = history.record_system_artifact(
            conversation.conversation_id,
            "BLUEPRINT",
            {"agent_key": "PROPERTY_BRIEF", "risk_level": "LOW"},
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        contract = history.record_system_artifact(
            conversation.conversation_id,
            "CONTRACT",
            {"agent_key": "PROPERTY_BRIEF", "approval_required": True},
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        assert message.actor_kind == "HUMAN"
        assert requirement.status == "DRAFT"
        assert blueprint.version == contract.version == 1
        assert [message.content for message in history.list_messages(
            conversation.conversation_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )] == [
            "Please research a read-only daily property brief.",
            "Create a low-risk read-only daily property brief with verified citations.",
        ]
        assert {artifact.artifact_type for artifact in history.list_artifacts(
            conversation.conversation_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )} == {"BLUEPRINT", "CONTRACT"}
        events = AuditReader(temporary_url).list_events(context.organization_id)
        assert {event.action for event in events}.issuperset(
            {
                "GENESIS_CONVERSATION_CREATED",
                "GENESIS_MESSAGE_RECORDED",
                "GENESIS_REQUIREMENT_RECORDED",
                "GENESIS_ARTIFACT_RECORDED",
            }
        )
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))

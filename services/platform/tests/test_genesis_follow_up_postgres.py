import os
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.audit.reader import AuditReader
from alos.config import Settings, get_settings
from alos.documents.center import (
    ChecklistCompletionRequest,
    DocumentCenterRepository,
    DocumentDraftRequest,
    DocumentReviewDecisionRequest,
)
from alos.genesis.document_analysis import (
    GenesisDocumentAnalysisRequest,
    GenesisDocumentAnalysisService,
)
from alos.genesis.document_workflow import (
    GenesisDocumentResearchRequest,
    GenesisDocumentWorkflowRepository,
)
from alos.genesis.follow_up import (
    GenesisFollowUpBlocked,
    GenesisFollowUpFailed,
    GenesisFollowUpRepository,
    GenesisFollowUpRequest,
    GenesisFollowUpService,
)
from alos.genesis.history import GenesisHistoryRepository
from alos.model_gateway import FakeModelGateway, ModelGateway, ModelResponse, ModelUsage
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_follow_up_persists_two_way_history_and_is_idempotent() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_genesis_follow_up_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        bootstrap = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        checker_id = _add_workspace_user(
            temporary_url,
            bootstrap.organization_id,
            bootstrap.workspace_id,
            "follow-up-checker@example.test",
            "BUSINESS_REVIEWER",
        )
        director_id = _add_workspace_user(
            temporary_url,
            bootstrap.organization_id,
            bootstrap.workspace_id,
            "follow-up-director@example.test",
            "DIRECTOR",
        )
        documents = DocumentCenterRepository(temporary_url)
        source = documents.create_draft(
            DocumentDraftRequest(
                workspace_id=bootstrap.workspace_id,
                title="SOP Tindak Lanjut Genesis",
                content="Owner belum ditetapkan.\nKPI operasional sudah tersedia.",
            ),
            organization_id=bootstrap.organization_id,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
        )
        for check_key in ("SOURCE_EVIDENCE", "SCOPE_OWNER", "RISK_CLASSIFICATION"):
            documents.complete_checklist_item(
                source.document_id,
                check_key,
                ChecklistCompletionRequest(notes=f"Checked {check_key}."),
                organization_id=bootstrap.organization_id,
                actor_user_id=checker_id,
                correlation_id=uuid4(),
            )
        documents.submit_for_review(
            source.document_id,
            organization_id=bootstrap.organization_id,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
        )
        approved = documents.decide_review(
            source.document_id,
            DocumentReviewDecisionRequest(notes="Approved for Genesis follow-up."),
            approved=True,
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
            correlation_id=uuid4(),
        )
        history = GenesisHistoryRepository(temporary_url)
        workflows = GenesisDocumentWorkflowRepository(temporary_url)
        analysis_service = GenesisDocumentAnalysisService(documents, history, workflows)
        analysis = analysis_service.create_analysis(
            GenesisDocumentAnalysisRequest(
                workspace_id=bootstrap.workspace_id,
                source_document_id=source.document_id,
                prompt="Analisa dokumen ini dan jelaskan kekurangan owner serta KPI-nya.",
            ),
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
            correlation_id=uuid4(),
        )
        settings = _settings(temporary_url)
        gateway = FakeModelGateway([_model_response(), _invalid_model_response()])
        follow_ups = GenesisFollowUpService(
            settings,
            GenesisFollowUpRepository(temporary_url, settings),
            _factory_for(gateway),
        )
        correlation_id = uuid4()
        request = GenesisFollowUpRequest(
            correlation_id=correlation_id,
            content="Saya setuju owner diprioritaskan. Apa persiapan berikutnya?",
        )

        first = follow_ups.follow_up(
            analysis.conversation.conversation_id,
            request,
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
        )
        replay = follow_ups.follow_up(
            analysis.conversation.conversation_id,
            request,
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
        )

        assert first.human_message.actor_kind == "HUMAN"
        assert first.genesis_message.actor_kind == "SYSTEM"
        assert first.genesis_message.system_actor == "GENESIS"
        assert replay.idempotent_replay is True
        assert replay.human_message.message_id == first.human_message.message_id
        assert replay.genesis_message.message_id == first.genesis_message.message_id
        assert len(gateway.requests) == 1
        messages = history.list_messages(
            analysis.conversation.conversation_id,
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
        )
        assert [message.actor_kind for message in messages] == ["HUMAN", "HUMAN", "SYSTEM"]
        assert analysis.workflow.status == "ANALYSIS_DRAFT"
        assert workflows.get(
            analysis.workflow.workflow_id,
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
        ).status == "ANALYSIS_DRAFT"
        with pytest.raises(GenesisFollowUpFailed) as invalid_answer:
            follow_ups.follow_up(
                analysis.conversation.conversation_id,
                GenesisFollowUpRequest(
                    correlation_id=uuid4(),
                    content="Jawab dengan sitasi yang harus tetap tervalidasi.",
                ),
                organization_id=bootstrap.organization_id,
                actor_user_id=director_id,
            )
        assert invalid_answer.value.code == "MODEL_ANSWER_INVALID"
        assert len(gateway.requests) == 2
        with psycopg.connect(temporary_url) as connection:
            binding = connection.execute(
                """
                SELECT source_document_id, source_version_number, source_content_sha256
                FROM genesis.follow_up_runs
                WHERE organization_id = %s AND correlation_id = %s
                """,
                (bootstrap.organization_id, correlation_id),
            ).fetchone()
            assert binding == (
                source.document_id,
                approved.document.version_number,
                approved.content_sha256,
            )
            connection.execute(
                """
                UPDATE governance.cost_limits
                SET daily_request_limit = 1
                WHERE organization_id = %s AND workspace_id = %s AND active
                """,
                (bootstrap.organization_id, bootstrap.workspace_id),
            )
            connection.commit()
        with pytest.raises(GenesisFollowUpBlocked) as budget_block:
            follow_ups.follow_up(
                analysis.conversation.conversation_id,
                GenesisFollowUpRequest(
                    correlation_id=uuid4(), content="Berikan jawaban kedua untuk menguji budget."
                ),
                organization_id=bootstrap.organization_id,
                actor_user_id=director_id,
            )
        assert budget_block.value.code == "DAILY_REQUEST_LIMIT_REACHED"
        assert len(gateway.requests) == 2
        analysis_service.create_rnd(
            analysis.workflow.workflow_id,
            GenesisDocumentResearchRequest(
                focus="Petakan owner dan KPI yang masih memerlukan review manusia."
            ),
            organization_id=bootstrap.organization_id,
            actor_user_id=director_id,
            correlation_id=uuid4(),
        )
        with pytest.raises(GenesisFollowUpBlocked) as workflow_block:
            follow_ups.follow_up(
                analysis.conversation.conversation_id,
                GenesisFollowUpRequest(
                    correlation_id=uuid4(), content="Follow-up setelah workflow maju."
                ),
                organization_id=bootstrap.organization_id,
                actor_user_id=director_id,
            )
        assert workflow_block.value.code == "WORKFLOW_STATUS_INVALID"
        assert len(gateway.requests) == 2
        actions = {
            event.action
            for event in AuditReader(temporary_url).list_events(bootstrap.organization_id)
        }
        assert {
            "GENESIS_FOLLOW_UP_PROMPT_RECORDED",
            "GENESIS_FOLLOW_UP_MODEL_REQUESTED",
            "GENESIS_FOLLOW_UP_COMPLETED",
            "GENESIS_FOLLOW_UP_BLOCKED",
            "GENESIS_FOLLOW_UP_FAILED",
        }.issubset(actions)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(database_name)))


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        auth_signing_secret="a" * 32,
        llm_provider="openai",
        llm_api_key="test-only-key",
        llm_model="gpt-5.6-luna",
        llm_max_output_tokens=512,
        llm_max_context_tokens=12_000,
        llm_daily_request_limit=20,
        llm_daily_output_token_limit=20_000,
        llm_max_retries=0,
        genesis_conversation_follow_up_enabled=True,
        genesis_follow_up_max_output_tokens=320,
    )


def _model_response() -> ModelResponse:
    answer = (
        "## Jawaban ringkas\nOwner dapat diprioritaskan. [Sumber L1-L2]\n\n"
        "## Temuan dan kekurangan\nOwner belum ditetapkan. [Sumber L1-L1]\n\n"
        "## Checklist perbaikan\n1. Rekomendasi: siapkan usulan owner.\n\n"
        "## Batasan dan informasi yang belum tersedia\n"
        "Nama owner belum tersedia. [Sumber L1-L1]\n\n"
        "## Sumber\n- [Sumber L1-L2]"
    )
    return ModelResponse(
        provider="openai",
        model="test-model",
        output_text=answer,
        usage=ModelUsage(input_tokens=100, output_tokens=60),
        latency_milliseconds=15,
        estimated_cost_usd=Decimal("0.000321"),
    )


def _invalid_model_response() -> ModelResponse:
    return _model_response().model_copy(
        update={"output_text": _model_response().output_text.replace("L1-L2", "L7-L9")}
    )


def _factory_for(
    gateway: ModelGateway,
) -> Callable[[], tuple[ModelGateway, Callable[[], None]]]:
    return lambda: (gateway, lambda: None)


def _add_workspace_user(
    database_url: str,
    organization_id: UUID,
    workspace_id: UUID,
    email: str,
    role_code: str,
) -> UUID:
    with psycopg.connect(database_url) as connection:
        user = connection.execute(
            """
            INSERT INTO identity.users (organization_id, email, display_name)
            VALUES (%s, %s, %s) RETURNING user_id
            """,
            (organization_id, email, email.split("@", 1)[0]),
        ).fetchone()
        if user is None:
            raise AssertionError("workspace fixture user was not created")
        connection.execute(
            "INSERT INTO identity.role_assignments (user_id, role_code) VALUES (%s, %s)",
            (user[0], role_code),
        )
        connection.execute(
            """
            INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
            VALUES (%s, %s, 'EDITOR')
            """,
            (workspace_id, user[0]),
        )
        connection.commit()
    return user[0]

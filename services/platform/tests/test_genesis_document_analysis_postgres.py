import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.audit.reader import AuditReader
from alos.config import get_settings
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
from alos.genesis.history import GenesisHistoryRepository
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_director_document_analysis_binds_approved_source_to_a_draft() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_genesis_document_analysis_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        checker_id = _add_workspace_user(
            temporary_url,
            context.organization_id,
            context.workspace_id,
            "checker@example.test",
            "BUSINESS_REVIEWER",
        )
        director_id = _add_workspace_user(
            temporary_url,
            context.organization_id,
            context.workspace_id,
            "director@example.test",
            "DIRECTOR",
        )
        documents = DocumentCenterRepository(temporary_url)
        source = documents.create_draft(
            DocumentDraftRequest(
                workspace_id=context.workspace_id,
                title="Rencana Operasional 2026",
                content="Rencana operasional internal yang telah siap untuk ditinjau.",
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        for check_key in ("SOURCE_EVIDENCE", "SCOPE_OWNER", "RISK_CLASSIFICATION"):
            documents.complete_checklist_item(
                source.document_id,
                check_key,
                ChecklistCompletionRequest(notes=f"Independent checker completed {check_key}."),
                organization_id=context.organization_id,
                actor_user_id=checker_id,
                correlation_id=uuid4(),
            )
        documents.submit_for_review(
            source.document_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        approved_source = documents.decide_review(
            source.document_id,
            DocumentReviewDecisionRequest(notes="Director approved the source document."),
            approved=True,
            organization_id=context.organization_id,
            actor_user_id=director_id,
            correlation_id=uuid4(),
        )
        service = GenesisDocumentAnalysisService(
            documents, GenesisHistoryRepository(temporary_url)
        )
        result = service.create_analysis(
            GenesisDocumentAnalysisRequest(
                workspace_id=context.workspace_id,
                source_document_id=source.document_id,
                prompt="Analisa dokumen ini dan catatkan kebutuhan pemeriksaan sebelum R&D.",
            ),
            organization_id=context.organization_id,
            actor_user_id=director_id,
            correlation_id=uuid4(),
        )
        assert approved_source.document.status == "APPROVED"
        assert result.source.document_id == source.document_id
        assert result.source.content_sha256 == approved_source.content_sha256
        assert result.analysis.artifact_type == "ANALYSIS"
        assert result.analysis.content["source"]["document_id"] == str(source.document_id)
        assert result.draft.origin == "GENESIS"
        assert result.draft.status == "DRAFT"
        draft_detail = documents.get_document(
            result.draft.document_id,
            organization_id=context.organization_id,
            actor_user_id=director_id,
        )
        assert approved_source.content_sha256 in draft_detail.content
        assert "Tidak ada kesimpulan substantif" in draft_detail.content
        events = AuditReader(temporary_url).list_events(context.organization_id)
        assert {event.action for event in events}.issuperset(
            {
                "GENESIS_CONVERSATION_CREATED",
                "GENESIS_REQUIREMENT_RECORDED",
                "GENESIS_ARTIFACT_RECORDED",
                "GENESIS_DOCUMENT_ANALYSIS_DRAFT_CREATED",
            }
        )
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


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

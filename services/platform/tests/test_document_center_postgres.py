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
    DocumentConflictError,
    DocumentReviewDecisionRequest,
    GenesisDocumentDraftRequest,
)
from alos.genesis.history import GenesisConversationRequest, GenesisHistoryRepository
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_document_center_keeps_genesis_draft_checklist_and_approval_separate() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_document_center_{uuid4().hex}"
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
        approver_id = _add_workspace_user(
            temporary_url,
            context.organization_id,
            context.workspace_id,
            "approver@example.test",
            "DIRECTOR",
        )
        history = GenesisHistoryRepository(temporary_url)
        conversation = history.create_conversation(
            GenesisConversationRequest(workspace_id=context.workspace_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        documents = DocumentCenterRepository(temporary_url)
        document = documents.create_genesis_draft(
            GenesisDocumentDraftRequest(
                workspace_id=context.workspace_id,
                title="SOP Brief Operasional",
                requirement=(
                    "Siapkan kerangka SOP Brief Operasional dengan sumber yang harus diverifikasi."
                ),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            conversation_id=conversation.conversation_id,
        )
        assert document.origin == "GENESIS"
        assert document.status == "DRAFT"
        assert documents.list_documents(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        ) == [document]

        with pytest.raises(DocumentConflictError, match="draft creator"):
            documents.complete_checklist_item(
                document.document_id,
                "SOURCE_EVIDENCE",
                ChecklistCompletionRequest(notes="Maker must not check its own draft."),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
            )

        for check_key in ("SOURCE_EVIDENCE", "SCOPE_OWNER", "RISK_CLASSIFICATION"):
            documents.complete_checklist_item(
                document.document_id,
                check_key,
                ChecklistCompletionRequest(notes=f"Independent checker completed {check_key}."),
                organization_id=context.organization_id,
                actor_user_id=checker_id,
                correlation_id=uuid4(),
            )

        in_review = documents.submit_for_review(
            document.document_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        assert in_review.document.status == "IN_REVIEW"
        assert all(item.status == "PASSED" for item in in_review.checklist)

        with pytest.raises(DocumentConflictError, match="cannot decide its own"):
            documents.decide_review(
                document.document_id,
                DocumentReviewDecisionRequest(notes="Maker cannot approve."),
                approved=True,
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
            )

        approved = documents.decide_review(
            document.document_id,
            DocumentReviewDecisionRequest(notes="Independent approval complete."),
            approved=True,
            organization_id=context.organization_id,
            actor_user_id=approver_id,
            correlation_id=uuid4(),
        )
        assert approved.document.status == "APPROVED"
        assert approved.reviews[0].reviewer_user_id == approver_id
        assert approved.content.startswith("# SOP Brief Operasional")
        events = AuditReader(temporary_url).list_events(context.organization_id)
        assert {event.action for event in events}.issuperset(
            {
                "GENESIS_DOCUMENT_DRAFT_CREATED",
                "DOCUMENT_CHECKLIST_COMPLETED",
                "DOCUMENT_SUBMITTED_FOR_REVIEW",
                "DOCUMENT_APPROVED",
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

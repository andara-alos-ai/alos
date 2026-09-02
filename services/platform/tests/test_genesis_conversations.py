import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alos.agents.registry import AgentRegistry
from alos.config import get_settings
from alos.genesis import (
    GenesisAnalyzeService,
    GenesisConversationCreate,
    GenesisConversationService,
    GenesisConversationStatus,
    GenesisMessageCreate,
    GenesisSenderType,
    InMemoryGenesisConversationStore,
    PostgresGenesisConversationStore,
    SourceRegistry,
)
from alos.llm import DisabledProvider, LLMGateway, PromptRegistry
from alos.main import app
from alos.persistence import Database
from alos.security import Principal, Role

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_genesis_conversation_service_with_initial_prompt() -> None:
    settings = get_settings()
    prompts = PromptRegistry(settings.definitions_root)
    gateway = LLMGateway(prompts, DisabledProvider())
    agents = AgentRegistry(settings.definitions_root)
    sources = SourceRegistry(settings.definitions_root)
    analyze_service = GenesisAnalyzeService(gateway, agents, sources)

    store = InMemoryGenesisConversationStore()
    service = GenesisConversationService(store, analyze_service)

    principal = Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.DIRECTOR}),
        division_codes=frozenset(),
        project_ids=frozenset(),
    )

    # 1. Create conversation with initial prompt
    conv = service.create_conversation(
        GenesisConversationCreate(
            title="Perancangan Agent Verifikasi Invoice Vendor",
            initial_prompt=(
                "Buat agent untuk membantu Finance memeriksa pengajuan pembayaran vendor. "
                "Agent harus memeriksa invoice, evidence pekerjaan, anggaran, pajak, "
                "dan jalur approval. Agent tidak boleh menyetujui atau melakukan pembayaran."
            ),
        ),
        principal,
    )

    assert conv.title == "Perancangan Agent Verifikasi Invoice Vendor"
    assert conv.status == GenesisConversationStatus.ACTIVE
    assert len(conv.messages) == 2
    assert conv.messages[0].sender_type == GenesisSenderType.USER
    assert conv.messages[1].sender_type == GenesisSenderType.GENESIS_ASSISTANT
    assert conv.messages[1].analysis_result is not None
    assert conv.messages[0].metadata["message_role"] == "REQUEST"
    assert conv.messages[1].metadata["provider"] == "disabled"
    assert conv.messages[1].analysis_result.parent_core_agent_id in {"FRA", "BCA"}

    assert len(conv.artifact_versions) == 1
    assert conv.artifact_versions[0].version_number == 1
    assert conv.artifact_versions[0].agent_id.startswith("SUB_FRA_")

    # 2. Post multi-turn message (iteration)
    updated_conv = service.post_message(
        conv.conversation_id,
        GenesisMessageCreate(
            message_text=(
                "Tambahkan pengecekan batas nominal pembayaran kas kecil vs invoice besar."
            ),
        ),
        principal,
    )

    assert len(updated_conv.messages) == 4
    assert updated_conv.messages[2].sender_type == GenesisSenderType.USER
    assert updated_conv.messages[3].sender_type == GenesisSenderType.GENESIS_ASSISTANT
    assert len(updated_conv.artifact_versions) == 2
    assert updated_conv.artifact_versions[1].version_number == 2
    assert updated_conv.artifact_versions[1].diff

    # 3. List conversations
    items = service.list_conversations(principal)
    assert len(items) == 1
    assert items[0].conversation_id == conv.conversation_id
    assert items[0].message_count == 4
    assert items[0].artifact_version_count == 2

    # 4. Get artifact versions
    artifacts = service.get_artifact_versions(conv.conversation_id, principal)
    assert len(artifacts) == 2
    assert artifacts[0].version_number == 1
    assert artifacts[1].version_number == 2


def test_genesis_conversations_api_endpoints() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT organization_id FROM identity.organizations WHERE code = 'ARM'")
        ).fetchone()
        assert row is not None
        org_id = row[0]

    client = TestClient(app)
    bootstrap_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(org_id),
            "roles": ["IT_ADMIN"],
            "division_codes": ["IT"],
            "project_ids": [],
        },
    )
    bootstrap_token = bootstrap_res.json()["access_token"]
    bootstrap_headers = {"Authorization": f"Bearer {bootstrap_token}"}

    # Create director user in database
    user_res = client.post(
        "/api/v1/users",
        headers=bootstrap_headers,
        json={
            "email": f"director-{uuid4().hex[:8]}@example.test",
            "display_name": "Test Director Genesis",
            "division_code": None,
            "role": "DIRECTOR",
        },
    )
    assert user_res.status_code == 201
    user_id = user_res.json()["user_id"]

    # Login as Director
    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "roles": ["DIRECTOR"],
            "division_codes": [],
            "project_ids": [],
        },
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create conversation via API
    create_res = client.post(
        "/api/v1/genesis/conversations",
        headers=headers,
        json={
            "title": "Perancangan Workforce Property Site Inspection",
            "initial_prompt": (
                "Buat agent untuk inspeksi progres fisik dan opname lapangan kontraktor."
            ),
            "source_references": [],
        },
    )
    assert create_res.status_code == 201
    conv_data = create_res.json()
    conv_id = conv_data["conversation_id"]
    assert conv_data["title"] == "Perancangan Workforce Property Site Inspection"
    assert len(conv_data["messages"]) == 2
    assert len(conv_data["artifact_versions"]) == 1

    # 2. List conversations via API
    list_res = client.get("/api/v1/genesis/conversations", headers=headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert any(item["conversation_id"] == conv_id for item in list_data)

    # 3. Post iteration message via API
    msg_res = client.post(
        f"/api/v1/genesis/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "message_text": (
                "Tambahkan aturan pemeriksaan foto geotag dan timestamp pada evidence lapangan."
            ),
        },
    )
    assert msg_res.status_code == 200
    updated_data = msg_res.json()
    assert len(updated_data["messages"]) == 4
    assert len(updated_data["artifact_versions"]) == 2

    # 4. Get artifacts history via API
    art_res = client.get(
        f"/api/v1/genesis/conversations/{conv_id}/artifacts",
        headers=headers,
    )
    assert art_res.status_code == 200
    art_data = art_res.json()
    assert len(art_data) == 2
    assert art_data[0]["version_number"] == 1
    assert art_data[1]["version_number"] == 2


def test_genesis_conversations_unauthorized_access() -> None:
    client = TestClient(app)

    # 1. Unauthenticated request
    res_no_auth = client.post(
        "/api/v1/genesis/conversations",
        json={"title": "Test Conv"},
    )
    assert res_no_auth.status_code == 401

    # 2. Authenticated with unprivileged role (SALES)
    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["SALES"],
            "division_codes": ["SALES"],
            "project_ids": [],
        },
    )
    token = login_res.json()["access_token"]
    res_forbidden = client.post(
        "/api/v1/genesis/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Test Conv"},
    )
    assert res_forbidden.status_code == 403


def test_postgres_genesis_conversation_store_persistence() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    store = PostgresGenesisConversationStore(db.engine)

    org_id = uuid4()
    user_id = uuid4()

    # Create dummy org & user in DB for FK constraints
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO identity.organizations (organization_id, code, name, created_at)
                VALUES (:org_id, :code, :name, NOW())
                ON CONFLICT (organization_id) DO NOTHING
                """
            ),
            {"org_id": org_id, "code": f"ORG-{org_id.hex[:6]}", "name": "Test Org Conv"},
        )
        conn.execute(
            text(
                """
                INSERT INTO identity.users (
                    user_id, organization_id, email, display_name, status, created_at, updated_at
                ) VALUES (
                    :user_id, :org_id, :email, :display_name, 'ACTIVE', NOW(), NOW()
                )
                ON CONFLICT (user_id) DO NOTHING
                """
            ),
            {
                "user_id": user_id,
                "org_id": org_id,
                "email": f"user_{user_id.hex[:6]}@andara.co.id",
                "display_name": "Test User Conv",
            },
        )

    # 1. Create conversation
    conv = store.create_conversation(
        organization_id=org_id,
        created_by_user_id=user_id,
        title="Postgres Conv Test",
    )
    assert conv.title == "Postgres Conv Test"

    # 2. Add message
    msg = store.add_message(
        conversation_id=conv.conversation_id,
        sender_type=GenesisSenderType.USER,
        sender_user_id=user_id,
        message_text="Halo Genesis, buatkan spesifikasi agent.",
    )
    assert msg.message_text == "Halo Genesis, buatkan spesifikasi agent."

    # 3. Add artifact version
    art = store.add_artifact_version(
        conversation_id=conv.conversation_id,
        version_number=1,
        agent_id="SUB-DIA-SPEC",
        spec_data={"name": "Test Spec"},
        created_by_user_id=user_id,
        change_summary="Initial spec v1",
    )
    assert art.version_number == 1

    # 4. Fetch conversation
    fetched = store.get_conversation(org_id, conv.conversation_id)
    assert fetched is not None
    assert len(fetched.messages) == 1
    assert len(fetched.artifact_versions) == 1

    # 5. List
    list_items = store.list_conversations(org_id)
    assert len(list_items) >= 1
    assert any(i.conversation_id == conv.conversation_id for i in list_items)


def test_postgres_genesis_conversation_rejects_cross_tenant_project() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    store = PostgresGenesisConversationStore(db.engine)
    organization_id = uuid4()
    user_id = uuid4()
    other_organization_id = uuid4()
    other_user_id = uuid4()
    other_project_id = uuid4()

    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO identity.organizations (organization_id, code, name)
                VALUES (:organization_id, :code, :name),
                       (:other_organization_id, :other_code, :other_name)
                """
            ),
            {
                "organization_id": organization_id,
                "code": f"ORG-{organization_id.hex[:8]}",
                "name": "Genesis Tenant A",
                "other_organization_id": other_organization_id,
                "other_code": f"ORG-{other_organization_id.hex[:8]}",
                "other_name": "Genesis Tenant B",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO identity.users (
                    user_id, organization_id, email, display_name, status
                ) VALUES
                    (:user_id, :organization_id, :email, 'Tenant A User', 'ACTIVE'),
                    (:other_user_id, :other_organization_id, :other_email,
                     'Tenant B User', 'ACTIVE')
                """
            ),
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "email": f"user-{user_id.hex[:8]}@example.test",
                "other_user_id": other_user_id,
                "other_organization_id": other_organization_id,
                "other_email": f"user-{other_user_id.hex[:8]}@example.test",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO platform.projects (
                    project_id, organization_id, code, name, status, created_by
                ) VALUES (
                    :project_id, :organization_id, :code, 'Tenant B Project', 'DRAFT', :created_by
                )
                """
            ),
            {
                "project_id": other_project_id,
                "organization_id": other_organization_id,
                "code": f"PRJ-{other_project_id.hex[:8]}",
                "created_by": other_user_id,
            },
        )

    with pytest.raises(IntegrityError):
        store.create_conversation(
            organization_id=organization_id,
            created_by_user_id=user_id,
            title="Cross tenant project must fail",
            project_id=other_project_id,
        )

    with pytest.raises(IntegrityError):
        store.create_conversation(
            organization_id=organization_id,
            created_by_user_id=other_user_id,
            title="Cross tenant creator must fail",
        )

    valid_conversation = store.create_conversation(
        organization_id=organization_id,
        created_by_user_id=user_id,
        title="Tenant scoped history",
    )
    with pytest.raises(IntegrityError):
        store.add_message(
            conversation_id=valid_conversation.conversation_id,
            sender_type=GenesisSenderType.USER,
            sender_user_id=other_user_id,
            message_text="Cross tenant sender must fail",
        )
    with pytest.raises(IntegrityError):
        store.add_artifact_version(
            conversation_id=valid_conversation.conversation_id,
            version_number=1,
            agent_id="SUB_DIA_TENANT_TEST",
            spec_data={"name": "Tenant test"},
            created_by_user_id=other_user_id,
            change_summary="Cross tenant creator must fail",
        )

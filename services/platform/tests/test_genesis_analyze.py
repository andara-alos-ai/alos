import json
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from alos.agents.registry import AgentRegistry
from alos.config import get_settings
from alos.genesis import (
    GenesisAnalyzeRequest,
    GenesisAnalyzeResult,
    GenesisAnalyzeService,
    GenesisStrategy,
    SourceRegistry,
)
from alos.llm import (
    DisabledProvider,
    LLMGateway,
    LocalOpenAIProvider,
    PromptRegistry,
)
from alos.main import app
from alos.security import Principal, Role


def test_genesis_analyze_fallback_vendor_payment() -> None:
    settings = get_settings()
    prompts = PromptRegistry(settings.definitions_root)
    gateway = LLMGateway(prompts, DisabledProvider())
    agents = AgentRegistry(settings.definitions_root)
    sources = SourceRegistry(settings.definitions_root)

    service = GenesisAnalyzeService(gateway, agents, sources)
    principal = Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.DIRECTOR}),
        division_codes=frozenset(),
        project_ids=frozenset(),
    )

    request = GenesisAnalyzeRequest(
        prompt=(
            "Buat agent untuk membantu Finance memeriksa pengajuan pembayaran vendor. "
            "Agent harus memeriksa invoice, evidence pekerjaan, anggaran, pajak, "
            "dan jalur approval. Agent tidak boleh menyetujui atau melakukan pembayaran."
        ),
        source_references=("ALOS-SP-SYNTHETIC-PILOT@1.0.0",),
    )

    result = service.analyze(request, principal)

    assert isinstance(result, GenesisAnalyzeResult)
    assert result.runtime_scope == "SHARED_AGENT_RUNTIME"
    assert result.domain == "shared-enterprise"
    assert result.strategy == GenesisStrategy.CREATE
    assert result.agent_contract_draft.agent_kind == "LOGICAL"
    assert result.agent_contract_draft.division_scope == ("FINANCE",)
    assert result.production_effect is False
    assert len(result.agent_contract_draft.forbidden_actions) > 0
    assert len(result.workflow_proposal.steps) > 0
    assert all(v.passed for v in result.validations)


def test_genesis_analyze_local_openai_provider_mock() -> None:
    settings = get_settings()
    prompts = PromptRegistry(settings.definitions_root)

    mock_llm_response = {
        "id": "chatcmpl-mock-123",
        "model": "qwen2.5-coder:7b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                        "content": json.dumps(
                            {
                                "understanding": (
                                    "Kebutuhan verifikasi invoice vendor untuk Finance."
                                ),
                                "business_owner": "Kepala Keuangan",
                                "agent_contract_draft": {
                                    "agent_id": "GENESIS_FINANCE_VENDOR_CHECK",
                                    "name": "Vendor Invoice Checker",
                                    "purpose": (
                                        "Verifikasi invoice dan evidence vendor secara read-only."
                                    ),
                                    "division_scope": ["FINANCE"],
                                    "human_owner": "Kepala Keuangan",
                                    "inputs": ["invoice_file", "evidence_doc"],
                                    "outputs": ["verification_status"],
                                    "source_of_truth": ["RAB", "SOP Finance"],
                                    "capabilities": ["validate_invoice_rules"],
                                    "tools_allowed": ["alos.invoice.read"],
                                    "approval_boundary": ["Tidak boleh menyetujui pembayaran"],
                                    "evidence_requirement": ["Invoice asli"],
                                    "forbidden_actions": ["Transfer bank", "Approval mandiri"],
                                    "kpi_metrics": ["Akurasi"],
                                    "escalation": ["Invoice tidak terbaca"],
                                    "prompt_ref": "genesis.validation@0.1.0",
                                    "model_policy_ref": "openai-primary-claude-fallback@0.1.0",
                                    "permission_policy_ref": "read-only-evidence@0.1.0",
                                    "risk_level": "LOW"
                                },
                                "workflow_proposal": {
                                    "workflow_name": "Vendor Payment Verification Workflow",
                                    "steps": []
                                },
                                "risks_and_blockers": ["Aturan pajak perlu validasi."],
                                "unanswered_questions": ["Berapa batas nominal approval Direktur?"]
                            }
                        ),
                },
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 250},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_llm_response)

    transport = httpx.MockTransport(handler)
    provider = LocalOpenAIProvider(
        model="qwen2.5-coder:7b",
        base_url="http://mock-local-llm/v1",
        transport=transport,
    )

    gateway = LLMGateway(prompts, provider)
    agents = AgentRegistry(settings.definitions_root)
    sources = SourceRegistry(settings.definitions_root)

    service = GenesisAnalyzeService(gateway, agents, sources)
    principal = Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.DIVISION_HEAD}),
        division_codes=frozenset({"FINANCE"}),
        project_ids=frozenset(),
    )

    request = GenesisAnalyzeRequest(
        prompt="Buat logical agent finance untuk verifikasi invoice vendor.",
        source_references=("ALOS-SP-SYNTHETIC-PILOT@1.0.0",),
    )
    result = service.analyze(request, principal)

    assert result.strategy == GenesisStrategy.CREATE
    assert result.runtime_scope == "SHARED_AGENT_RUNTIME"
    assert result.agent_contract_draft.agent_id == "GENESIS_FINANCE_VENDOR_CHECK"
    assert result.llm_result_status == "COMPLETED"
    assert result.production_effect is False


def test_genesis_analyze_api_endpoint() -> None:
    client = TestClient(app)
    org_id = uuid4()
    user_id = uuid4()

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

    response = client.post(
        "/api/v1/genesis/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "prompt": "Buat agent untuk membantu Sales kualifikasi lead baru.",
            "source_references": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "understanding" in data
    assert "strategy" in data
    assert data["runtime_scope"] == "SHARED_AGENT_RUNTIME"
    assert data["agent_contract_draft"]["agent_kind"] == "LOGICAL"
    assert data["production_effect"] is False
    assert "agent_contract_draft" in data


def test_genesis_analyze_unauthorized_access() -> None:
    client = TestClient(app)

    # 1. Unauthenticated request
    res_no_auth = client.post(
        "/api/v1/genesis/analyze",
        json={"prompt": "Buat agent baru."},
    )
    assert res_no_auth.status_code == 401

    # 2. Authenticated with unprivileged role (FINANCE staff without DIVISION_HEAD)
    login_res = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": ["FINANCE"],
            "division_codes": ["FINANCE"],
            "project_ids": [],
        },
    )
    token = login_res.json()["access_token"]

    res_forbidden = client.post(
        "/api/v1/genesis/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "Buat agent baru."},
    )
    assert res_forbidden.status_code == 403


def test_local_openai_provider_markdown_code_fences() -> None:
    settings = get_settings()
    prompts = PromptRegistry(settings.definitions_root)
    prompt_def = prompts.get("agent.structured-analysis")

    # Mock response with ```json ... ``` wrapper
    markdown_wrapped_content = "```json\n" + json.dumps({
        "summary": "Analisis ringkas",
        "findings": ["Temuan 1", "Temuan 2"],
        "confidence": 0.95,
        "human_review_required": True,
    }) + "\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-md-1",
                "model": "mistral:7b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": markdown_wrapped_content,
                        },
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 60},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = LocalOpenAIProvider(
        model="mistral:7b",
        base_url="http://mock-local/v1",
        transport=transport,
    )

    output = provider.generate(
        prompt_def,
        {"some_input": "data"},
        max_output_tokens=500,
        safety_identifier="test-user",
    )

    assert output.output["summary"] == "Analisis ringkas"
    assert len(output.output["findings"]) == 2
    assert output.output["confidence"] == 0.95
    assert output.output["human_review_required"] is True
    assert output.usage.input_tokens == 50
    assert output.usage.output_tokens == 60

from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.agents.registry import (
    AgentBuilderRequest,
    AgentDraftBuilder,
    DeterministicAgentDraftGenerator,
    GeneratedAgentFields,
)
from alos.agents.validation_catalog import validation_agent_requests
from alos.main import AgentDesignerRequest
from alos.sources.registry import SourceVaultPolicyRequest


class StubDraftGenerator:
    def generate(self, request: AgentBuilderRequest) -> GeneratedAgentFields:
        return GeneratedAgentFields(
            purpose=f"Read-only: {request.objective}",
            prompt_template="Return cited evidence only. Do not take actions.",
            evidence_requirements=["source reference", "retrieval timestamp"],
        )


def _request(**changes: object) -> AgentBuilderRequest:
    values: dict[str, object] = {
        "workspace_id": uuid4(),
        "agent_key": "DAILY_BRIEF",
        "name": "Daily Brief",
        "objective": "Prepare a concise read-only operational brief from registered sources.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "model_policy": {"provider": "gemini", "mode": "local_test"},
        "tool_keys": [],
        "permission_keys": ["sources.read"],
        "approval_required": True,
        "forbidden_actions": ["No write, external action, or production change."],
        "kpis": [{"name": "citation_coverage", "target": 1}],
    }
    values.update(changes)
    return AgentBuilderRequest.model_validate(values)


def test_builder_keeps_human_security_controls_outside_draft_generator() -> None:
    request = _request(risk_level="HIGH", approval_required=True)

    contract = AgentDraftBuilder(StubDraftGenerator()).build(request, uuid4())

    assert contract.workspace_id == request.workspace_id
    assert contract.risk_level == "HIGH"
    assert contract.approval_required is True
    assert contract.tool_keys == []
    assert contract.permission_keys == ["sources.read"]
    assert contract.prompt_template == "Return cited evidence only. Do not take actions."


def test_deterministic_genesis_builder_never_requires_a_model_gateway() -> None:
    request = _request(
        objective="Prepare a read-only operational brief from registered evidence for IT review."
    )

    contract = AgentDraftBuilder(DeterministicAgentDraftGenerator()).build(request, uuid4())

    assert contract.purpose == request.objective
    assert "Do not take external actions." in contract.prompt_template
    assert request.forbidden_actions[0] in contract.prompt_template
    assert contract.evidence_requirements == [
        "Use only registered or explicitly supplied evidence.",
        "Cite evidence for every material conclusion.",
    ]


def test_generated_fields_normalizes_a_single_non_security_evidence_statement() -> None:
    generated = GeneratedAgentFields.model_validate(
        {
            "purpose": "Read-only validation.",
            "prompt_template": "Return JSON only.",
            "evidence_requirements": "Cite every source.",
        }
    )

    assert generated.evidence_requirements == ["Cite every source."]


def test_high_risk_builder_request_cannot_disable_human_approval() -> None:
    with pytest.raises(ValidationError, match="require human approval"):
        _request(risk_level="HIGH", approval_required=False)


def test_natural_language_designer_request_stays_a_low_risk_draft_input() -> None:
    request = AgentDesignerRequest(
        workspace_id=uuid4(),
        agent_key="PROPERTY_LEAD_BRIEF",
        name="Property Lead Brief",
        requirement=(
            "Create a read-only daily property lead brief from registered internal sources "
            "with citations."
        ),
    )

    builder_request = request.to_builder_request()

    assert builder_request.objective == request.requirement
    assert builder_request.risk_level == "LOW"
    assert builder_request.approval_required is True
    assert builder_request.tool_keys == []
    assert builder_request.permission_keys == []
    assert builder_request.forbidden_actions == [
        "Do not write data, contact external parties, spend funds, or change production."
    ]


def test_natural_language_designer_can_generate_a_deterministic_draft_identity() -> None:
    request = AgentDesignerRequest(
        workspace_id=uuid4(),
        requirement=(
            "Create a read-only daily property lead brief from internal registered sources."
        ),
    )

    first = request.to_builder_request()
    second = request.to_builder_request()

    assert first.agent_key == second.agent_key
    assert first.agent_key.startswith("GENESIS_")
    assert first.name.startswith("Genesis Draft ")


def test_validation_agent_catalog_has_three_generic_read_only_contract_inputs() -> None:
    requests = validation_agent_requests(uuid4())

    assert [request.agent_key for request in requests] == [
        "DAILY_BRIEF",
        "EVIDENCE_CHECKER",
        "PERMIT_OVERDUE_MONITOR",
    ]
    assert all(request.risk_level == "LOW" for request in requests)
    assert all(request.approval_required for request in requests)
    assert all(request.tool_keys == ["SOURCE_REGISTRY_SEARCH"] for request in requests)
    assert all(request.permission_keys == ["SOURCE_READ_INTERNAL"] for request in requests)
    assert all(request.model_policy["model_route"] == "light" for request in requests)
    assert all(request.model_policy["max_output_tokens"] == 1200 for request in requests)
    assert all("provider" not in request.model_policy for request in requests)
    assert all("Do not write data" in request.forbidden_actions[0] for request in requests)


def test_source_vault_policy_accepts_distinct_google_drive_folders() -> None:
    allowed_root = "https://drive.google.com/drive/folders/1D66GYJVl7WZlefS8e8FO9lkL034CA9wS"
    excluded_folder = "https://drive.google.com/drive/folders/1rf-8esLauaCNylWm6Y65oQfMU68AvTqj"

    policy = SourceVaultPolicyRequest(
        allowed_root_url=allowed_root,
        excluded_folder_url=excluded_folder,
        reason="Controlled H5 pilot allows only the management-approved source root.",
    )

    assert policy.allowed_root_url == allowed_root
    assert policy.excluded_folder_url == excluded_folder


def test_source_vault_policy_rejects_invalid_folder_boundaries() -> None:
    allowed_root = "https://drive.google.com/drive/folders/1D66GYJVl7WZlefS8e8FO9lkL034CA9wS"

    with pytest.raises(ValidationError, match="must be different"):
        SourceVaultPolicyRequest(
            allowed_root_url=allowed_root,
            excluded_folder_url=allowed_root,
            reason="A policy must preserve a separately denied folder boundary.",
        )
    with pytest.raises(ValidationError, match="Google Drive folder URL"):
        SourceVaultPolicyRequest(
            allowed_root_url="https://example.com/not-a-drive-folder",
            excluded_folder_url=allowed_root,
            reason="H5 requires a Drive folder boundary before registration.",
        )

from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.agents.registry import (
    AgentBuilderRequest,
    AgentDraftBuilder,
    GeneratedAgentFields,
)
from alos.agents.validation_catalog import validation_agent_requests
from alos.main import AgentDesignerRequest


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


def test_builder_keeps_human_security_controls_outside_gemini() -> None:
    request = _request(risk_level="HIGH", approval_required=True)

    contract = AgentDraftBuilder(StubDraftGenerator()).build(request, uuid4())

    assert contract.workspace_id == request.workspace_id
    assert contract.risk_level == "HIGH"
    assert contract.approval_required is True
    assert contract.tool_keys == []
    assert contract.permission_keys == ["sources.read"]
    assert contract.prompt_template == "Return cited evidence only. Do not take actions."


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


def test_validation_agent_catalog_has_three_generic_read_only_contract_inputs() -> None:
    requests = validation_agent_requests(uuid4())

    assert [request.agent_key for request in requests] == [
        "DAILY_BRIEF",
        "EVIDENCE_CHECKER",
        "PERMIT_OVERDUE_MONITOR",
    ]
    assert all(request.risk_level == "LOW" for request in requests)
    assert all(request.approval_required for request in requests)
    assert all(request.tool_keys == [] for request in requests)
    assert all(request.permission_keys == [] for request in requests)
    assert all("Do not write data" in request.forbidden_actions[0] for request in requests)

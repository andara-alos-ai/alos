from pathlib import Path

import pytest

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.registry import AgentRegistry
from alos.agents.runtime import (
    AgentCapabilityExecuteRequest,
    AgentRunRequest,
    SharedAgentRuntime,
)
from alos.tools import ToolEffect, ToolRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

CORE_SYNTHETIC_INPUTS: dict[str, dict[str, object]] = {
    "ARA": {"amount": 1_000_000},
    "BCA": {"amount": 1_000_000, "available_amount": 2_000_000},
    "CEA": {"checksum_valid": True, "scan_status": "CLEAN"},
    "CFA": {"content": "Riwayat follow-up sintetis."},
    "CLA": {"content": "Kontrak sintetis untuk validasi runtime."},
    "CRA": {"impact_score": 2, "probability_score": 2},
    "DIA": {"content": "Dokumen sintetis untuk klasifikasi."},
    "FRA": {
        "payment_amount": 100,
        "transaction_amount": 100,
        "payment_reference": "PAY-001",
        "transaction_reference": "PAY-001",
        "payment_currency": "IDR",
        "currency": "IDR",
    },
    "HPA": {"required_documents": ["KTP"], "provided_documents": ["KTP"]},
    "HRA": {"content": "Profil kandidat sintetis."},
    "KDA": {"numerator": 9, "denominator": 10, "target": 0.8},
    "LPA": {"content": "Dokumen izin sintetis."},
    "MCA": {
        "verified_facts": [{"status": "VERIFIED"}],
        "source_references": ["synthetic:fact"],
    },
    "MCA_MKT": {"content": "Brief konten marketing sintetis."},
    "SEA": {
        "released_versions": [
            {"sop_id": "SOP-001", "version": "1.0.0", "status": "RELEASED"}
        ]
    },
    "SLA": {"phone": "081234567890", "consent_recorded": True},
    "TIA": {"content": "Invoice sintetis."},
    "TPA": {
        "required_evidence": ["PHOTO"],
        "provided_evidence": ["PHOTO"],
        "all_verified": True,
    },
}


def test_all_agent_capabilities_have_versioned_contracts_and_handlers() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    capabilities = CapabilityRegistry(definitions)
    contracts = capabilities.load_all()
    referenced = {
        capability
        for agent in AgentRegistry(definitions).load_all()
        for capability in agent.capabilities
    }

    assert len(contracts) == 62
    assert referenced == {item.capability_id for item in contracts}
    assert all(item.contract_digest for item in contracts)
    assert all(item.input_schema["properties"] for item in contracts)
    assert all(item.output_schema["properties"] for item in contracts)


def test_each_of_18_core_agents_executes_through_shared_runtime() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    agents = AgentRegistry(definitions)
    tools = ToolRegistry(definitions)
    runtime = SharedAgentRuntime(agents, tools)

    for agent in agents.load_core():
        capability_id = agent.capabilities[0]
        capability = CapabilityRegistry(definitions).get(capability_id)
        requested_tools: list[str] = []
        if capability.execution_mode == "AI_ASSISTED":
            requested_tools = [
                tool_id
                for tool_id in agent.tools_allowed
                if tools.get(tool_id).effect == ToolEffect.AI_ASSISTED
            ][:1]
        plan = runtime.prepare(
            AgentRunRequest(
                agent_id=agent.agent_id,
                capability=capability_id,
                execution_mode=capability.execution_mode,
                input_references=[f"synthetic:{agent.agent_id.lower()}"],
                requested_tools=requested_tools,
                correlation_id="00000000-0000-0000-0000-000000000001",
                idempotency_key=f"synthetic-{agent.agent_id.lower()}-001",
            )
        )
        payload = {
            **CORE_SYNTHETIC_INPUTS[agent.agent_id],
            "data_classification": "INTERNAL",
        }
        if capability.execution_mode == "AI_ASSISTED":
            payload["source_reference"] = f"synthetic:{agent.agent_id.lower()}"
        executed = runtime.execute(plan, payload)

        assert executed.execution is not None
        assert executed.execution.handler_id == capability.handler_id
        assert executed.execution.status in {"COMPLETED", "NEEDS_REVIEW"}


def test_direct_agent_payload_rejects_credentials_and_oversized_data() -> None:
    with pytest.raises(ValueError, match="Kredensial"):
        AgentCapabilityExecuteRequest(
            agent_id="TIA",
            capability="invoice_validation",
            input_references=["invoice:test"],
            input_payload={"nested": {"api-key": "not-allowed"}},
        )

    with pytest.raises(ValueError, match="256 KiB"):
        AgentCapabilityExecuteRequest(
            agent_id="TIA",
            capability="invoice_validation",
            input_references=["invoice:test"],
            input_payload={"content": "x" * (256 * 1024)},
        )


def test_numeric_capability_fails_safe_for_invalid_number() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    agents = AgentRegistry(definitions)
    tools = ToolRegistry(definitions)
    runtime = SharedAgentRuntime(agents, tools)
    plan = runtime.prepare(
        AgentRunRequest(
            agent_id="BCA",
            capability="check_budget_deterministically",
            execution_mode="DETERMINISTIC",
            input_references=["budget:synthetic"],
            requested_tools=["deterministic.calculator"],
            correlation_id="00000000-0000-0000-0000-000000000001",
            idempotency_key="invalid-number-safe-001",
        )
    )

    executed = runtime.execute(
        plan,
        {"amount": "bukan-angka", "available_amount": "Infinity"},
    )

    assert executed.execution is not None
    assert executed.execution.status == "NEEDS_REVIEW"
    assert executed.execution.verification_status == "PROVISIONAL"
    assert executed.execution.output_reference == {
        "database_verification_required": True
    }

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


def test_all_agent_capabilities_have_versioned_contracts_and_handlers() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    capabilities = CapabilityRegistry(definitions)
    contracts = capabilities.load_all()
    referenced = {
        capability
        for agent in AgentRegistry(definitions).load_all()
        for capability in agent.capabilities
    }

    assert len(contracts) == 61
    assert referenced == {item.capability_id for item in contracts}
    assert all(item.contract_digest for item in contracts)


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
        executed = runtime.execute(plan, {"data_classification": "INTERNAL"})

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

from pathlib import Path
from uuid import uuid4

import pytest

from alos.agents.registry import AgentRegistry
from alos.agents.runtime import AgentRunRequest, RuntimePolicyViolation, SharedAgentRuntime

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def runtime() -> SharedAgentRuntime:
    return SharedAgentRuntime(AgentRegistry(REPOSITORY_ROOT / "definitions"))


def test_runtime_prepares_allowed_agent_capability() -> None:
    plan = runtime().prepare(
        AgentRunRequest(
            agent_id="BCA",
            capability="check_budget_deterministically",
            input_references=["payment-request:synthetic-001"],
            requested_tools=["deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-001",
        )
    )

    assert plan.agent_id == "BCA"
    assert plan.status == "RECEIVED"


def test_runtime_blocks_tool_outside_agent_contract() -> None:
    with pytest.raises(RuntimePolicyViolation, match="Tool tidak diizinkan"):
        runtime().prepare(
            AgentRunRequest(
                agent_id="BCA",
                capability="check_budget_deterministically",
                input_references=["payment-request:synthetic-001"],
                requested_tools=["external.bank.transfer"],
                correlation_id=uuid4(),
                idempotency_key="pilot-payment-002",
            )
        )

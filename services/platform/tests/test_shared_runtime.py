from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from alos.agents.contract import AgentDefinition, AgentStatus, CapabilityExecutionMode
from alos.agents.registry import AgentRegistry
from alos.agents.runtime import (
    AgentRunRequest,
    CapabilityHandlerError,
    CapabilityHandlerOutput,
    CapabilityHandlerRegistry,
    RuntimePolicyViolation,
    SharedAgentRuntime,
)
from alos.tools import ToolRegistry
from alos.workflow.models import WorkflowStatus
from alos.workflow.registry import WorkflowRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def runtime() -> SharedAgentRuntime:
    definitions = REPOSITORY_ROOT / "definitions"
    return SharedAgentRuntime(AgentRegistry(definitions), ToolRegistry(definitions))


class StaticRegistry:
    def __init__(self, agent: AgentDefinition) -> None:
        self._agent = agent

    def get(self, agent_id: str, version: str | None = None) -> AgentDefinition:
        return self._agent


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
    assert plan.agent_version == "0.1.0"
    assert plan.contract_version == "1.0.0"
    assert plan.agent_kind == "CORE"
    assert plan.contract_snapshot.agent_id == "BCA"
    assert plan.contract_digest == plan.contract_snapshot.contract_digest
    assert plan.status == "RECEIVED"


def test_runtime_resolves_an_explicit_agent_version() -> None:
    plan = runtime().prepare(
        AgentRunRequest(
            agent_id="BCA",
            agent_version="0.1.0",
            capability="check_budget_deterministically",
            input_references=["payment-request:synthetic-versioned"],
            requested_tools=["deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-versioned",
        )
    )

    assert plan.agent_version == "0.1.0"


def test_runtime_normalizes_agent_id_for_backward_compatibility() -> None:
    plan = runtime().prepare(
        AgentRunRequest(
            agent_id="bca",
            capability="check_budget_deterministically",
            input_references=["payment-request:normalized-agent-id"],
            requested_tools=["deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-normalized",
        )
    )

    assert plan.agent_id == "BCA"


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


def test_runtime_marks_material_action_for_human_review() -> None:
    plan = runtime().prepare(
        AgentRunRequest(
            agent_id="CFA",
            capability="draft_customer_message",
            execution_mode=CapabilityExecutionMode.AI_ASSISTED,
            input_references=["lead:synthetic-001"],
            requested_tools=["ai.language.generate"],
            material_action=True,
            correlation_id=uuid4(),
            idempotency_key="pilot-follow-up-001",
        )
    )

    assert plan.requires_human_review is True


def test_runtime_blocks_contract_status_outside_pilot_release_gate() -> None:
    draft = AgentRegistry(REPOSITORY_ROOT / "definitions").get("BCA").model_copy(
        update={"status": AgentStatus.DRAFT}
    )
    draft_runtime = SharedAgentRuntime(
        cast(AgentRegistry, StaticRegistry(draft)),
        ToolRegistry(REPOSITORY_ROOT / "definitions"),
    )

    with pytest.raises(RuntimePolicyViolation, match="tidak dapat dijalankan"):
        draft_runtime.prepare(
            AgentRunRequest(
                agent_id="BCA",
                capability="check_budget_deterministically",
                input_references=["payment-request:draft-contract"],
                requested_tools=["deterministic.calculator"],
                correlation_id=uuid4(),
                idempotency_key="pilot-payment-draft",
            )
        )


def test_runtime_prepares_workflow_step_from_invocation_contract() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    workflow = WorkflowRegistry(definitions).get("FLOW-004")

    plans = runtime().prepare_workflow_step(
        workflow,
        "legal-analysis",
        ["legal-document:synthetic-001"],
        uuid4(),
        "legal-contract-synthetic-001",
        selector="CONTRACT",
    )

    assert len(plans) == 1
    assert plans[0].agent_id == "CLA"
    assert plans[0].capability == "extract_contract_clauses"
    assert plans[0].workflow_id == "FLOW-004"
    assert plans[0].workflow_step_id == "legal-analysis"
    assert plans[0].approved_tool_releases


def test_runtime_blocks_draft_workflow_even_when_agent_is_runnable() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    draft_workflow = WorkflowRegistry(definitions).get("FLOW-001").model_copy(
        update={"status": WorkflowStatus.DRAFT}
    )

    with pytest.raises(RuntimePolicyViolation, match="Workflow FLOW-001.*tidak dapat dijalankan"):
        runtime().prepare_workflow_step(
            draft_workflow,
            "lead-validation",
            ["lead-intake:draft-workflow"],
            uuid4(),
            "draft-workflow-test",
        )


def test_runtime_blocks_ai_tool_for_deterministic_request() -> None:
    with pytest.raises(RuntimePolicyViolation, match="tidak boleh memakai AI"):
        runtime().prepare(
            AgentRunRequest(
                agent_id="CFA",
                capability="draft_customer_message",
                input_references=["lead:synthetic-ai-policy"],
                requested_tools=["ai.language.generate"],
                correlation_id=uuid4(),
                idempotency_key="pilot-follow-up-ai-policy",
            )
        )


def test_runtime_dispatches_by_capability_without_agent_specific_branch() -> None:
    shared_runtime = runtime()
    plan = shared_runtime.prepare(
        AgentRunRequest(
            agent_id="BCA",
            capability="check_budget_deterministically",
            input_references=["payment-request:dispatch-test"],
            requested_tools=["deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-dispatch",
        )
    )
    handlers = CapabilityHandlerRegistry()
    handlers.register(
        "check_budget_deterministically",
        "finance.budget-check.v1",
        lambda prepared, payload: CapabilityHandlerOutput(
            output_reference={
                "amount": str(payload["amount"]),
                "available_amount": str(payload["available_amount"]),
                "available": True,
            },
            evidence_references=("budget-release:synthetic",),
        ),
    )

    result = shared_runtime.dispatch(
        plan,
        {"amount": 1_000_000, "available_amount": 2_000_000},
        handlers,
    )

    assert result.status == "COMPLETED"
    assert result.handler_id == "finance.budget-check.v1"
    assert result.output_reference["available"] is True


def test_runtime_rejects_dispatch_without_registered_capability_handler() -> None:
    plan = runtime().prepare(
        AgentRunRequest(
            agent_id="BCA",
            capability="check_budget_deterministically",
            input_references=["payment-request:no-handler"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-no-handler",
        )
    )

    with pytest.raises(CapabilityHandlerError, match="belum terdaftar"):
        runtime().dispatch(
            plan,
            {"amount": 1_000_000, "available_amount": 2_000_000},
            CapabilityHandlerRegistry(),
        )


def test_runtime_rejects_duplicate_tool_request() -> None:
    with pytest.raises(ValueError, match="duplikat"):
        AgentRunRequest(
            agent_id="BCA",
            capability="check_budget_deterministically",
            input_references=["payment-request:duplicate-tools"],
            requested_tools=["deterministic.calculator", "deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key="pilot-payment-duplicate-tools",
        )


def test_workflow_agent_idempotency_is_step_scoped_and_bounded() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    workflow = WorkflowRegistry(definitions).get("FLOW-001")
    long_key = "x" * 128

    plan = runtime().prepare_workflow_step(
        workflow,
        "lead-validation",
        ["lead-intake:bounded-idempotency"],
        uuid4(),
        long_key,
    )[0]

    assert len(plan.idempotency_key) <= 128
    assert plan.idempotency_key == runtime().prepare_workflow_step(
        workflow,
        "lead-validation",
        ["lead-intake:bounded-idempotency"],
        plan.correlation_id,
        long_key,
    )[0].idempotency_key

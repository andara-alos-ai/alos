from pathlib import Path

from alos.workflow.registry import WorkflowRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_registry_contains_the_six_required_pilot_workflow_graphs() -> None:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()

    assert {workflow.workflow_id for workflow in workflows} >= {
        "FLOW-006",
        "FLOW-001",
        "FLOW-002",
        "FLOW-004",
        "FLOW-005",
        "FLOW-003",
    }


def test_human_decisions_are_not_assigned_to_agents() -> None:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()

    decision_steps = [
        step for workflow in workflows for step in workflow.steps if step.requires_human_decision
    ]
    assert decision_steps
    assert all(step.actor_type == "human" for step in decision_steps)


def test_every_agent_step_has_registry_validated_invocation_contract() -> None:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()
    agent_steps = [
        step for workflow in workflows for step in workflow.steps if step.actor_type == "agent"
    ]

    assert agent_steps
    assert all(step.invocations for step in agent_steps)
    assert all(step.actor_ref != "LPA_OR_CLA" for step in agent_steps)


def test_legal_workflow_resolves_permit_and_contract_agents_without_placeholder() -> None:
    workflow = WorkflowRegistry(REPOSITORY_ROOT / "definitions").get("FLOW-004")

    assert workflow.resolve_invocations("legal-analysis", "PERMIT")[0].agent_id == "LPA"
    assert workflow.resolve_invocations("legal-analysis", "CONTRACT")[0].agent_id == "CLA"

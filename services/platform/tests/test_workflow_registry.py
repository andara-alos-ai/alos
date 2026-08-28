from pathlib import Path

from alos.workflow.registry import WorkflowRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_registry_contains_six_valid_workflow_graphs() -> None:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()

    assert [workflow.workflow_id for workflow in workflows] == [
        "FLOW-006",
        "FLOW-001",
        "FLOW-002",
        "FLOW-004",
        "FLOW-005",
        "FLOW-003",
    ]


def test_human_decisions_are_not_assigned_to_agents() -> None:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()

    decision_steps = [
        step for workflow in workflows for step in workflow.steps if step.requires_human_decision
    ]
    assert decision_steps
    assert all(step.actor_type == "human" for step in decision_steps)

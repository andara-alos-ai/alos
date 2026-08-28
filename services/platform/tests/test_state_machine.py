from pathlib import Path

import pytest

from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry
from alos.workflow.state_machine import InvalidTransition, StateMachine

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def payment_workflow() -> WorkflowDefinition:
    workflows = WorkflowRegistry(REPOSITORY_ROOT / "definitions").load_all()
    return next(item for item in workflows if item.workflow_id == "FLOW-002")


def test_payment_workflow_follows_defined_path() -> None:
    machine = StateMachine(payment_workflow())

    result = machine.transition("request-submitted", "submitted")

    assert result.current_step == "document-extraction"
    assert result.terminal is False


def test_payment_workflow_cannot_skip_to_approval() -> None:
    machine = StateMachine(payment_workflow())

    with pytest.raises(InvalidTransition):
        machine.transition("request-submitted", "approved")

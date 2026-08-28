from dataclasses import dataclass

from alos.workflow.models import WorkflowDefinition


class InvalidTransition(ValueError):
    """Raised when a deterministic workflow transition is not defined."""


@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous_step: str
    outcome: str
    current_step: str
    terminal: bool


class StateMachine:
    def __init__(self, definition: WorkflowDefinition) -> None:
        self._definition = definition
        self._transitions = {
            (transition.from_step, transition.outcome): transition.to_step
            for transition in definition.transitions
        }

    def transition(self, current_step: str, outcome: str) -> TransitionResult:
        try:
            next_step = self._transitions[(current_step, outcome)]
        except KeyError as exc:
            raise InvalidTransition(
                f"Transisi tidak diizinkan: {current_step} + {outcome}"
            ) from exc
        return TransitionResult(
            previous_step=current_step,
            outcome=outcome,
            current_step=next_step,
            terminal=next_step in self._definition.terminal_steps,
        )

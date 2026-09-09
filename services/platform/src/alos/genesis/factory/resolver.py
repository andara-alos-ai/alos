"""Deterministic implementation-type resolution from structured semantics."""

from typing import Literal

from alos.genesis.factory.models import (
    ImplementationDecision,
    ImplementationType,
    RequirementUnderstanding,
    TriggerKind,
)


class ImplementationTypeResolver:
    """Prefer reusable deterministic primitives and use AGENT only for reasoning."""

    def resolve(self, requirement: RequirementUnderstanding) -> ImplementationDecision:
        components = self._components(requirement)
        implementation_type = (
            components[0] if len(components) == 1 else ImplementationType.COMPOSITE
        )
        risk = self._risk(requirement)
        return ImplementationDecision(
            implementation_type=implementation_type,
            components=components if implementation_type == ImplementationType.COMPOSITE else (),
            reason=self._reason(requirement, components),
            required_capabilities=requirement.required_capabilities,
            required_data=requirement.required_data,
            risk=risk,
            human_gate_required=(
                bool(requirement.material_actions)
                or requirement.requires_human_judgment
                or risk in {"HIGH", "CRITICAL"}
            ),
        )

    @staticmethod
    def _components(requirement: RequirementUnderstanding) -> tuple[ImplementationType, ...]:
        selected: list[ImplementationType] = []
        if requirement.deterministic_constraints:
            selected.append(ImplementationType.RULE)
        if requirement.requires_validation:
            selected.append(ImplementationType.VALIDATOR)
        if requirement.requires_research:
            selected.append(ImplementationType.REPORT)
        if requirement.requires_reasoning:
            selected.append(ImplementationType.AGENT)
        if requirement.material_actions or len(requirement.desired_outputs) > 1:
            selected.append(ImplementationType.WORKFLOW)
        if requirement.requires_human_judgment:
            selected.append(ImplementationType.HUMAN_TASK)
        if requirement.trigger_kind == TriggerKind.SCHEDULED:
            selected.append(ImplementationType.SCHEDULE)
        elif requirement.trigger_kind == TriggerKind.EVENT:
            selected.append(ImplementationType.EVENT_HANDLER)
        if not selected:
            selected.append(
                ImplementationType.SKILL
                if requirement.required_capabilities
                else ImplementationType.HUMAN_TASK
            )
        return tuple(dict.fromkeys(selected))

    @staticmethod
    def _risk(
        requirement: RequirementUnderstanding,
    ) -> Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        if requirement.requires_human_judgment and requirement.material_actions:
            return "HIGH"
        if requirement.material_actions:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _reason(
        requirement: RequirementUnderstanding,
        components: tuple[ImplementationType, ...],
    ) -> str:
        labels = ", ".join(component.value for component in components)
        if ImplementationType.AGENT not in components:
            return f"Capability-first resolution selected {labels}; autonomous reasoning is absent."
        return (
            f"Capability-first resolution selected {labels}; an Agent is limited to the "
            "reasoning portion while deterministic controls remain separate."
        )

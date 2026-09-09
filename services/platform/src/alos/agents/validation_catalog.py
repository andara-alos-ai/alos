"""The three MVP1 validation agents as generic Agent Contract inputs.

These definitions are not separate services.  They are low-risk, read-only
logical agents that are created in the same Registry as every future agent.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict
from uuid import UUID

from alos.agents.registry import AgentBuilderRequest


class _ValidationControls(TypedDict):
    risk_level: Literal["LOW"]
    model_policy: dict[str, Any]
    tool_keys: list[str]
    permission_keys: list[str]
    approval_required: bool
    timeout_seconds: int
    data_classification: Literal["INTERNAL"]
    forbidden_actions: list[str]
    kpis: list[dict[str, Any]]


def validation_agent_requests(workspace_id: UUID) -> tuple[AgentBuilderRequest, ...]:
    """Return the human-controlled fields for the MVP1 validation agents."""
    controls: _ValidationControls = {
        "risk_level": "LOW",
        # Provider routing remains server-side.  This contract deliberately
        # omits a provider so the staging Model Gateway can apply its approved
        # environment route without exposing a credential or vendor control to
        # the browser.
        "model_policy": {
            "usage": "controlled_pilot",
            "model_route": "light",
            "max_output_tokens": 1200,
        },
        "tool_keys": ["SOURCE_REGISTRY_SEARCH"],
        "permission_keys": ["SOURCE_READ_INTERNAL"],
        "approval_required": True,
        "timeout_seconds": 120,
        "data_classification": "INTERNAL",
        "forbidden_actions": [
            (
                "Do not write data, contact external parties, spend funds, "
                "change production, or create tools."
            )
        ],
        "kpis": [{"name": "citation_coverage", "target": 1}],
    }
    return (
        AgentBuilderRequest(
            workspace_id=workspace_id,
            agent_key="DAILY_BRIEF",
            name="Daily Brief Agent",
            objective=(
                "Prepare a concise read-only daily operational brief from registered sources, "
                "highlighting priority items, open risks, and evidence citations."
            ),
            input_schema={
                "type": "object",
                "properties": {"as_of_date": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["summary", "highlights", "citations"],
                "properties": {
                    "summary": {"type": "string"},
                    "highlights": {"type": "array"},
                    "citations": {"type": "array"},
                },
            },
            **controls,
        ),
        AgentBuilderRequest(
            workspace_id=workspace_id,
            agent_key="EVIDENCE_CHECKER",
            name="Evidence Checker Agent",
            objective=(
                "Assess a stated internal claim against registered evidence, identify gaps or "
                "conflicts, and return a read-only cited assessment."
            ),
            input_schema={
                "type": "object",
                "required": ["claim"],
                "properties": {"claim": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["assessment", "gaps", "citations"],
                "properties": {
                    "assessment": {"type": "string"},
                    "gaps": {"type": "array"},
                    "citations": {"type": "array"},
                },
            },
            **controls,
        ),
        AgentBuilderRequest(
            workspace_id=workspace_id,
            agent_key="PERMIT_OVERDUE_MONITOR",
            name="Permit/Overdue Monitor Agent",
            objective=(
                "Monitor registered permit or deadline records for due-soon, overdue, and "
                "blocked conditions; return a read-only cited alert summary."
            ),
            input_schema={
                "type": "object",
                "properties": {"as_of_date": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["summary", "alerts", "citations"],
                "properties": {
                    "summary": {"type": "string"},
                    "alerts": {"type": "array"},
                    "citations": {"type": "array"},
                },
            },
            **controls,
        ),
    )

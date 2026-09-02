from pathlib import Path

from alos.agents.registry import AgentRegistry
from alos.tools import ToolEffect, ToolRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_tool_registry_covers_every_agent_allow_list() -> None:
    definitions = REPOSITORY_ROOT / "definitions"
    tools = ToolRegistry(definitions)
    registered = {tool.tool_id for tool in tools.load_all()}
    referenced = {
        tool_id
        for agent in AgentRegistry(definitions, tools).load_all()
        for tool_id in agent.tools_allowed
    }

    assert len(registered) == 3
    assert referenced == registered


def test_validation_tools_are_read_only_and_deterministic_safe() -> None:
    tools = ToolRegistry(REPOSITORY_ROOT / "definitions").load_all()

    assert all(tool.effect == ToolEffect.READ_ONLY for tool in tools)
    assert all(tool.allowed_in_deterministic_steps for tool in tools)

from pathlib import Path

from alos.agents.registry import AgentRegistry
from alos.tools import ToolEffect, ToolKind, ToolRegistry

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

    assert len(registered) == 38
    assert referenced == registered


def test_ai_tools_are_never_allowed_in_deterministic_steps() -> None:
    tools = ToolRegistry(REPOSITORY_ROOT / "definitions").load_all()
    ai_tools = [tool for tool in tools if tool.kind == ToolKind.AI_PROVIDER]

    assert ai_tools
    assert all(tool.effect == ToolEffect.AI_ASSISTED for tool in ai_tools)
    assert all(not tool.allowed_in_deterministic_steps for tool in ai_tools)

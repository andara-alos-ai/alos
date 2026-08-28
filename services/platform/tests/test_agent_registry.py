from pathlib import Path

from alos.agents.registry import AgentRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_registry_contains_exactly_18_unique_core_agents() -> None:
    agents = AgentRegistry(REPOSITORY_ROOT / "definitions").load_all()

    assert len(agents) == 18
    assert len({agent.agent_id for agent in agents}) == 18


def test_it_is_not_business_owner_of_all_agents() -> None:
    agents = AgentRegistry(REPOSITORY_ROOT / "definitions").load_all()

    assert all(agent.human_owner != "Divisi IT" for agent in agents)

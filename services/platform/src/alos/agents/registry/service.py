import json
from pathlib import Path

from alos.agents.contract import AgentDefinition


class RegistryError(ValueError):
    """Raised when the versioned agent registry is invalid."""


class AgentRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._definitions_root = definitions_root

    def load_all(self) -> tuple[AgentDefinition, ...]:
        files = sorted((self._definitions_root / "agents" / "core").glob("*/agent.json"))
        agents = tuple(self._load_file(path) for path in files)
        self._validate_registry(agents)
        return agents

    def get(self, agent_id: str) -> AgentDefinition:
        normalized = agent_id.upper()
        for agent in self.load_all():
            if agent.agent_id == normalized:
                return agent
        raise KeyError(normalized)

    @staticmethod
    def _load_file(path: Path) -> AgentDefinition:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return AgentDefinition.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RegistryError(f"Definisi agent tidak valid: {path}: {exc}") from exc

    @staticmethod
    def _validate_registry(agents: tuple[AgentDefinition, ...]) -> None:
        if len(agents) != 18:
            raise RegistryError(
                f"Registry wajib berisi tepat 18 Core Agent; ditemukan {len(agents)}"
            )
        ids = [agent.agent_id for agent in agents]
        if len(ids) != len(set(ids)):
            raise RegistryError("agent_id harus unik")

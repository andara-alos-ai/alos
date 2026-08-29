import json
from collections.abc import Callable
from pathlib import Path

from alos.agents.contract import AgentDefinition, AgentKind, AgentStatus
from alos.tools import ToolRegistry, ToolRegistryError

CORE_AGENT_IDS = frozenset(
    {
        "MCA",
        "DIA",
        "SEA",
        "CEA",
        "KDA",
        "ARA",
        "CRA",
        "FRA",
        "BCA",
        "TIA",
        "SLA",
        "MCA_MKT",
        "CFA",
        "TPA",
        "HRA",
        "HPA",
        "LPA",
        "CLA",
    }
)

AgentKey = tuple[str, str]


class RegistryError(ValueError):
    """Raised when the versioned agent registry is invalid."""


class AgentRegistry:
    def __init__(
        self, definitions_root: Path, tool_registry: ToolRegistry | None = None
    ) -> None:
        self._definitions_root = definitions_root
        self._tool_registry = tool_registry or ToolRegistry(definitions_root)
        self._cache: tuple[AgentDefinition, ...] | None = None

    def load_all(self, *, force_reload: bool = False) -> tuple[AgentDefinition, ...]:
        """Load every versioned Core, Sub-Agent, and Sub-Sub-Agent definition."""

        if self._cache is not None and not force_reload:
            return self._cache

        files = sorted((self._definitions_root / "agents").rglob("agent.json"))
        if not files:
            raise RegistryError(f"Tidak ada definisi agent di {self._definitions_root / 'agents'}")
        agents = tuple(self._load_file(path) for path in files)
        self._validate_registry(agents)
        try:
            for agent in agents:
                self._tool_registry.validate_allowed_tools(agent.tools_allowed)
        except ToolRegistryError as exc:
            raise RegistryError(f"Referensi Tool Registry tidak valid: {exc}") from exc
        self._cache = tuple(
            sorted(agents, key=lambda item: (item.agent_id, self._semantic_version(item.version)))
        )
        return self._cache

    def refresh(self) -> tuple[AgentDefinition, ...]:
        """Explicitly reload the design-time registry from disk."""

        return self.load_all(force_reload=True)

    def validate_candidate(self, candidate: AgentDefinition) -> None:
        """Validate a design-time candidate without writing it to the registry."""

        agents = (*self.load_all(), candidate)
        self._validate_registry(agents)
        try:
            self._tool_registry.validate_allowed_tools(candidate.tools_allowed)
        except ToolRegistryError as exc:
            raise RegistryError(f"Referensi Tool Registry tidak valid: {exc}") from exc

    def load_core(self) -> tuple[AgentDefinition, ...]:
        """Return the latest contract for each of the 18 baseline Core Agent identities."""

        agents = self.load_all()
        self.validate_core_baseline(agents)
        latest: dict[str, AgentDefinition] = {}
        for agent in agents:
            if agent.agent_kind != AgentKind.CORE:
                continue
            current = latest.get(agent.agent_id)
            if current is None or self._semantic_version(agent.version) > self._semantic_version(
                current.version
            ):
                latest[agent.agent_id] = agent
        return tuple(latest[agent_id] for agent_id in sorted(latest))

    def get(self, agent_id: str, version: str | None = None) -> AgentDefinition:
        normalized = agent_id.upper()
        matches = [agent for agent in self.load_all() if agent.agent_id == normalized]
        if version is not None:
            for agent in matches:
                if agent.version == version:
                    return agent
            raise KeyError(f"{normalized}@{version}")
        if not matches:
            raise KeyError(normalized)
        return max(matches, key=lambda item: self._semantic_version(item.version))

    def find(
        self,
        *,
        kind: AgentKind | None = None,
        domain: str | None = None,
        status: AgentStatus | None = None,
    ) -> tuple[AgentDefinition, ...]:
        agents = self.load_all()
        return tuple(
            agent
            for agent in agents
            if (kind is None or agent.agent_kind == kind)
            and (domain is None or agent.domain == domain)
            and (status is None or agent.status == status)
        )

    @staticmethod
    def _load_file(path: Path) -> AgentDefinition:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return AgentDefinition.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RegistryError(f"Definisi agent tidak valid: {path}: {exc}") from exc

    @classmethod
    def _validate_registry(cls, agents: tuple[AgentDefinition, ...]) -> None:
        index: dict[AgentKey, AgentDefinition] = {}
        for agent in agents:
            key = (agent.agent_id, agent.version)
            if key in index:
                raise RegistryError(
                    f"Kombinasi agent_id dan version harus unik: {agent.agent_id}@{agent.version}"
                )
            index[key] = agent

        for key, agent in index.items():
            cls._validate_parent(key, agent, index)
            if agent.extends is not None:
                target = (agent.extends.agent_id, agent.extends.version)
                if target not in index:
                    raise RegistryError(
                        f"extends {target[0]}@{target[1]} untuk {agent.agent_id}@{agent.version} "
                        "tidak ditemukan"
                    )

        cls._assert_acyclic(
            index,
            lambda agent: (
                (agent.parent_agent_id, agent.parent_agent_version)
                if agent.parent_agent_id is not None and agent.parent_agent_version is not None
                else None
            ),
            "parent",
        )
        cls._assert_acyclic(
            index,
            lambda agent: (
                (agent.extends.agent_id, agent.extends.version)
                if agent.extends is not None
                else None
            ),
            "extends",
        )

    @staticmethod
    def validate_core_baseline(agents: tuple[AgentDefinition, ...]) -> None:
        core_ids = {agent.agent_id for agent in agents if agent.agent_kind == AgentKind.CORE}
        missing = sorted(CORE_AGENT_IDS - core_ids)
        unexpected = sorted(core_ids - CORE_AGENT_IDS)
        if missing or unexpected:
            raise RegistryError(
                "Baseline Core Agent tidak sesuai; "
                f"missing={missing or '[]'}, unexpected={unexpected or '[]'}"
            )

    @staticmethod
    def _validate_parent(
        key: AgentKey,
        agent: AgentDefinition,
        index: dict[AgentKey, AgentDefinition],
    ) -> None:
        if agent.agent_kind == AgentKind.CORE:
            return
        if agent.parent_agent_id is None or agent.parent_agent_version is None:
            raise RegistryError(f"Metadata parent untuk {key[0]}@{key[1]} tidak lengkap")
        parent_key = (agent.parent_agent_id, agent.parent_agent_version)
        if parent_key not in index:
            raise RegistryError(
                f"Parent {parent_key[0]}@{parent_key[1]} untuk {key[0]}@{key[1]} tidak ditemukan"
            )
        parent = index[parent_key]
        expected_kind = (
            AgentKind.CORE if agent.agent_kind == AgentKind.SUB_AGENT else AgentKind.SUB_AGENT
        )
        if parent.agent_kind != expected_kind:
            raise RegistryError(
                f"Parent {parent.agent_id}@{parent.version} untuk {agent.agent_kind} "
                f"wajib berjenis {expected_kind}"
            )

    @staticmethod
    def _assert_acyclic(
        index: dict[AgentKey, AgentDefinition],
        edge: Callable[[AgentDefinition], AgentKey | None],
        relationship: str,
    ) -> None:
        visited: set[AgentKey] = set()
        active: set[AgentKey] = set()

        def visit(key: AgentKey) -> None:
            if key in active:
                raise RegistryError(f"Siklus {relationship} terdeteksi pada {key[0]}@{key[1]}")
            if key in visited:
                return
            active.add(key)
            target = edge(index[key])
            if target is not None:
                visit(target)
            active.remove(key)
            visited.add(key)

        for key in index:
            visit(key)

    @staticmethod
    def _semantic_version(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

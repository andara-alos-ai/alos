import json
from collections.abc import Callable
from pathlib import Path

from alos.agents.capabilities import CapabilityRegistry, CapabilityRegistryError
from alos.agents.contract import AgentDefinition, AgentKind, AgentReference, AgentStatus
from alos.agents.contract.policies import ContractPolicyRegistry
from alos.llm import PromptRegistry
from alos.tools import ToolRegistry, ToolRegistryError

# Kept only for the legacy controlled-pilot validator. Runtime discovery is
# registry-driven and must not depend on a fixed taxonomy or agent count.
LEGACY_CORE_AGENT_IDS = frozenset(
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
# Backward-compatible import for existing tooling. It is intentionally not
# consulted by runtime discovery; new code should not depend on this constant.
CORE_AGENT_IDS = LEGACY_CORE_AGENT_IDS

AgentKey = tuple[str, str]


class RegistryError(ValueError):
    """Raised when the versioned agent registry is invalid."""


class AgentRegistry:
    def __init__(
        self, definitions_root: Path, tool_registry: ToolRegistry | None = None
    ) -> None:
        self._definitions_root = definitions_root
        self._tool_registry = tool_registry or ToolRegistry(definitions_root)
        self._capability_registry = CapabilityRegistry(definitions_root)
        self._prompt_registry = PromptRegistry(definitions_root)
        self._policy_registry = ContractPolicyRegistry(definitions_root)
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
                if self._capability_registry.exists:
                    self._capability_registry.validate_references(agent.capabilities)
                self._validate_logical_configuration(agent)
        except ToolRegistryError as exc:
            raise RegistryError(f"Referensi Tool Registry tidak valid: {exc}") from exc
        except CapabilityRegistryError as exc:
            raise RegistryError(f"Referensi Capability Registry tidak valid: {exc}") from exc
        self._cache = tuple(
            sorted(agents, key=lambda item: (item.agent_id, self._semantic_version(item.version)))
        )
        return self._cache

    def refresh(self) -> tuple[AgentDefinition, ...]:
        """Explicitly reload the design-time registry from disk."""

        return self.load_all(force_reload=True)

    @property
    def definitions_root(self) -> Path:
        """Root containing versioned definitions; never contains credentials."""

        return self._definitions_root

    def release_generated(self, candidate: AgentDefinition) -> AgentDefinition:
        """Materialize a human-approved Genesis candidate in the shared registry.

        The registry is the only definition source consulted by the runtime. A
        generated release is immutable by identity and version; a different
        payload for the same identity/version is rejected instead of replaced.
        """

        if candidate.status != AgentStatus.DRAFT:
            raise RegistryError("Genesis hanya dapat merilis candidate berstatus DRAFT")
        self.validate_candidate(candidate)
        released = candidate.model_copy(update={"status": AgentStatus.RELEASED})
        path = self._generated_path(released.agent_id, released.version)
        if path.exists():
            existing = self._load_file(path)
            if existing.contract_digest != released.contract_digest:
                raise RegistryError(
                    "Version Agent Contract sudah ada dengan payload berbeda: "
                    f"{released.agent_id}@{released.version}"
                )
            return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(released.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._cache = None
        return released

    def activate_generated(self, agent_id: str, version: str) -> AgentDefinition:
        """Make one generated version active and retire a previously active version.

        An Agent Registry identity represents one logical agent.  Only one
        version of that identity may be ACTIVE at a time, so activation remains
        deterministic and rollback always has an unambiguous target.
        """

        current = self._load_generated(agent_id, version)
        if current.status not in {AgentStatus.RELEASED, AgentStatus.SUSPENDED}:
            raise RegistryError(
                f"Transition {current.status} -> {AgentStatus.ACTIVE} tidak diizinkan untuk "
                f"{current.agent_id}@{current.version}"
            )
        generated_root = self._generated_path(current.agent_id, version).parents[1]
        if generated_root.exists():
            for path in generated_root.glob("*/agent.json"):
                sibling = self._load_file(path)
                if sibling.version != current.version and sibling.status == AgentStatus.ACTIVE:
                    self._write_generated(
                        sibling.model_copy(update={"status": AgentStatus.ROLLED_BACK})
                    )
        return self._transition_generated(agent_id, version, AgentStatus.ACTIVE)

    def suspend_generated(self, agent_id: str, version: str) -> AgentDefinition:
        return self._transition_generated(agent_id, version, AgentStatus.SUSPENDED)

    def rollback_generated(
        self,
        agent_id: str,
        version: str,
        rollback_target: AgentReference,
    ) -> AgentDefinition:
        current = self._load_generated(agent_id, version)
        if current.status not in {AgentStatus.ACTIVE, AgentStatus.SUSPENDED}:
            raise RegistryError("Rollback hanya dapat dilakukan dari agent ACTIVE atau SUSPENDED")
        target = self._load_generated(rollback_target.agent_id, rollback_target.version)
        if target.agent_id != current.agent_id or target.version == current.version:
            raise RegistryError("Rollback wajib menargetkan versi lain dari agent yang sama")
        if self._semantic_version(target.version) >= self._semantic_version(current.version):
            raise RegistryError("Rollback target wajib merupakan versi yang lebih lama")
        if target.status not in {
            AgentStatus.RELEASED,
            AgentStatus.SUSPENDED,
            AgentStatus.ROLLED_BACK,
        }:
            raise RegistryError(
                "Rollback target harus merupakan generated release yang dapat dipulihkan"
            )
        self._write_generated(current.model_copy(update={"status": AgentStatus.ROLLED_BACK}))
        restored = target.model_copy(update={"status": AgentStatus.ACTIVE})
        self._write_generated(restored)
        self._cache = None
        return restored

    def validate_candidate(self, candidate: AgentDefinition) -> None:
        """Validate a design-time candidate without writing it to the registry."""

        agents = (*self.load_all(), candidate)
        self._validate_registry(agents)
        try:
            self._tool_registry.validate_allowed_tools(candidate.tools_allowed)
            if self._capability_registry.exists:
                self._capability_registry.validate_references(candidate.capabilities)
            self._validate_logical_configuration(candidate)
        except ToolRegistryError as exc:
            raise RegistryError(f"Referensi Tool Registry tidak valid: {exc}") from exc
        except CapabilityRegistryError as exc:
            raise RegistryError(f"Referensi Capability Registry tidak valid: {exc}") from exc

    def load_core(self) -> tuple[AgentDefinition, ...]:
        """Return the latest contract for every top-level agent.

        ``CORE`` is a hierarchy level, not a permanent list of identities.
        Genesis may add another top-level agent after the normal validation,
        review, staging, and release gates. The old fixed 18-agent check is
        intentionally not part of runtime loading.
        """

        agents = self.load_all()
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

    def load_top_level(self) -> tuple[AgentDefinition, ...]:
        """Return the latest version of each top-level agent identity."""

        return self.load_core()

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
        return max(
            matches,
            key=lambda item: (
                self._status_priority(item.status),
                self._semantic_version(item.version),
            ),
        )

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
        """Validate the historical 18-agent pilot baseline explicitly.

        This method is retained for audit/backward compatibility only. It is
        never called by runtime discovery, because the active taxonomy is
        intentionally extensible through Genesis.
        """

        core_ids = {agent.agent_id for agent in agents if agent.agent_kind == AgentKind.CORE}
        missing = sorted(LEGACY_CORE_AGENT_IDS - core_ids)
        unexpected = sorted(core_ids - LEGACY_CORE_AGENT_IDS)
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
        if agent.agent_kind == AgentKind.LOGICAL and (
            agent.parent_agent_id is None or agent.parent_agent_version is None
        ):
            return
        if agent.parent_agent_id is None or agent.parent_agent_version is None:
            raise RegistryError(f"Metadata parent untuk {key[0]}@{key[1]} tidak lengkap")
        parent_key = (agent.parent_agent_id, agent.parent_agent_version)
        if parent_key not in index:
            raise RegistryError(
                f"Parent {parent_key[0]}@{parent_key[1]} untuk {key[0]}@{key[1]} tidak ditemukan"
            )
        parent = index[parent_key]
        if agent.agent_kind == AgentKind.LOGICAL:
            return
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

    @staticmethod
    def _status_priority(status: AgentStatus) -> int:
        """Prefer the currently active contract when no version was requested."""

        return {
            AgentStatus.ACTIVE: 9,
            AgentStatus.RELEASED: 8,
            AgentStatus.STAGED: 7,
            AgentStatus.TESTED: 6,
            AgentStatus.REVIEWED: 5,
            AgentStatus.VALIDATED: 4,
            AgentStatus.DRAFT: 3,
            AgentStatus.SUSPENDED: 2,
            AgentStatus.ROLLED_BACK: 1,
            AgentStatus.DEPRECATED: 0,
            AgentStatus.RETIRED: -1,
        }[status]

    def _generated_path(self, agent_id: str, version: str) -> Path:
        return self._definitions_root / "agents" / "generated" / agent_id / version / "agent.json"

    def _validate_logical_configuration(self, agent: AgentDefinition) -> None:
        if agent.agent_kind != AgentKind.LOGICAL:
            return
        if (
            agent.prompt_ref is None
            or agent.model_policy_ref is None
            or agent.permission_policy_ref is None
        ):
            raise RegistryError("Logical Agent wajib memiliki configuration reference")
        prompt_id, separator, prompt_version = agent.prompt_ref.rpartition("@")
        if not separator or not prompt_id or not prompt_version:
            raise RegistryError(f"Prompt reference tidak versioned: {agent.prompt_ref}")
        try:
            self._prompt_registry.get(prompt_id, prompt_version)
            self._policy_registry.validate(agent.model_policy_ref, agent.permission_policy_ref)
            permission = self._policy_registry.permission_policy(agent.permission_policy_ref)
            disallowed = [
                tool_id
                for tool_id in agent.tools_allowed
                if self._tool_registry.get(tool_id).effect.value
                not in permission.allowed_tool_effects
            ]
            if disallowed:
                raise ValueError(
                    f"Permission policy menolak effect tool: {sorted(disallowed)}"
                )
        except (KeyError, ValueError) as exc:
            raise RegistryError(f"Configuration reference tidak valid: {exc}") from exc

    def _load_generated(self, agent_id: str, version: str) -> AgentDefinition:
        path = self._generated_path(agent_id.upper(), version)
        if not path.exists():
            raise RegistryError(f"Generated Agent Contract tidak ditemukan: {agent_id}@{version}")
        return self._load_file(path)

    def _transition_generated(
        self, agent_id: str, version: str, target_status: AgentStatus
    ) -> AgentDefinition:
        current = self._load_generated(agent_id, version)
        allowed = {
            AgentStatus.ACTIVE: {AgentStatus.RELEASED, AgentStatus.SUSPENDED},
            AgentStatus.SUSPENDED: {AgentStatus.ACTIVE, AgentStatus.RELEASED},
        }
        if current.status not in allowed[target_status]:
            raise RegistryError(
                f"Transition {current.status} -> {target_status} tidak diizinkan untuk "
                f"{current.agent_id}@{current.version}"
            )
        updated = current.model_copy(update={"status": target_status})
        self._write_generated(updated)
        self._cache = None
        return updated

    def _write_generated(self, definition: AgentDefinition) -> None:
        path = self._generated_path(definition.agent_id, definition.version)
        if not path.exists():
            raise RegistryError("Hanya definition generated yang dapat diubah lifecycle-nya")
        path.write_text(
            json.dumps(definition.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

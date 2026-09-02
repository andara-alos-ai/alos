import json
from pathlib import Path

import pytest

from alos.agents.contract import AgentDefinition, AgentKind, AgentStatus
from alos.agents.registry import CORE_AGENT_IDS, AgentRegistry, RegistryError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _definition(
    agent_id: str,
    kind: str,
    *,
    version: str = "1.0.0",
    parent: tuple[str, str] | None = None,
    extends: tuple[str, str] | None = None,
    status: str = "STAGED",
) -> dict[str, object]:
    return {
        "contract_version": "1.0.0",
        "agent_id": agent_id,
        "name": f"{agent_id} Test Agent",
        "agent_kind": kind,
        "parent_agent_id": parent[0] if parent else None,
        "parent_agent_version": parent[1] if parent else None,
        "extends": (
            {"agent_id": extends[0], "version": extends[1]} if extends is not None else None
        ),
        "domain": "synthetic-test",
        "purpose": "Menjalankan pengujian kontrak agent sintetis secara aman.",
        "human_owner": "Pemilik Bisnis Pengujian",
        "triggers": ["Permintaan pengujian"],
        "inputs": ["Data sintetis"],
        "source_of_truth": ["Fixture pengujian"],
        "capabilities": ["validate_synthetic_input"],
        "outputs": ["Hasil pengujian"],
        "tools_allowed": ["synthetic.read"],
        "approval_boundary": ["Tindakan material wajib direview"],
        "evidence_requirement": ["Referensi fixture wajib tersedia"],
        "forbidden_actions": ["Mengakses data produksi"],
        "metrics": ["Validitas kontrak"],
        "escalation": ["Kontrak tidak valid"],
        "version": version,
        "status": status,
    }


def _write_definition(root: Path, relative: str, payload: dict[str, object]) -> None:
    tools_path = root / "tools" / "registry.json"
    if not tools_path.exists():
        tools_path.parent.mkdir(parents=True, exist_ok=True)
        tools_path.write_text(
            json.dumps(
                [
                    {
                        "contract_version": "1.0.0",
                        "tool_id": "synthetic.read",
                        "name": "Baca Sintetis",
                        "purpose": "Membaca data sintetis untuk pengujian kontrak.",
                        "kind": "INTERNAL",
                        "effect": "READ_ONLY",
                        "credential_mode": "EXECUTION_CONTEXT",
                        "allowed_in_deterministic_steps": True,
                        "timeout_seconds": 5,
                        "max_attempts": 1,
                        "version": "1.0.0",
                        "status": "STAGED",
                    }
                ]
            ),
            encoding="utf-8",
        )
    path = root / "agents" / relative / "agent.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_registry_keeps_legacy_core_contracts_without_fixed_total() -> None:
    registry = AgentRegistry(REPOSITORY_ROOT / "definitions")
    agents = registry.load_all()
    core_agents = registry.load_core()

    assert len(core_agents) == 18
    assert {agent.agent_id for agent in core_agents} == CORE_AGENT_IDS
    assert all(agent.agent_kind == AgentKind.CORE for agent in core_agents)
    assert all(agent.contract_version == "1.0.0" for agent in core_agents)
    assert all(agent.parent_agent_id is None for agent in core_agents)
    assert len(agents) >= len(core_agents)
    assert any(agent.agent_kind == AgentKind.LOGICAL for agent in agents)


def test_it_is_not_business_owner_of_all_agents() -> None:
    agents = AgentRegistry(REPOSITORY_ROOT / "definitions").load_core()

    assert all(agent.human_owner != "Divisi IT" for agent in agents)


def test_registry_loads_valid_core_sub_and_sub_sub_hierarchy(tmp_path: Path) -> None:
    _write_definition(tmp_path, "core/TEST_CORE", _definition("TEST_CORE", "CORE"))
    _write_definition(
        tmp_path,
        "sub/TEST_SUB",
        _definition(
            "TEST_SUB",
            "SUB_AGENT",
            parent=("TEST_CORE", "1.0.0"),
            extends=("TEST_CORE", "1.0.0"),
        ),
    )
    _write_definition(
        tmp_path,
        "sub-sub/TEST_TASK",
        _definition(
            "TEST_TASK",
            "SUB_SUB_AGENT",
            parent=("TEST_SUB", "1.0.0"),
            extends=("TEST_SUB", "1.0.0"),
        ),
    )

    registry = AgentRegistry(tmp_path)

    assert len(registry.load_all()) == 3
    assert registry.get("test_sub").agent_kind == AgentKind.SUB_AGENT
    assert len(registry.find(kind=AgentKind.SUB_SUB_AGENT)) == 1


def test_registry_accepts_additional_top_level_agent_without_fixed_count(
    tmp_path: Path,
) -> None:
    _write_definition(tmp_path, "generated/NEW_TOP_LEVEL", _definition("NEW_TOP_LEVEL", "CORE"))

    registry = AgentRegistry(tmp_path)

    assert [agent.agent_id for agent in registry.load_top_level()] == ["NEW_TOP_LEVEL"]


def test_registry_resolves_exact_or_latest_semantic_version(tmp_path: Path) -> None:
    _write_definition(
        tmp_path,
        "core/TEST_CORE/1.0.0",
        _definition("TEST_CORE", "CORE", version="1.0.0"),
    )
    _write_definition(
        tmp_path,
        "core/TEST_CORE/1.10.0",
        _definition("TEST_CORE", "CORE", version="1.10.0"),
    )
    registry = AgentRegistry(tmp_path)

    assert registry.get("TEST_CORE").version == "1.10.0"
    assert registry.get("TEST_CORE", "1.0.0").version == "1.0.0"


def test_registry_rejects_invalid_parent_kind(tmp_path: Path) -> None:
    _write_definition(tmp_path, "core/TEST_CORE", _definition("TEST_CORE", "CORE"))
    _write_definition(
        tmp_path,
        "sub-sub/TEST_TASK",
        _definition(
            "TEST_TASK",
            "SUB_SUB_AGENT",
            parent=("TEST_CORE", "1.0.0"),
        ),
    )

    with pytest.raises(RegistryError, match="wajib berjenis SUB_AGENT"):
        AgentRegistry(tmp_path).load_all()


def test_registry_rejects_unknown_extends_reference(tmp_path: Path) -> None:
    _write_definition(tmp_path, "core/TEST_CORE", _definition("TEST_CORE", "CORE"))
    _write_definition(
        tmp_path,
        "sub/TEST_SUB",
        _definition(
            "TEST_SUB",
            "SUB_AGENT",
            parent=("TEST_CORE", "1.0.0"),
            extends=("UNKNOWN_AGENT", "1.0.0"),
        ),
    )

    with pytest.raises(RegistryError, match="tidak ditemukan"):
        AgentRegistry(tmp_path).load_all()


def test_registry_rejects_extends_cycle(tmp_path: Path) -> None:
    _write_definition(tmp_path, "core/TEST_CORE", _definition("TEST_CORE", "CORE"))
    _write_definition(
        tmp_path,
        "sub/TEST_SUB_A",
        _definition(
            "TEST_SUB_A",
            "SUB_AGENT",
            parent=("TEST_CORE", "1.0.0"),
            extends=("TEST_SUB_B", "1.0.0"),
        ),
    )
    _write_definition(
        tmp_path,
        "sub/TEST_SUB_B",
        _definition(
            "TEST_SUB_B",
            "SUB_AGENT",
            parent=("TEST_CORE", "1.0.0"),
            extends=("TEST_SUB_A", "1.0.0"),
        ),
    )

    with pytest.raises(RegistryError, match="Siklus extends"):
        AgentRegistry(tmp_path).load_all()


def test_registry_rejects_duplicate_agent_version(tmp_path: Path) -> None:
    payload = _definition("TEST_CORE", "CORE")
    _write_definition(tmp_path, "core/TEST_CORE/first", payload)
    _write_definition(tmp_path, "core/TEST_CORE/second", payload)

    with pytest.raises(RegistryError, match="harus unik"):
        AgentRegistry(tmp_path).load_all()


def test_contract_digest_is_stable_for_equivalent_payload_order() -> None:
    payload = _definition("TEST_CORE", "CORE")
    first = AgentDefinition.model_validate(payload)
    second = AgentDefinition.model_validate(dict(reversed(tuple(payload.items()))))

    assert first.contract_digest == second.contract_digest
    assert first.contract_digest == first.model_copy(
        update={"status": AgentStatus.RELEASED}
    ).contract_digest
    assert len(first.contract_digest) == 64
    assert first.status == AgentStatus.STAGED


def test_published_json_schema_matches_runtime_contract() -> None:
    schema_path = REPOSITORY_ROOT / "definitions" / "schemas" / "agent-contract.schema.json"
    published = json.loads(schema_path.read_text(encoding="utf-8"))

    assert published.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert published.pop("$id").endswith("agent-contract-1.0.0.schema.json")
    assert published == AgentDefinition.model_json_schema()

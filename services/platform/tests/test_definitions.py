import json
from pathlib import Path


def test_agent_contract_schema_declares_hari_1_governance_fields() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    schema_path = repository_root / "definitions" / "contracts" / "agent-contract.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["required"]) >= {
        "agent_key",
        "risk_level",
        "tool_keys",
        "permission_keys",
        "evidence_requirements",
        "forbidden_actions",
        "kpis",
    }

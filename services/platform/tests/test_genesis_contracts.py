from alos.genesis import AgentContract, validate_agent_contract


def _contract(**overrides: object) -> dict:
    base: dict[str, object] = {
        "agent_key": "GEN_VAL_EVIDENCE_CHECKER",
        "name": "Evidence Checker Agent",
        "purpose": "Memeriksa kelengkapan evidence sebuah record",
        "risk_level": "MEDIUM",
        "input_schema": {"required": ["record_id"]},
        "output_schema": {"required": ["result"]},
        "model_policy": {"primary": "local"},
        "tool_keys": ["READ_EVIDENCE"],
        "permission_keys": ["EVIDENCE_READ"],
        "evidence_requirements": ["record_id", "source"],
        "forbidden_actions": [
            "SELF_APPROVE",
            "TRANSFER_FUNDS",
            "FINAL_LEGAL_DECISION",
            "MUTATE_VERIFIED_RECORD",
            "PRODUCTION_DEPLOY",
        ],
        "kpis": [{"key": "coverage", "target": 0.95}],
        "parent_agent_key": None,
    }
    base.update(overrides)
    return base


def test_valid_contract_has_no_violations() -> None:
    assert validate_agent_contract(AgentContract(**_contract())) == []


def test_bad_agent_key_is_rejected() -> None:
    violations = validate_agent_contract(_contract(agent_key="lowercase"))
    assert any(v.code == "AGENT_KEY_FORMAT" for v in violations)


def test_contract_without_boundary_is_rejected() -> None:
    violations = validate_agent_contract(_contract(forbidden_actions=[]))
    codes = {v.code for v in violations}
    assert "NO_BOUNDARY" in codes
    assert "SELF_APPROVE_MISSING" in codes


def test_self_approve_must_be_forbidden() -> None:
    violations = validate_agent_contract(_contract(forbidden_actions=["TRANSFER_FUNDS"]))
    assert any(v.code == "SELF_APPROVE_MISSING" for v in violations)


def test_high_risk_requires_evidence() -> None:
    violations = validate_agent_contract(
        _contract(risk_level="CRITICAL", evidence_requirements=[])
    )
    assert any(v.code == "HIGH_RISK_EVIDENCE" for v in violations)


def test_duplicate_tools_are_rejected() -> None:
    violations = validate_agent_contract(
        _contract(tool_keys=["READ_EVIDENCE", "READ_EVIDENCE"])
    )
    assert any(v.code == "DUPLICATE" for v in violations)


def test_human_authority_actions_cannot_be_omitted() -> None:
    violations = validate_agent_contract(
        _contract(forbidden_actions=["SELF_APPROVE"])
    )
    assert any(v.code == "GUARDRAIL_MISSING" for v in violations)

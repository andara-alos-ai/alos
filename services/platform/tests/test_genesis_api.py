from uuid import uuid4

from fastapi.testclient import TestClient

from alos.main import app

client = TestClient(app)

_CONTRACT_BASE: dict[str, object] = {
    "name": "Evidence Checker Agent",
    "purpose": "Memeriksa kelengkapan evidence sebuah record",
    "risk_level": "MEDIUM",
    "input_schema": {"required": ["record_id"]},
    "output_schema": {"required": ["result"]},
    "model_policy": {"primary": "local"},
    "tool_keys": ["READ_EVIDENCE", "CREATE_DRAFT"],
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


def _token(roles: list[str], divisions: list[str] | None = None) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/local-token",
        json={
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "roles": roles,
            "division_codes": divisions or [],
            "workspace_ids": [],
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _draft(headers: dict[str, str], agent_key: str) -> None:
    response = client.post(
        "/api/v1/genesis/agents",
        headers=headers,
        json={"agent_key": agent_key, **_CONTRACT_BASE},
    )
    assert response.status_code == 201, response.text


def test_genesis_requires_authentication() -> None:
    assert client.get("/api/v1/genesis/agents").status_code == 401


def test_full_lifecycle_draft_to_active() -> None:
    maker = _token(["IT_LEAD"])
    tech = _token(["TECHNICAL_REVIEWER"])
    business = _token(["BUSINESS_REVIEWER"])
    activator = _token(["DIRECTOR"])
    key = "GEN_TEST_LIFECYCLE"

    _draft(maker, key)

    # Maker cannot review their own agent (SoD).
    client.post(f"/api/v1/genesis/agents/{key}/submit", headers=maker)
    self_review = client.post(
        f"/api/v1/genesis/agents/{key}/reviews",
        headers=maker,
        json={"gate": "TECHNICAL", "decision": "APPROVED", "notes": "self"},
    )
    assert self_review.status_code == 403
    assert self_review.json()["detail"]["code"] == "SOD_VIOLATION"

    # Independent technical + business reviews.
    tech_review = client.post(
        f"/api/v1/genesis/agents/{key}/reviews",
        headers=tech,
        json={"gate": "TECHNICAL", "decision": "APPROVED", "notes": "ok"},
    )
    assert tech_review.status_code == 200
    assert client.post(
        f"/api/v1/genesis/agents/{key}/reviews",
        headers=business,
        json={"gate": "BUSINESS", "decision": "APPROVED", "notes": "ok"},
    ).status_code == 200

    # Activation requires a privileged role.
    activated = client.post(f"/api/v1/genesis/agents/{key}/activate", headers=activator)
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"


def test_invalid_contract_is_rejected() -> None:
    maker = _token(["IT_LEAD"])
    # Well-formed request body, but a contract with no governance boundary.
    bad = {**_CONTRACT_BASE, "agent_key": "GEN_TEST_BAD_CONTRACT", "forbidden_actions": []}
    response = client.post("/api/v1/genesis/agents", headers=maker, json=bad)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CONTRACT_INVALID"


def test_live_run_blocked_until_active_and_tools_guarded() -> None:
    maker = _token(["IT_LEAD"])
    key = "GEN_TEST_RUN_GUARD"
    _draft(maker, key)

    # A live run on a DRAFT agent is blocked.
    live = client.post(
        f"/api/v1/genesis/agents/{key}/runs",
        headers=maker,
        json={"mode": "live", "requested_tools": ["READ_EVIDENCE"], "budget_usd": 100},
    )
    assert live.status_code == 403
    assert live.json()["detail"]["code"] == "RUN_BLOCKED"

    # Tool guardrail denies forbidden/unregistered tools even in test mode.
    checked = client.post(
        f"/api/v1/genesis/agents/{key}/tool-check",
        headers=maker,
        json={"tool_keys": ["READ_EVIDENCE", "TRANSFER_FUNDS", "HACK_TOOL"]},
    )
    assert checked.status_code == 200
    by_tool = {d["tool_key"]: d["decision"] for d in checked.json()["decisions"]}
    assert by_tool["READ_EVIDENCE"] == "ALLOW"
    assert by_tool["TRANSFER_FUNDS"] == "DENY"
    assert by_tool["HACK_TOOL"] == "DENY"

    # Test-mode run with a denied tool is recorded as BLOCKED.
    blocked_run = client.post(
        f"/api/v1/genesis/agents/{key}/runs",
        headers=maker,
        json={
            "mode": "test",
            "requested_tools": ["READ_EVIDENCE", "TRANSFER_FUNDS"],
            "budget_usd": 100,
            "estimated_run_usd": 1,
        },
    )
    assert blocked_run.status_code == 200
    assert blocked_run.json()["status"] == "BLOCKED"
    assert "TRANSFER_FUNDS" in blocked_run.json()["blocked_tools"]


def test_budget_hard_stop_blocks_run() -> None:
    maker = _token(["IT_LEAD"])
    key = "GEN_TEST_BUDGET"
    _draft(maker, key)
    response = client.post(
        f"/api/v1/genesis/agents/{key}/runs",
        headers=maker,
        json={
            "mode": "test",
            "requested_tools": ["READ_EVIDENCE"],
            "budget_usd": 10,
            "estimated_run_usd": 15,  # would cross the 10 cap
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["budget_state"] == "HARD_STOP_100"


def test_no_source_output_is_labelled_ai_inferred() -> None:
    maker = _token(["IT_LEAD"])
    key = "GEN_TEST_SOURCE_LABEL"
    _draft(maker, key)
    response = client.post(
        f"/api/v1/genesis/agents/{key}/runs",
        headers=maker,
        json={
            "mode": "test",
            "requested_tools": ["READ_EVIDENCE"],
            "has_cited_source": False,
            "evidence_present": True,
            "budget_usd": 100,
            "estimated_run_usd": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCEEDED"
    assert response.json()["source_status"] == "AI_INFERRED"

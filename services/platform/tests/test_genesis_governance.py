from alos.genesis import (
    BudgetState,
    Decision,
    SourceStatus,
    ToolDecision,
    decide_activation,
    decide_budget,
    evaluate_tools,
    label_source,
    lifecycle_next,
    review_decision,
    validate_hierarchy,
)

FORBIDDEN = ["SELF_APPROVE", "TRANSFER_FUNDS", "PRODUCTION_DEPLOY"]


# --- UAT-02: hierarchy ------------------------------------------------------
def test_unknown_parent_is_rejected() -> None:
    problems = validate_hierarchy("CHILD", {"CHILD": "MISSING_PARENT"})
    assert any("tidak terdaftar" in p for p in problems)


def test_circular_parent_is_rejected() -> None:
    parent_map = {"A": "B", "B": "A"}
    problems = validate_hierarchy("A", parent_map)
    assert any("sirkular" in p for p in problems)


def test_root_and_valid_chain_are_accepted() -> None:
    assert validate_hierarchy("MCA", {"MCA": None, "CHILD": "MCA"}) == []


# --- UAT lifecycle ----------------------------------------------------------
def test_lifecycle_happy_path_and_illegal_jump() -> None:
    assert lifecycle_next("DRAFT", "VALIDATED")
    assert lifecycle_next("VALIDATED", "TESTED")
    assert lifecycle_next("TESTED", "IN_REVIEW")
    assert lifecycle_next("IN_REVIEW", "APPROVED")
    # DRAFT cannot jump straight to ACTIVE
    assert not lifecycle_next("DRAFT", "ACTIVE")
    assert not lifecycle_next("RETIRED", "ACTIVE")


# --- UAT-04: segregation of duties -----------------------------------------
def test_self_approval_is_denied() -> None:
    assert review_decision("user-1", "user-1") is Decision.DENY


def test_distinct_reviewer_is_allowed() -> None:
    assert review_decision("maker", "qa-reviewer") is Decision.ALLOW


# --- UAT-03/07: tool guardrail ---------------------------------------------
def test_unregistered_and_forbidden_tools_are_denied() -> None:
    decisions = evaluate_tools(
        requested_tools=["READ_EVIDENCE", "TRANSFER_FUNDS", "HACK_TOOL"],
        allowed_tools=["READ_EVIDENCE", "TRANSFER_FUNDS", "HACK_TOOL"],
        forbidden_actions=FORBIDDEN,
        registered_tools=["READ_EVIDENCE"],
    )
    by_key = {d.tool_key: d for d in decisions}
    assert isinstance(by_key["READ_EVIDENCE"], ToolDecision)
    assert by_key["READ_EVIDENCE"].decision is Decision.ALLOW
    assert by_key["TRANSFER_FUNDS"].decision is Decision.DENY
    assert by_key["HACK_TOOL"].decision is Decision.DENY


def test_tool_not_in_allowlist_is_denied() -> None:
    (decision,) = evaluate_tools(
        requested_tools=["SEND_EMAIL"],
        allowed_tools=[],
        forbidden_actions=FORBIDDEN,
        registered_tools=["SEND_EMAIL"],
    )
    assert decision.decision is Decision.DENY


# --- UAT-09: budget gates ---------------------------------------------------
def test_budget_alert_and_hard_stop_states() -> None:
    assert decide_budget(50, 100) is BudgetState.OK
    assert decide_budget(75, 100) is BudgetState.ALERT_70
    assert decide_budget(95, 100) is BudgetState.ALERT_90
    assert decide_budget(100, 100) is BudgetState.HARD_STOP_100


def test_run_that_would_cross_budget_is_stopped() -> None:
    # 95 spent + 10 estimated would cross the 100 cap -> hard stop
    assert decide_budget(95, 100, estimated_run_usd=10) is BudgetState.HARD_STOP_100


# --- UAT-06: source labelling ----------------------------------------------
def test_no_source_output_is_ai_inferred() -> None:
    assert label_source(has_cited_source=False, evidence_present=True) is SourceStatus.AI_INFERRED
    assert label_source(has_cited_source=True, evidence_present=True) is SourceStatus.SUPPORTED
    assert label_source(has_cited_source=True, evidence_present=False) is SourceStatus.NEEDS_REVIEW


# --- UAT-15/05: activation gate --------------------------------------------
def test_high_risk_agent_requires_verified_evidence_to_activate() -> None:
    assert (
        decide_activation("HIGH", "APPROVED", evidence_verified=False, kill_switch_active=False)
        is Decision.DENY
    )
    assert (
        decide_activation("HIGH", "APPROVED", evidence_verified=True, kill_switch_active=False)
        is Decision.ALLOW
    )


def test_kill_switch_blocks_activation() -> None:
    assert (
        decide_activation("LOW", "RELEASED", evidence_verified=True, kill_switch_active=True)
        is Decision.DENY
    )


def test_draft_cannot_activate() -> None:
    assert (
        decide_activation("LOW", "DRAFT", evidence_verified=True, kill_switch_active=False)
        is Decision.DENY
    )

"""GENESIS runtime governance rules (H3/H4/H5).

Pure functions implementing the operational guardrails: lifecycle state
machine, segregation of duties, tool allowlist, cost gates, source labelling,
hierarchy cycle detection, and the HIGH/CRITICAL activation gate.
"""
from dataclasses import dataclass
from enum import StrEnum

from alos.genesis.catalog import LIFECYCLE_STATES

# --- Lifecycle (agents.versions.lifecycle_status) ---------------------------
# Allowed forward transitions. REJECTED/RETURNED drafts go back to DRAFT.
_LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"VALIDATED", "RETIRED"}),
    "VALIDATED": frozenset({"TESTED", "DRAFT"}),
    "TESTED": frozenset({"IN_REVIEW", "DRAFT"}),
    "IN_REVIEW": frozenset({"APPROVED", "DRAFT", "ROLLED_BACK"}),
    "APPROVED": frozenset({"STAGED", "ACTIVE", "DRAFT"}),
    "STAGED": frozenset({"RELEASED", "ROLLED_BACK", "SUSPENDED"}),
    "RELEASED": frozenset({"ACTIVE", "ROLLED_BACK", "SUSPENDED"}),
    "ACTIVE": frozenset({"SUSPENDED", "RETIRED"}),
    "SUSPENDED": frozenset({"ACTIVE", "RETIRED", "ROLLED_BACK"}),
    "ROLLED_BACK": frozenset({"DRAFT", "RETIRED"}),
    "RETIRED": frozenset(),
}


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


def lifecycle_next(current: str, target: str) -> bool:
    """True if `current -> target` is a permitted lifecycle transition."""
    if current not in LIFECYCLE_STATES or target not in LIFECYCLE_STATES:
        return False
    return target in _LIFECYCLE_TRANSITIONS.get(current, frozenset())


# --- Segregation of duties --------------------------------------------------
def review_decision(requester_user_id: str, reviewer_user_id: str) -> Decision:
    """UAT-04: a maker must not approve their own change (SoD)."""
    if not requester_user_id or not reviewer_user_id:
        return Decision.DENY
    return Decision.ALLOW if requester_user_id != reviewer_user_id else Decision.DENY


# --- Hierarchy --------------------------------------------------------------
def validate_hierarchy(child_key: str, parent_keys: dict[str, str | None]) -> list[str]:
    """Reject unknown or circular parents.

    `parent_keys` maps agent_key -> parent_agent_key (None or 'GENESIS'/'MCA'
    marks a root). Returns a list of problems; empty means the hierarchy is sound.
    """
    problems: list[str] = []
    for key, parent in parent_keys.items():
        if parent in (None, "MCA", "GENESIS"):
            continue
        if parent not in parent_keys:
            problems.append(f"{key}: parent '{parent}' tidak terdaftar")
            continue
        seen = {key}
        cursor: str | None = parent
        depth = 0
        while (
            cursor is not None
            and cursor not in ("MCA", "GENESIS")
            and depth <= len(parent_keys) + 1
        ):
            node: str = cursor
            if node in seen:
                problems.append(f"{key}: hierarki sirkular terdeteksi via '{node}'")
                break
            seen.add(node)
            cursor = parent_keys.get(node)
            depth += 1
    return problems


# --- Tool guardrail ---------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ToolDecision:
    tool_key: str
    decision: Decision
    reason: str


def evaluate_tools(
    requested_tools: list[str],
    allowed_tools: list[str],
    forbidden_actions: list[str],
    registered_tools: list[str],
) -> list[ToolDecision]:
    """UAT-03/07: allow only registered tools that are in the contract
    allowlist and are not forbidden. Anything else is denied and auditable."""
    allowed = {t.upper() for t in allowed_tools}
    registered = {t.upper() for t in registered_tools}
    forbidden = {a.upper() for a in forbidden_actions}
    decisions: list[ToolDecision] = []
    for tool in requested_tools:
        key = tool.upper()
        if key in forbidden:
            decisions.append(ToolDecision(key, Decision.DENY, "forbidden action on contract"))
        elif key not in allowed:
            decisions.append(ToolDecision(key, Decision.DENY, "not in agent allowlist"))
        elif key not in registered:
            decisions.append(ToolDecision(key, Decision.DENY, "tool not registered"))
        else:
            decisions.append(ToolDecision(key, Decision.ALLOW, "registered and permitted"))
    return decisions


# --- Cost gate --------------------------------------------------------------
class BudgetState(StrEnum):
    OK = "OK"
    ALERT_70 = "ALERT_70"
    ALERT_90 = "ALERT_90"
    HARD_STOP_100 = "HARD_STOP_100"


def decide_budget(
    spent_usd: float, budget_usd: float, estimated_run_usd: float = 0.0
) -> BudgetState:
    """UAT-09: 70/90 alerts and a hard stop at 100% (or if a run would cross it)."""
    if budget_usd <= 0:
        return BudgetState.HARD_STOP_100
    projected = spent_usd + estimated_run_usd
    if spent_usd >= budget_usd or projected > budget_usd:
        return BudgetState.HARD_STOP_100
    pct = spent_usd / budget_usd
    if pct >= 0.90:
        return BudgetState.ALERT_90
    if pct >= 0.70:
        return BudgetState.ALERT_70
    return BudgetState.OK


# --- Source labelling -------------------------------------------------------
class SourceStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    AI_INFERRED = "AI_INFERRED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


def label_source(has_cited_source: bool, evidence_present: bool) -> SourceStatus:
    """UAT-06: output without a citable source is labelled AI-inferred;
    missing evidence routes to review instead of silently passing."""
    if has_cited_source and evidence_present:
        return SourceStatus.SUPPORTED
    if evidence_present:
        return SourceStatus.AI_INFERRED
    return SourceStatus.NEEDS_REVIEW


# --- Activation gate --------------------------------------------------------
def decide_activation(
    risk_level: str,
    lifecycle_status: str,
    evidence_verified: bool,
    kill_switch_active: bool,
) -> Decision:
    """UAT-15/05: an agent may go ACTIVE only after release, with verified
    evidence for HIGH/CRITICAL, and never while a kill switch is set."""
    if kill_switch_active:
        return Decision.DENY
    if lifecycle_status not in {"APPROVED", "STAGED", "RELEASED"}:
        return Decision.DENY
    if risk_level in {"HIGH", "CRITICAL"} and not evidence_verified:
        return Decision.DENY
    return Decision.ALLOW

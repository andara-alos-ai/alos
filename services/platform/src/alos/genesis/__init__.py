"""GENESIS domain rules.

Pure, dependency-free control-plane rules for the shared Agent Runtime. This
package deliberately contains *policy*, not persistence: every function takes
plain values and returns decisions/violations so the same rules can be used by
the API layer, the runtime, and the UAT suite without a live database.

Coverage of the GENESIS MVP-1 gates:

* agent contract validation (H1/H2)
* parent/child hierarchy with circular-parent rejection (H2)
* lifecycle state machine DRAFT -> ... -> ACTIVE/SUSPENDED/RETIRED (H2/H4)
* segregation of duties: self-approval is forbidden (H4)
* tool allowlist / forbidden-action guardrail (H3)
* cost budget gates 70/90/100 with hard stop (H3)
* source labelling: no-source output is AI-inferred (H3)
* activation gate for HIGH/CRITICAL risk (H4/H5)
"""
from alos.genesis.catalog import (
    FORBIDDEN_ACTIONS,
    RISK_LEVELS,
    VALIDATION_AGENT_KEYS,
)
from alos.genesis.contracts import (
    AgentContract,
    ContractViolation,
    validate_agent_contract,
)
from alos.genesis.governance import (
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

__all__ = [
    "FORBIDDEN_ACTIONS",
    "RISK_LEVELS",
    "VALIDATION_AGENT_KEYS",
    "AgentContract",
    "ContractViolation",
    "validate_agent_contract",
    "BudgetState",
    "Decision",
    "SourceStatus",
    "ToolDecision",
    "decide_activation",
    "decide_budget",
    "evaluate_tools",
    "label_source",
    "lifecycle_next",
    "review_decision",
    "validate_hierarchy",
]

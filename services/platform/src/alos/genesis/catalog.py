"""Static catalog values for GENESIS MVP-1.

These mirror the check constraints in migrations 001/002 so the domain rules
and the database agree. Keeping them in one place prevents drift between the
policy layer and infra/database.
"""

# Risk levels accepted on agent contracts (agents.contracts.risk_level).
RISK_LEVELS: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})

# Lifecycle states for an agent version (agents.versions.lifecycle_status).
LIFECYCLE_STATES: frozenset[str] = frozenset(
    {
        "DRAFT",
        "VALIDATED",
        "TESTED",
        "IN_REVIEW",
        "APPROVED",
        "STAGED",
        "RELEASED",
        "ACTIVE",
        "SUSPENDED",
        "ROLLED_BACK",
        "RETIRED",
    }
)

# Source/output provenance labels surfaced to reviewers.
SOURCE_STATUSES: frozenset[str] = frozenset(
    {"SUPPORTED", "AI_INFERRED", "UNSUPPORTED", "NEEDS_REVIEW"}
)

# Actions no agent contract may ever permit (forbidden on every contract).
# These are irreversible / human-authority actions per the MVP-1 scope freeze.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "TRANSFER_FUNDS",
        "CHANGE_BANK_ACCOUNT",
        "SIGN_CONTRACT",
        "FINAL_LEGAL_DECISION",
        "HIRE_OR_FIRE",
        "MUTATE_VERIFIED_RECORD",
        "DELETE_EVIDENCE",
        "SELF_APPROVE",
        "AUTO_ACTIVATE_HIGH_RISK",
        "PRODUCTION_DEPLOY",
    }
)

# The three Hari-5 validation agents, created through the same GENESIS engine.
# Keys follow the agent-contract pattern ^[A-Z][A-Z0-9_]{2,79}$.
VALIDATION_AGENT_KEYS: frozenset[str] = frozenset(
    {
        "GEN_VAL_DAILY_BRIEF",
        "GEN_VAL_EVIDENCE_CHECKER",
        "GEN_VAL_PERMIT_OVERDUE_MONITOR",
    }
)

"""Hari-1 seed: the three validation agents.

These are the three read-first validation agents named in the MVP-1 scope
freeze. They are created **through the same GENESIS engine** as any other
agent (``GenesisService.draft_agent``), so they start life as ``DRAFT``
contracts and must still pass the independent technical + business review and
human activation gates. Seeding them never bypasses segregation of duties.

The seed is idempotent: agents that already exist in the registry are left
untouched, so it is safe to call at process start-up or from a test.
"""

from alos.genesis.catalog import VALIDATION_AGENT_KEYS
from alos.genesis.contracts import AgentContract
from alos.genesis.service import Actor, GenesisService
from alos.genesis.store import AgentRecord

# Genesis is a system actor, not a division and not a human role. It drafts the
# baseline contracts; a human reviewer/approver remains mandatory downstream.
GENESIS_SYSTEM_ACTOR = Actor(
    user_id="00000000-0000-0000-0000-000000000000",
    organization_id="00000000-0000-0000-0000-000000000000",
    roles=frozenset({"IT_LEAD"}),
)

# Every validation agent is read-first and may never take an irreversible or
# human-authority action. We declare the full forbidden-action boundary.
_GUARDRAILS: list[str] = [
    "SELF_APPROVE",
    "TRANSFER_FUNDS",
    "CHANGE_BANK_ACCOUNT",
    "SIGN_CONTRACT",
    "FINAL_LEGAL_DECISION",
    "HIRE_OR_FIRE",
    "MUTATE_VERIFIED_RECORD",
    "DELETE_EVIDENCE",
    "AUTO_ACTIVATE_HIGH_RISK",
    "PRODUCTION_DEPLOY",
]

_MODEL_POLICY: dict[str, object] = {
    "routing": "genesis-model-gateway",
    "primary_provider": "openai",
    "notes": "provider/model di-resolve dari ALOS_LLM_* saat aktivasi",
}

_VALIDATION_AGENTS: tuple[AgentContract, ...] = (
    AgentContract(
        agent_key="GEN_VAL_DAILY_BRIEF",
        name="Daily Brief Agent",
        purpose=(
            "Menyusun ringkasan harian lintas divisi secara read-only dari Source "
            "Registry; hanya membuat draf (CREATE_DRAFT) dan tidak mengambil tindakan."
        ),
        risk_level="MEDIUM",
        input_schema={"type": "object", "required": ["division_codes", "date"]},
        output_schema={
            "type": "object",
            "required": ["brief", "citations", "evidence_status"],
        },
        model_policy=_MODEL_POLICY,
        tool_keys=["READ_EVIDENCE", "READ_BANK", "READ_PAYMENT", "READ_PROPERTY", "CREATE_DRAFT"],
        permission_keys=["SOURCE_READ", "BRIEF_DRAFT"],
        evidence_requirements=["cited_source", "division_scope"],
        forbidden_actions=_GUARDRAILS,
        kpis=[{"name": "citation_coverage", "target": ">= 0.95"}],
        parent_agent_key=None,
    ),
    AgentContract(
        agent_key="GEN_VAL_EVIDENCE_CHECKER",
        name="Evidence Checker Agent",
        purpose=(
            "Memverifikasi klaim/citation terhadap bukti di Source Registry dan "
            "melabeli provenance (SUPPORTED/AI_INFERRED/NEEDS_REVIEW); read-only."
        ),
        risk_level="MEDIUM",
        input_schema={"type": "object", "required": ["claim", "candidate_sources"]},
        output_schema={
            "type": "object",
            "required": ["claim", "source_status", "evidence_status"],
        },
        model_policy=_MODEL_POLICY,
        tool_keys=["READ_EVIDENCE", "SEND_NOTIFICATION"],
        permission_keys=["SOURCE_READ", "EVIDENCE_REVIEW"],
        evidence_requirements=["cited_source", "hash_match"],
        forbidden_actions=_GUARDRAILS,
        kpis=[{"name": "unsupported_claim_flagging", "target": ">= 0.99"}],
        parent_agent_key=None,
    ),
    AgentContract(
        agent_key="GEN_VAL_PERMIT_OVERDUE_MONITOR",
        name="Permit & Overdue Monitor Agent",
        purpose=(
            "Memantau jatuh tempo dokumen/izin dan menaikkan eskalasi via notifikasi; "
            "read-only dan tidak mengubah record terverifikasi."
        ),
        risk_level="MEDIUM",
        input_schema={"type": "object", "required": ["division_code", "as_of_date"]},
        output_schema={
            "type": "object",
            "required": ["overdue_items", "escalations", "evidence_status"],
        },
        model_policy=_MODEL_POLICY,
        tool_keys=["READ_PROPERTY", "READ_EVIDENCE", "SEND_NOTIFICATION"],
        permission_keys=["SOURCE_READ", "ESCALATION_NOTIFY"],
        evidence_requirements=["cited_source", "due_date_reference"],
        forbidden_actions=_GUARDRAILS,
        kpis=[{"name": "overdue_detection_recall", "target": ">= 0.98"}],
        parent_agent_key=None,
    ),
)


def seed_validation_agents(
    service: GenesisService,
    *,
    actor: Actor = GENESIS_SYSTEM_ACTOR,
) -> list[AgentRecord]:
    """Draft the three validation agents if they are not already registered.

    Returns the records for every validation agent (existing or newly drafted).
    Existing agents are never overwritten, so calling this repeatedly is safe.
    """
    existing = {agent.agent_key: agent for agent in service.list_agents()}
    records: list[AgentRecord] = []
    for contract in _VALIDATION_AGENTS:
        record = existing.get(contract.agent_key)
        if record is None:
            record = service.draft_agent(contract, actor)
        records.append(record)
    return records


def validation_agent_keys() -> frozenset[str]:
    """Expose the canonical keys (mirrors ``catalog.VALIDATION_AGENT_KEYS``)."""
    return VALIDATION_AGENT_KEYS

"""GENESIS application service.

Applies the pure domain rules (``alos.genesis.governance`` / ``contracts``)
onto the in-memory registry and models the maker -> reviewer -> approver flow
with actor (JWT) identity. A Postgres adapter can replace ``InMemoryGenesisStore``
without touching this layer.
"""
from dataclasses import dataclass
from uuid import uuid4

from alos.genesis.contracts import AgentContract, ContractViolation, validate_agent_contract
from alos.genesis.governance import (
    BudgetState,
    Decision,
    ToolDecision,
    decide_activation,
    decide_budget,
    evaluate_tools,
    label_source,
    lifecycle_next,
    review_decision,
    validate_hierarchy,
)
from alos.genesis.store import (
    AgentRecord,
    InMemoryGenesisStore,
    ReviewRecord,
    RunRecord,
)

# Roles permitted to perform each action (Segregation of Duties).
_REVIEW_TECH_ROLES = {"IT_LEAD", "TECHNICAL_REVIEWER", "QA_SECURITY"}
_REVIEW_BUSINESS_ROLES = {"DIRECTOR", "DIVISION_OWNER", "BUSINESS_REVIEWER"}
_APPROVE_ROLES = {"DIRECTOR", "IT_LEAD"}

# Read-only/standard tools available in local/staging by default.
def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_str_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


_DEFAULT_REGISTERED_TOOLS = {
    "READ_EVIDENCE",
    "READ_BANK",
    "READ_PAYMENT",
    "READ_PROPERTY",
    "SEND_NOTIFICATION",
    "CREATE_DRAFT",
}


class GenesisError(Exception):
    """Mapped to an HTTP error by the router."""

    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    organization_id: str
    roles: frozenset[str]


class GenesisService:
    def __init__(self, store: InMemoryGenesisStore) -> None:
        self._store = store
        for tool in _DEFAULT_REGISTERED_TOOLS:
            store.register_tool(tool)

    # --- agent factory ------------------------------------------------------
    def draft_agent(self, contract: AgentContract, actor: Actor) -> AgentRecord:
        violations: list[ContractViolation] = validate_agent_contract(contract)
        if violations:
            raise GenesisError(
                "CONTRACT_INVALID",
                "; ".join(f"[{v.code}] {v.message}" for v in violations),
            )
        if self._store.get(contract.agent_key) is not None:
            raise GenesisError("AGENT_EXISTS", f"agent {contract.agent_key} sudah ada", 409)
        # Hierarchy: parent must exist or be a known root.
        parent_map: dict[str, str | None] = {
            a.agent_key: _optional_str(a.current.contract.get("parent_agent_key"))
            for a in self._store.list_agents()
        }
        parent_map.setdefault(contract.agent_key, contract.parent_agent_key)
        problems = validate_hierarchy(contract.agent_key, parent_map)
        if problems:
            raise GenesisError("HIERARCHY_INVALID", "; ".join(problems))
        return self._store.add_agent(contract, actor.user_id, actor.organization_id)

    def get_agent(self, agent_key: str) -> AgentRecord:
        record = self._store.get(agent_key)
        if record is None:
            raise GenesisError("AGENT_NOT_FOUND", f"agent {agent_key} tidak ditemukan", 404)
        return record

    def list_agents(self) -> list[AgentRecord]:
        return self._store.list_agents()

    def submit_for_review(self, agent_key: str, actor: Actor) -> AgentRecord:
        record = self.get_agent(agent_key)
        # Walk DRAFT -> VALIDATED -> TESTED -> IN_REVIEW using the state machine.
        for target in ("VALIDATED", "TESTED", "IN_REVIEW"):
            current = record.current.lifecycle_status
            if not lifecycle_next(current, target):
                if current == target:
                    continue
                raise GenesisError(
                    "LIFECYCLE_ILLEGAL",
                    f"tidak dapat berpindah {current} -> {target}",
                )
            record = self._store.transition(agent_key, target)
        return record

    # --- review / approval --------------------------------------------------
    def review(
        self, agent_key: str, gate: str, decision: str, notes: str, actor: Actor
    ) -> ReviewRecord:
        record = self.get_agent(agent_key)
        if record.current.lifecycle_status != "IN_REVIEW":
            raise GenesisError(
                "NOT_IN_REVIEW",
                f"agent berstatus {record.current.lifecycle_status}; harus IN_REVIEW",
            )
        allowed_roles = _REVIEW_TECH_ROLES if gate == "TECHNICAL" else _REVIEW_BUSINESS_ROLES
        if not actor.roles.intersection(allowed_roles):
            raise GenesisError("FORBIDDEN_ROLE", f"peran tidak berwenang untuk gate {gate}", 403)
        # UAT-04: maker cannot be checker.
        if review_decision(record.owner_user_id, actor.user_id) is Decision.DENY:
            raise GenesisError("SOD_VIOLATION", "maker tidak boleh menjadi reviewer (SoD)", 403)
        if decision not in {"APPROVED", "REJECTED"}:
            raise GenesisError("BAD_DECISION", "keputusan harus APPROVED/REJECTED")
        return self._store.add_review(agent_key, actor.user_id, gate, decision, notes)

    def activate(self, agent_key: str, actor: Actor) -> AgentRecord:
        record = self.get_agent(agent_key)
        if not actor.roles.intersection(_APPROVE_ROLES):
            raise GenesisError(
                "FORBIDDEN_ROLE",
                "hanya DIRECTOR/IT_LEAD yang dapat mengaktifkan",
                403,
            )
        # Both gates must be approved before activation.
        reviews = self._store.reviews_for(agent_key)
        approved_gates = {r.gate for r in reviews if r.decision == "APPROVED"}
        if not {"TECHNICAL", "BUSINESS"}.issubset(approved_gates):
            raise GenesisError(
                "REVIEW_INCOMPLETE",
                "aktivasi butuh review APPROVED pada gate TECHNICAL dan BUSINESS",
            )
        if lifecycle_next(record.current.lifecycle_status, "APPROVED"):
            record = self._store.transition(agent_key, "APPROVED")
        if decide_activation(
            risk_level=str(record.current.contract.get("risk_level")),
            lifecycle_status=record.current.lifecycle_status,
            evidence_verified=record.evidence_verified,
            kill_switch_active=record.kill_switch,
        ) is Decision.DENY:
            raise GenesisError(
                "ACTIVATION_DENIED",
                "aktivasi ditolak: perlu status rilis, evidence terverifikasi "
                "(HIGH/CRITICAL), dan tanpa kill switch",
            )
        return self._store.transition(agent_key, "ACTIVE")

    def verify_evidence(self, agent_key: str, verified: bool, actor: Actor) -> AgentRecord:
        self.get_agent(agent_key)
        if not actor.roles.intersection(_REVIEW_BUSINESS_ROLES | _REVIEW_TECH_ROLES):
            raise GenesisError(
                "FORBIDDEN_ROLE",
                "peran tidak berwenang memverifikasi evidence",
                403,
            )
        return self._store.set_evidence_verified(agent_key, verified)

    def kill_switch(self, agent_key: str, active: bool, actor: Actor) -> AgentRecord:
        self.get_agent(agent_key)
        if "DIRECTOR" not in actor.roles and "IT_LEAD" not in actor.roles:
            raise GenesisError("FORBIDDEN_ROLE", "kill switch hanya DIRECTOR/IT_LEAD", 403)
        return self._store.set_kill_switch(agent_key, active)

    # --- tool guardrail -----------------------------------------------------
    def check_tools(self, agent_key: str, requested_tools: list[str]) -> list[ToolDecision]:
        record = self.get_agent(agent_key)
        contract = record.current.contract
        return evaluate_tools(
            requested_tools=requested_tools,
            allowed_tools=_as_str_list(contract.get("tool_keys")),
            forbidden_actions=_as_str_list(contract.get("forbidden_actions")),
            registered_tools=sorted(self._store.registered_tools()),
        )

    # --- runtime run --------------------------------------------------------
    def run_agent(
        self,
        agent_key: str,
        *,
        mode: str,
        requested_tools: list[str],
        has_cited_source: bool,
        evidence_present: bool,
        budget_usd: float,
        estimated_run_usd: float,
        actor: Actor,
    ) -> RunRecord:
        record = self.get_agent(agent_key)

        # Live runs require an ACTIVE agent and no kill switch.
        if mode == "live" and (record.kill_switch or record.current.lifecycle_status != "ACTIVE"):
                raise GenesisError(
                    "RUN_BLOCKED",
                    f"live run butuh agent ACTIVE (kini {record.current.lifecycle_status})",
                    403,
                )

        decisions = self.check_tools(agent_key, requested_tools)
        blocked = [d.tool_key for d in decisions if d.decision is Decision.DENY]

        # Cost gate (UAT-09): a denied tool or budget hard stop blocks the run.
        budget = decide_budget(
            spent_usd=self._store.cumulative_cost_usd(),
            budget_usd=budget_usd,
            estimated_run_usd=estimated_run_usd,
        )
        blocked_reason: str | None = None
        if blocked:
            blocked_reason = f"tool ditolak: {', '.join(blocked)}"
        elif budget is BudgetState.HARD_STOP_100:
            blocked_reason = "BUDGET_HARD_STOP_100"

        source_status = label_source(has_cited_source, evidence_present)
        status = "BLOCKED" if blocked_reason else "SUCCEEDED"
        if not blocked_reason:
            self._store.add_cost(estimated_run_usd)

        run = RunRecord(
            run_id=str(uuid4()),
            agent_key=agent_key,
            correlation_id=str(uuid4()),
            requested_by_user_id=actor.user_id,
            status=status,
            mode=mode,
            blocked_tools=blocked,
            source_status=source_status.value,
            budget_state=budget.value,
            reason=blocked_reason,
        )
        self._store.add_run(run)
        return run

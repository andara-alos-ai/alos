"""In-memory GENESIS registry for local/staging.

This follows the same deterministic, persistence-free approach already used by
``alos.model_gateway.UsageBudget``: the runtime policy is proven in-memory
before a Postgres adapter exists. The shapes mirror the SQL schema in
``infra/database/001-002`` (agents.contracts/versions, governance.reviews,
runtime.agent_runs/tool_calls) so a psycopg repository can replace this store
without changing the service or API layer.
"""
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from alos.genesis.contracts import AgentContract


@dataclass
class VersionRecord:
    semantic_version: str
    lifecycle_status: str
    contract: dict[str, object]
    rollback_target: str | None = None


@dataclass
class AgentRecord:
    agent_key: str
    owner_user_id: str
    organization_id: str
    versions: list[VersionRecord] = field(default_factory=list)
    kill_switch: bool = False
    evidence_verified: bool = False

    @property
    def current(self) -> VersionRecord:
        return self.versions[-1]

    @property
    def status(self) -> str:
        return self.current.lifecycle_status


@dataclass
class ReviewRecord:
    review_id: str
    agent_key: str
    reviewer_user_id: str
    gate: str
    decision: str
    notes: str


@dataclass
class RunRecord:
    run_id: str
    agent_key: str
    correlation_id: str
    requested_by_user_id: str
    status: str
    mode: str
    blocked_tools: list[str]
    source_status: str
    budget_state: str
    reason: str | None = None


class InMemoryGenesisStore:
    """Thread-safe minimal registry. One process = one local environment."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._agents: dict[str, AgentRecord] = {}
        self._reviews: list[ReviewRecord] = []
        self._runs: list[RunRecord] = []
        self._tools: set[str] = set()
        self._cumulative_cost_usd: float = 0.0

    def register_tool(self, tool_key: str) -> None:
        with self._lock:
            self._tools.add(tool_key.upper())

    def registered_tools(self) -> set[str]:
        return set(self._tools)

    def add_cost(self, cost_usd: float) -> None:
        with self._lock:
            self._cumulative_cost_usd += cost_usd

    def cumulative_cost_usd(self) -> float:
        return self._cumulative_cost_usd

    # --- agents -------------------------------------------------------------
    def add_agent(
        self, contract: AgentContract, owner_user_id: str, organization_id: str
    ) -> AgentRecord:
        with self._lock:
            record = AgentRecord(
                agent_key=contract.agent_key,
                owner_user_id=owner_user_id,
                organization_id=organization_id,
                versions=[
                    VersionRecord(
                        semantic_version="v1.0.0",
                        lifecycle_status="DRAFT",
                        contract=contract.model_dump(),
                    )
                ],
            )
            self._agents[contract.agent_key] = record
            return record

    def get(self, agent_key: str) -> AgentRecord | None:
        return self._agents.get(agent_key)

    def list_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def transition(self, agent_key: str, target: str) -> AgentRecord:
        with self._lock:
            record = self._agents[agent_key]
            record.versions.append(
                VersionRecord(
                    semantic_version=f"v{len(record.versions) + 1}.0.0",
                    lifecycle_status=target,
                    contract=record.current.contract,
                    rollback_target=record.current.semantic_version,
                )
            )
            return record

    def set_kill_switch(self, agent_key: str, active: bool) -> AgentRecord:
        with self._lock:
            record = self._agents[agent_key]
            record.kill_switch = active
            return record

    def set_evidence_verified(self, agent_key: str, verified: bool) -> AgentRecord:
        with self._lock:
            record = self._agents[agent_key]
            record.evidence_verified = verified
            return record

    # --- reviews ------------------------------------------------------------
    def add_review(
        self, agent_key: str, reviewer_user_id: str, gate: str, decision: str, notes: str
    ) -> ReviewRecord:
        with self._lock:
            record = ReviewRecord(
                review_id=str(uuid4()),
                agent_key=agent_key,
                reviewer_user_id=reviewer_user_id,
                gate=gate,
                decision=decision,
                notes=notes,
            )
            self._reviews.append(record)
            return record

    def reviews_for(self, agent_key: str) -> list[ReviewRecord]:
        return [r for r in self._reviews if r.agent_key == agent_key]

    # --- runs ---------------------------------------------------------------
    def add_run(self, run: RunRecord) -> RunRecord:
        with self._lock:
            self._runs.append(run)
            return run

    def runs_for(self, agent_key: str) -> list[RunRecord]:
        return [r for r in self._runs if r.agent_key == agent_key]

"""HTTP wiring for the GENESIS control plane.

Endpoints live under /api/v1/genesis and reuse the platform bearer-token actor
identity. Persistence is the in-memory local store until a Postgres adapter is
introduced; the contract is stable.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from alos.genesis.contracts import AgentContract
from alos.genesis.service import Actor, GenesisError, GenesisService
from alos.genesis.store import InMemoryGenesisStore
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/genesis", tags=["genesis"])

_store = InMemoryGenesisStore()


def get_service() -> GenesisService:
    return GenesisService(_store)



def _actor(context: ActorContext) -> Actor:
    return Actor(
        user_id=str(context.user_id),
        organization_id=str(context.organization_id),
        roles=frozenset(str(role) for role in context.roles),
    )


def _fail(error: GenesisError) -> None:
    raise HTTPException(
        status_code=error.http_status,
        detail={"code": error.code, "message": str(error)},
    )


CurrentActor = Annotated[ActorContext, Depends(get_current_actor)]
Service = Annotated[GenesisService, Depends(get_service)]


class ReviewIn(BaseModel):
    gate: Literal["TECHNICAL", "BUSINESS"]
    decision: Literal["APPROVED", "REJECTED"]
    notes: str = Field(default="", max_length=1000)


class EvidenceIn(BaseModel):
    verified: bool


class KillIn(BaseModel):
    active: bool


class ToolsIn(BaseModel):
    tool_keys: list[str] = Field(default_factory=list)


class RunIn(BaseModel):
    mode: Literal["test", "live"] = "test"
    requested_tools: list[str] = Field(default_factory=list)
    has_cited_source: bool = False
    evidence_present: bool = True
    budget_usd: float = Field(default=100.0, gt=0)
    estimated_run_usd: float = Field(default=0.0, ge=0)


def _agent_payload(record: object) -> dict[str, object]:
    return {
        "agent_key": record.agent_key,  # type: ignore[attr-defined]
        "status": record.status,  # type: ignore[attr-defined]
        "version": record.current.semantic_version,  # type: ignore[attr-defined]
        "risk_level": record.current.contract.get("risk_level"),  # type: ignore[attr-defined]
        "kill_switch": record.kill_switch,  # type: ignore[attr-defined]
        "evidence_verified": record.evidence_verified,  # type: ignore[attr-defined]
    }


@router.post("/agents", status_code=201)
def draft_agent(
    contract: AgentContract,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.draft_agent(contract, _actor(context))
    except GenesisError as error:
        _fail(error)
    return _agent_payload(record)


@router.get("/agents")
def list_agents(context: CurrentActor, service: Service) -> dict[str, object]:
    return {"agents": [_agent_payload(a) for a in service.list_agents()]}


@router.get("/agents/{agent_key}")
def get_agent(
    agent_key: str,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.get_agent(agent_key)
    except GenesisError as error:
        _fail(error)
    return _agent_payload(record)


@router.post("/agents/{agent_key}/submit")
def submit(
    agent_key: str,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.submit_for_review(agent_key, _actor(context))
    except GenesisError as error:
        _fail(error)
    return _agent_payload(record)


@router.post("/agents/{agent_key}/reviews")
def review(
    agent_key: str,
    body: ReviewIn,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.review(
            agent_key, body.gate, body.decision, body.notes, _actor(context)
        )
    except GenesisError as error:
        _fail(error)
    return {
        "review_id": record.review_id,
        "agent_key": record.agent_key,
        "gate": record.gate,
        "decision": record.decision,
    }


@router.post("/agents/{agent_key}/evidence")
def verify_evidence(
    agent_key: str,
    body: EvidenceIn,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.verify_evidence(agent_key, body.verified, _actor(context))
    except GenesisError as error:
        _fail(error)
    return {"agent_key": agent_key, "evidence_verified": record.evidence_verified}


@router.post("/agents/{agent_key}/activate")
def activate(
    agent_key: str,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.activate(agent_key, _actor(context))
    except GenesisError as error:
        _fail(error)
    return _agent_payload(record)


@router.post("/agents/{agent_key}/kill-switch")
def kill_switch(
    agent_key: str,
    body: KillIn,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        record = service.kill_switch(agent_key, body.active, _actor(context))
    except GenesisError as error:
        _fail(error)
    return {"agent_key": agent_key, "kill_switch": record.kill_switch, "status": record.status}


@router.post("/agents/{agent_key}/tool-check")
def tool_check(
    agent_key: str,
    body: ToolsIn,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        decisions = service.check_tools(agent_key, body.tool_keys)
    except GenesisError as error:
        _fail(error)
    return {
        "decisions": [
            {"tool_key": d.tool_key, "decision": d.decision.value, "reason": d.reason}
            for d in decisions
        ]
    }


@router.post("/agents/{agent_key}/runs")
def run_agent(
    agent_key: str,
    body: RunIn,
    context: CurrentActor,
    service: Service,
) -> dict[str, object]:
    try:
        run = service.run_agent(
            agent_key,
            mode=body.mode,
            requested_tools=body.requested_tools,
            has_cited_source=body.has_cited_source,
            evidence_present=body.evidence_present,
            budget_usd=body.budget_usd,
            estimated_run_usd=body.estimated_run_usd,
            actor=_actor(context),
        )
    except GenesisError as error:
        _fail(error)
    return {
        "run_id": run.run_id,
        "agent_key": run.agent_key,
        "status": run.status,
        "mode": run.mode,
        "blocked_tools": run.blocked_tools,
        "source_status": run.source_status,
        "budget_state": run.budget_state,
        "reason": run.reason,
    }

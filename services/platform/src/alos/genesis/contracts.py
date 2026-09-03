"""Agent Contract validation (H1/H2).

Mirrors definitions/contracts/agent-contract.schema.json but enforces the
governance invariants the JSON schema cannot express, e.g. forbidden actions
may never be whitelisted and every contract must declare at least one
forbidden action (an agent with no boundary is rejected).
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from alos.genesis.catalog import FORBIDDEN_ACTIONS, RISK_LEVELS

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_AGENT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")


class ContractViolation(BaseModel):
    """A single contract problem, expressed in reviewer-friendly language."""

    field: str
    code: str
    message: str


class AgentContract(BaseModel):
    """Structured Agent Contract used by the GENESIS factory.

    Field names align with definitions/contracts/agent-contract.schema.json.
    """

    agent_key: str
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=10_000)
    risk_level: RiskLevel
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    model_policy: dict[str, object]
    tool_keys: list[str] = Field(default_factory=list)
    permission_keys: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    kpis: list[dict[str, object]] = Field(default_factory=list)
    parent_agent_key: str | None = None

    @field_validator("agent_key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not _AGENT_KEY_PATTERN.match(value):
            raise ValueError("agent_key must match ^[A-Z][A-Z0-9_]{2,79}$")
        return value


def validate_agent_contract(contract: AgentContract | dict[str, object]) -> list[ContractViolation]:
    """Return a list of violations; an empty list means the contract is valid.

    Accepts an AgentContract or a raw dict (e.g. a draft from the AI designer).
    Pure function: no database or network access.
    """
    data: dict[str, object] = (
        contract.model_dump() if isinstance(contract, AgentContract) else dict(contract)
    )
    violations: list[ContractViolation] = []

    def as_list(key: str) -> list[object]:
        value = data.get(key, [])
        return value if isinstance(value, list) else []

    def add(field: str, code: str, message: str) -> None:
        violations.append(ContractViolation(field=field, code=code, message=message))

    agent_key = str(data.get("agent_key", ""))
    if not _AGENT_KEY_PATTERN.match(agent_key):
        add("agent_key", "AGENT_KEY_FORMAT", "agent_key harus berpola ^[A-Z][A-Z0-9_]{2,79}$")

    for key_name in ("name", "purpose"):
        if not str(data.get(key_name, "")).strip():
            add(key_name, "REQUIRED", f"{key_name} wajib diisi")

    if data.get("risk_level") not in RISK_LEVELS:
        add("risk_level", "RISK_INVALID", "risk_level harus LOW/MEDIUM/HIGH/CRITICAL")

    for list_field in ("tool_keys", "permission_keys", "evidence_requirements", "kpis"):
        if not isinstance(data.get(list_field, []), list):
            add(list_field, "TYPE", f"{list_field} harus berupa list")

    tools = [str(item).upper() for item in as_list("tool_keys")]
    if len(tools) != len(set(tools)):
        add("tool_keys", "DUPLICATE", "tool_keys tidak boleh duplikat")

    forbidden = {str(item).upper() for item in as_list("forbidden_actions")}
    if not forbidden:
        add(
            "forbidden_actions",
            "NO_BOUNDARY",
            "contract wajib mendeklarasikan forbidden_actions (minimal SELF_APPROVE)",
        )
    if "SELF_APPROVE" not in forbidden:
        add(
            "forbidden_actions",
            "SELF_APPROVE_MISSING",
            "setiap agent wajib melarang SELF_APPROVE (maker != checker != approver)",
        )
    # Irreversible / human-authority actions may never be omitted.
    for mandatory in FORBIDDEN_ACTIONS:
        if mandatory in {
            "TRANSFER_FUNDS",
            "FINAL_LEGAL_DECISION",
            "MUTATE_VERIFIED_RECORD",
            "PRODUCTION_DEPLOY",
        } and mandatory not in forbidden:
            add(
                "forbidden_actions",
                "GUARDRAIL_MISSING",
                f"aksi {mandatory} wajib masuk forbidden_actions (kewenangan manusia)",
            )

    # HIGH/CRITICAL contracts must state evidence requirements.
    if data.get("risk_level") in {"HIGH", "CRITICAL"} and not data.get("evidence_requirements"):
        add(
            "evidence_requirements",
            "HIGH_RISK_EVIDENCE",
            "agent HIGH/CRITICAL wajib mendeklarasikan evidence_requirements",
        )

    parent = data.get("parent_agent_key")
    if parent is not None and not _AGENT_KEY_PATTERN.match(str(parent)):
        add("parent_agent_key", "PARENT_FORMAT", "parent_agent_key harus berpola agent key")

    return violations

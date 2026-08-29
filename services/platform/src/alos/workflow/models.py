import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alos.agents.contract import CapabilityExecutionMode


class AgentInvocation(BaseModel):
    """Version-aware capability binding used by a workflow step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selector: str | None = Field(default=None, min_length=1, max_length=64)
    agent_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    agent_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    execution_mode: CapabilityExecutionMode
    tools: tuple[str, ...] = ()
    requires_human_review: bool = False

    @field_validator("tools")
    @classmethod
    def reject_duplicate_tools(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Tool invocation tidak boleh duplikat")
        return values


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    actor_type: str
    actor_ref: str
    deterministic: bool
    requires_evidence: bool = False
    requires_human_decision: bool = False
    invocations: tuple[AgentInvocation, ...] = ()

    @model_validator(mode="after")
    def validate_agent_invocations(self) -> "WorkflowStep":
        if self.actor_type == "agent" and not self.invocations:
            raise ValueError("Langkah agent wajib memiliki invocation contract")
        if self.actor_type != "agent" and self.invocations:
            raise ValueError("Invocation hanya boleh dimiliki langkah agent")
        if len(self.invocations) == 1 and self.actor_ref != self.invocations[0].agent_id:
            raise ValueError("actor_ref wajib sama dengan agent_id invocation")
        if len(self.invocations) > 1:
            if self.actor_ref != "conditional-agent":
                raise ValueError("Invocation bercabang wajib memakai actor_ref conditional-agent")
            selectors = [invocation.selector for invocation in self.invocations]
            if any(selector is None for selector in selectors):
                raise ValueError("Invocation bercabang wajib memiliki selector")
            if len(selectors) != len(set(selectors)):
                raise ValueError("Selector invocation wajib unik")
        if self.deterministic and any(
            invocation.execution_mode != CapabilityExecutionMode.DETERMINISTIC
            for invocation in self.invocations
        ):
            raise ValueError("Langkah deterministik tidak boleh memakai capability AI_ASSISTED")
        return self


class WorkflowTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_step: str
    outcome: str
    to_step: str


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(pattern=r"^FLOW-00[1-6]$")
    name: str
    purpose: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: str
    owner: str
    trigger: list[str] = Field(min_length=1)
    agents: list[str] = Field(min_length=1)
    initial_step: str
    terminal_steps: list[str] = Field(min_length=1)
    steps: list[WorkflowStep] = Field(min_length=2)
    transitions: list[WorkflowTransition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        step_ids = {step.step_id for step in self.steps}
        referenced = {self.initial_step, *self.terminal_steps}
        referenced.update(transition.from_step for transition in self.transitions)
        referenced.update(transition.to_step for transition in self.transitions)
        missing = referenced - step_ids
        if missing:
            raise ValueError(f"step workflow tidak ditemukan: {sorted(missing)}")
        invocation_agents = {
            invocation.agent_id for step in self.steps for invocation in step.invocations
        }
        if set(self.agents) != invocation_agents:
            raise ValueError(
                "Daftar agents wajib sama dengan seluruh invocation; "
                f"agents={sorted(self.agents)}, invocations={sorted(invocation_agents)}"
            )
        return self

    def get_step(self, step_id: str) -> WorkflowStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)

    def resolve_invocations(
        self, step_id: str, selector: str | None = None
    ) -> tuple[AgentInvocation, ...]:
        step = self.get_step(step_id)
        if not step.invocations:
            raise ValueError(f"Langkah {step_id} tidak memiliki invocation agent")
        if len(step.invocations) == 1:
            if selector is not None and step.invocations[0].selector not in {None, selector}:
                raise KeyError(f"{step_id}:{selector}")
            return step.invocations
        if selector is None:
            raise ValueError(f"Langkah {step_id} memerlukan selector")
        matches = tuple(item for item in step.invocations if item.selector == selector)
        if not matches:
            raise KeyError(f"{step_id}:{selector}")
        return matches

    def canonical_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"status"})

    @property
    def definition_digest(self) -> str:
        payload = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

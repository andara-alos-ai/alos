from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    actor_type: str
    actor_ref: str
    deterministic: bool
    requires_evidence: bool = False
    requires_human_decision: bool = False


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
        return self

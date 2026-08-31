import hashlib
from collections.abc import Mapping
from uuid import UUID, uuid4

from alos.agents.capabilities import (
    CapabilityEvidencePolicy,
    CapabilityRegistry,
    CapabilityReviewPolicy,
)
from alos.agents.contract import AgentStatus, CapabilityExecutionMode
from alos.agents.registry import AgentRegistry
from alos.agents.runtime.handlers import CapabilityHandlerRegistry
from alos.agents.runtime.models import (
    AgentExecutionPlan,
    AgentRunRequest,
    AgentRunStatus,
    CapabilityDispatchResult,
)
from alos.tools import ToolEffect, ToolReference, ToolRegistry
from alos.workflow.models import WorkflowDefinition, WorkflowStatus


class RuntimePolicyViolation(ValueError):
    """Raised when a requested capability or tool exceeds an Agent Contract."""


class SharedAgentRuntime:
    def __init__(
        self,
        registry: AgentRegistry,
        tool_registry: ToolRegistry,
        handlers: CapabilityHandlerRegistry | None = None,
        runnable_statuses: frozenset[AgentStatus] = frozenset(
            {AgentStatus.STAGED, AgentStatus.RELEASED}
        ),
    ) -> None:
        self._registry = registry
        self._tool_registry = tool_registry
        self._capability_registry = CapabilityRegistry(tool_registry.definitions_root)
        if handlers is None:
            from alos.agents.runtime.builtin_handlers import build_default_handler_registry
            from alos.llm import DisabledProvider, LLMGateway, PromptRegistry

            gateway = LLMGateway(
                PromptRegistry(tool_registry.definitions_root), DisabledProvider()
            )
            handlers = build_default_handler_registry(self._capability_registry, gateway)
        self._handlers = handlers
        self._runnable_statuses = runnable_statuses

    def prepare(self, request: AgentRunRequest) -> AgentExecutionPlan:
        agent = self._registry.get(request.agent_id, request.agent_version)
        if agent.status not in self._runnable_statuses:
            versioned_agent = f"{agent.agent_id}@{agent.version}"
            raise RuntimePolicyViolation(
                f"Status {agent.status} tidak dapat dijalankan untuk {versioned_agent}"
            )
        if request.capability not in agent.capabilities:
            raise RuntimePolicyViolation(
                f"Capability {request.capability!r} tidak diizinkan untuk {agent.agent_id}"
            )
        capability = self._capability_registry.get(request.capability)
        if capability.execution_mode != request.execution_mode:
            raise RuntimePolicyViolation(
                f"Capability AI tidak boleh memakai AI dalam mode {request.execution_mode}; "
                f"Capability Contract {capability.capability_id} menetapkan "
                f"{capability.execution_mode}"
            )

        disallowed_tools = set(request.requested_tools) - set(agent.tools_allowed)
        if disallowed_tools:
            raise RuntimePolicyViolation(
                f"Tool tidak diizinkan untuk {agent.agent_id}: {sorted(disallowed_tools)}"
            )

        try:
            tools = tuple(self._tool_registry.get(tool_id) for tool_id in request.requested_tools)
        except KeyError as exc:
            raise RuntimePolicyViolation(f"Tool tidak terdaftar: {exc.args[0]}") from exc
        blocked_tools = [
            tool.tool_id for tool in tools if not self._tool_registry.is_runnable(tool)
        ]
        if blocked_tools:
            raise RuntimePolicyViolation(f"Status tool tidak dapat dijalankan: {blocked_tools}")
        if request.execution_mode == CapabilityExecutionMode.DETERMINISTIC:
            ai_tools = [tool.tool_id for tool in tools if not tool.allowed_in_deterministic_steps]
            if ai_tools:
                raise RuntimePolicyViolation(
                    f"Capability deterministik tidak boleh memakai AI: {sorted(ai_tools)}"
                )
        elif not any(tool.effect == ToolEffect.AI_ASSISTED for tool in tools):
            raise RuntimePolicyViolation(
                "Capability AI_ASSISTED wajib memakai tool AI yang disetujui Agent Contract"
            )

        return AgentExecutionPlan(
            run_id=uuid4(),
            agent_id=agent.agent_id,
            agent_version=agent.version,
            contract_version=agent.contract_version,
            agent_kind=agent.agent_kind,
            contract_digest=agent.contract_digest,
            contract_snapshot=agent,
            capability=request.capability,
            capability_version=capability.version,
            capability_contract_digest=capability.contract_digest,
            execution_mode=request.execution_mode,
            approved_tools=tuple(request.requested_tools),
            approved_tool_releases=tuple(
                ToolReference(tool_id=tool.tool_id, version=tool.version) for tool in tools
            ),
            input_references=tuple(request.input_references),
            status=AgentRunStatus.RECEIVED,
            requires_human_review=(
                request.material_action
                or capability.review_policy == CapabilityReviewPolicy.ALWAYS
            ),
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            workflow_id=request.workflow_id,
            workflow_version=request.workflow_version,
            workflow_step_id=request.workflow_step_id,
        )

    def prepare_workflow_step(
        self,
        workflow: WorkflowDefinition,
        step_id: str,
        input_references: list[str],
        correlation_id: UUID,
        idempotency_key: str,
        selector: str | None = None,
    ) -> tuple[AgentExecutionPlan, ...]:
        """Resolve and prepare a workflow step without agent-specific runtime logic."""

        if workflow.status not in {WorkflowStatus.STAGED, WorkflowStatus.RELEASED}:
            raise RuntimePolicyViolation(
                f"Workflow {workflow.workflow_id}@{workflow.version} berstatus "
                f"{workflow.status} dan tidak dapat dijalankan"
            )

        invocations = workflow.resolve_invocations(step_id, selector)
        return tuple(
            self.prepare(
                AgentRunRequest(
                    agent_id=invocation.agent_id,
                    agent_version=invocation.agent_version,
                    capability=invocation.capability,
                    execution_mode=invocation.execution_mode,
                    input_references=input_references,
                    requested_tools=list(invocation.tools),
                    material_action=invocation.requires_human_review,
                    correlation_id=correlation_id,
                    idempotency_key=self._agent_idempotency_key(
                        invocation.agent_id, step_id, idempotency_key
                    ),
                    workflow_id=workflow.workflow_id,
                    workflow_version=workflow.version,
                    workflow_step_id=step_id,
                )
            )
            for invocation in invocations
        )

    def dispatch(
        self,
        plan: AgentExecutionPlan,
        input_payload: Mapping[str, object],
        handlers: CapabilityHandlerRegistry | None = None,
    ) -> CapabilityDispatchResult:
        """Dispatch a prepared plan to a capability handler after integrity checks."""

        if plan.status != AgentRunStatus.RECEIVED:
            raise RuntimePolicyViolation("Hanya execution plan RECEIVED yang dapat dijalankan")
        agent = self._registry.get(plan.agent_id, plan.agent_version)
        if agent.contract_digest != plan.contract_digest:
            raise RuntimePolicyViolation("Digest Agent Contract pada execution plan tidak valid")
        if plan.contract_snapshot.contract_digest != plan.contract_digest:
            raise RuntimePolicyViolation("Snapshot Agent Contract pada execution plan tidak valid")
        capability = self._capability_registry.get(
            plan.capability, plan.capability_version
        )
        if capability.contract_digest != plan.capability_contract_digest:
            raise RuntimePolicyViolation(
                "Digest Capability Contract pada execution plan tidak valid"
            )
        if capability.execution_mode != plan.execution_mode:
            raise RuntimePolicyViolation(
                "Mode Capability Contract pada execution plan tidak konsisten"
            )
        if set(plan.approved_tools) != {
            reference.tool_id for reference in plan.approved_tool_releases
        }:
            raise RuntimePolicyViolation("Referensi tool pada execution plan tidak konsisten")
        for reference in plan.approved_tool_releases:
            try:
                tool = self._tool_registry.get(reference.tool_id, reference.version)
            except KeyError as exc:
                raise RuntimePolicyViolation(
                    f"Tool release pada execution plan tidak ditemukan: {exc.args[0]}"
                ) from exc
            if not self._tool_registry.is_runnable(tool):
                raise RuntimePolicyViolation(
                    f"Tool release tidak dapat dijalankan: {tool.tool_id}@{tool.version}"
                )
        result = (handlers or self._handlers).dispatch(plan, input_payload)
        if result.handler_id != capability.handler_id:
            raise RuntimePolicyViolation(
                "Handler hasil dispatch tidak sama dengan Capability Contract"
            )
        if (
            capability.evidence_policy == CapabilityEvidencePolicy.REQUIRED
            and not result.evidence_references
        ):
            raise RuntimePolicyViolation(
                f"Capability {capability.capability_id} wajib menghasilkan referensi evidence"
            )
        return result

    def execute(
        self,
        plan: AgentExecutionPlan,
        input_payload: Mapping[str, object],
        handlers: CapabilityHandlerRegistry | None = None,
    ) -> AgentExecutionPlan:
        """Execute and attach an immutable, auditable dispatch record to the plan."""

        result = self.dispatch(plan, input_payload, handlers)
        return plan.model_copy(update={"execution": result.to_execution_record()})

    @staticmethod
    def _agent_idempotency_key(agent_id: str, step_id: str, source_key: str) -> str:
        candidate = f"{agent_id.lower()}-{step_id}-{source_key}"
        if len(candidate) <= 128:
            return candidate
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        prefix = f"{agent_id.lower()}-{step_id}-"
        available_prefix = prefix[: 128 - len(digest) - 1]
        return f"{available_prefix}-{digest}"

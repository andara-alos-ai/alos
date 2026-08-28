from uuid import uuid4

from alos.agents.registry import AgentRegistry
from alos.agents.runtime.models import AgentExecutionPlan, AgentRunRequest, AgentRunStatus


class RuntimePolicyViolation(ValueError):
    """Raised when a requested capability or tool exceeds an Agent Contract."""


class SharedAgentRuntime:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def prepare(self, request: AgentRunRequest) -> AgentExecutionPlan:
        agent = self._registry.get(request.agent_id)
        if request.capability not in agent.capabilities:
            raise RuntimePolicyViolation(
                f"Capability {request.capability!r} tidak diizinkan untuk {agent.agent_id}"
            )

        disallowed_tools = set(request.requested_tools) - set(agent.tools_allowed)
        if disallowed_tools:
            raise RuntimePolicyViolation(
                f"Tool tidak diizinkan untuk {agent.agent_id}: {sorted(disallowed_tools)}"
            )

        return AgentExecutionPlan(
            run_id=uuid4(),
            agent_id=agent.agent_id,
            agent_version=agent.version,
            capability=request.capability,
            approved_tools=request.requested_tools,
            input_references=request.input_references,
            status=AgentRunStatus.RECEIVED,
            requires_human_review=request.material_action,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )

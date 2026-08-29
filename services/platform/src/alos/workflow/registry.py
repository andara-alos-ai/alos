from pathlib import Path

from alos.agents.registry import AgentRegistry
from alos.tools import ToolEffect, ToolRegistry, ToolRegistryError
from alos.workflow.models import WorkflowDefinition


class WorkflowRegistry:
    def __init__(
        self,
        definitions_root: Path,
        agent_registry: AgentRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._definitions_root = definitions_root
        self._agent_registry = agent_registry or AgentRegistry(definitions_root)
        self._tool_registry = tool_registry or ToolRegistry(definitions_root)
        self._cache: tuple[WorkflowDefinition, ...] | None = None

    def load_all(self, *, force_reload: bool = False) -> tuple[WorkflowDefinition, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        files = sorted((self._definitions_root / "workflows").glob("*/workflow.json"))
        workflows = tuple(
            WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
            for path in files
        )
        if len(workflows) != 6:
            raise ValueError(f"Registry wajib berisi tepat 6 workflow; ditemukan {len(workflows)}")
        if len({item.workflow_id for item in workflows}) != len(workflows):
            raise ValueError("workflow_id harus unik")
        for workflow in workflows:
            self._validate_invocations(workflow)
        self._cache = workflows
        return workflows

    def get(self, workflow_id: str) -> WorkflowDefinition:
        for workflow in self.load_all():
            if workflow.workflow_id == workflow_id:
                return workflow
        raise KeyError(workflow_id)

    def refresh(self) -> tuple[WorkflowDefinition, ...]:
        self._agent_registry.refresh()
        self._tool_registry.refresh()
        return self.load_all(force_reload=True)

    def _validate_invocations(self, workflow: WorkflowDefinition) -> None:
        for step in workflow.steps:
            for invocation in step.invocations:
                try:
                    agent = self._agent_registry.get(
                        invocation.agent_id, invocation.agent_version
                    )
                except KeyError as exc:
                    raise ValueError(
                        f"Invocation {workflow.workflow_id}/{step.step_id} merujuk agent "
                        f"yang tidak terdaftar: {exc}"
                    ) from exc
                if invocation.capability not in agent.capabilities:
                    raise ValueError(
                        f"Capability {invocation.capability} tidak diizinkan untuk "
                        f"{agent.agent_id}@{agent.version}"
                    )
                disallowed_tools = set(invocation.tools) - set(agent.tools_allowed)
                if disallowed_tools:
                    raise ValueError(
                        f"Tool invocation tidak diizinkan untuk {agent.agent_id}: "
                        f"{sorted(disallowed_tools)}"
                    )
                try:
                    self._tool_registry.validate_allowed_tools(invocation.tools)
                except ToolRegistryError as exc:
                    raise ValueError(
                        f"Tool invocation {workflow.workflow_id}/{step.step_id} tidak valid: {exc}"
                    ) from exc
                if step.deterministic:
                    ai_tools = [
                        tool_id
                        for tool_id in invocation.tools
                        if self._tool_registry.get(tool_id).effect == ToolEffect.AI_ASSISTED
                    ]
                    if ai_tools:
                        raise ValueError(
                            f"Langkah deterministik {workflow.workflow_id}/{step.step_id} "
                            f"tidak boleh memakai AI: {sorted(ai_tools)}"
                        )

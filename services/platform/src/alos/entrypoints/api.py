from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from alos.agents.contract import AgentDefinition
from alos.agents.registry import AgentRegistry
from alos.agents.runtime import (
    AgentExecutionPlan,
    AgentRunRequest,
    RuntimePolicyViolation,
    SharedAgentRuntime,
)
from alos.config import Settings, get_settings
from alos.workflow.models import WorkflowDefinition
from alos.workflow.registry import WorkflowRegistry

router = APIRouter()


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def agent_registry(settings: SettingsDependency) -> AgentRegistry:
    return AgentRegistry(settings.definitions_root)


def workflow_registry(settings: SettingsDependency) -> WorkflowRegistry:
    return WorkflowRegistry(settings.definitions_root)


AgentRegistryDependency = Annotated[AgentRegistry, Depends(agent_registry)]
WorkflowRegistryDependency = Annotated[WorkflowRegistry, Depends(workflow_registry)]


def shared_runtime(registry: AgentRegistryDependency) -> SharedAgentRuntime:
    return SharedAgentRuntime(registry)


SharedRuntimeDependency = Annotated[SharedAgentRuntime, Depends(shared_runtime)]


@router.get("/health", tags=["system"])
def health(settings: SettingsDependency) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.application_name,
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
    }


@router.get("/agents", response_model=list[AgentDefinition], tags=["agent-registry"])
def list_agents(registry: AgentRegistryDependency) -> tuple[AgentDefinition, ...]:
    return registry.load_all()


@router.get("/agents/{agent_id}", response_model=AgentDefinition, tags=["agent-registry"])
def get_agent(agent_id: str, registry: AgentRegistryDependency) -> AgentDefinition:
    try:
        return registry.get(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Core Agent tidak ditemukan") from exc


@router.get("/workflows", response_model=list[WorkflowDefinition], tags=["workflow"])
def list_workflows(
    registry: WorkflowRegistryDependency,
) -> tuple[WorkflowDefinition, ...]:
    return registry.load_all()


@router.post(
    "/agent-runs/prepare",
    response_model=AgentExecutionPlan,
    status_code=201,
    tags=["shared-agent-runtime"],
)
def prepare_agent_run(
    request: AgentRunRequest,
    runtime: SharedRuntimeDependency,
) -> AgentExecutionPlan:
    try:
        return runtime.prepare(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Core Agent tidak ditemukan") from exc
    except RuntimePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

"""Prepare, but never approve, local controls for source-enabled validation drafts.

This command creates only Tool Registry and Permission Policy DRAFT records.
An independent human must approve them through the API before the Runtime can
read sources or the release lifecycle can continue.
"""

from __future__ import annotations

import json
from uuid import uuid4

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.agents.validation_catalog import validation_agent_requests
from alos.config import get_settings
from alos.permissions.registry import (
    PermissionPolicyRequest,
    PermissionRegistryRepository,
)
from alos.tools.registry import ToolDefinitionRequest, ToolRegistryRepository


def prepare_validation_controls() -> list[dict[str, str]]:
    """Create missing local DRAFT controls for the three source-enabled contracts."""
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        raise RuntimeError("validation control preparation is limited to local/test")
    agents = AgentRegistryRepository(settings.database_url)
    context = agents.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
    tools = ToolRegistryRepository(settings.database_url)
    permissions = PermissionRegistryRepository(settings.database_url)
    results: list[dict[str, str]] = []

    tool = next(
        (
            record
            for record in tools.list_tools(context.organization_id)
            if record.tool_key == "SOURCE_REGISTRY_SEARCH"
        ),
        None,
    )
    if tool is None:
        tool = tools.create_draft(
            ToolDefinitionRequest(
                tool_key="SOURCE_REGISTRY_SEARCH",
                name="Source Registry Search",
                risk_level="LOW",
                manifest={
                    "access_mode": "READ_ONLY",
                    "runtime_handler": "SOURCE_REGISTRY_SEARCH",
                },
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        results.append({"control": "SOURCE_REGISTRY_SEARCH", "status": "TOOL_DRAFT_CREATED"})
    else:
        results.append(
            {"control": "SOURCE_REGISTRY_SEARCH", "status": f"TOOL_{tool.lifecycle_status}"}
        )

    for request in validation_agent_requests(context.workspace_id):
        agent = agents.get_agent(context.organization_id, request.agent_key)
        version = agent.versions[0]
        if version.lifecycle_status != "DRAFT":
            raise RuntimeError(f"{request.agent_key} latest version must remain DRAFT")
        snapshot = version.contract_snapshot
        if (
            snapshot.get("tool_keys") != request.tool_keys
            or snapshot.get("permission_keys") != request.permission_keys
        ):
            raise RuntimeError(f"{request.agent_key} latest draft is not source-enabled")
        existing = next(
            (
                policy
                for policy in permissions.list_policies(
                    context.organization_id, agent_key=request.agent_key
                )
                if policy.agent_version_id == version.agent_version_id
                and policy.permission_key == "SOURCE_READ_INTERNAL"
            ),
            None,
        )
        if existing is None:
            policy = permissions.create_draft(
                PermissionPolicyRequest(
                    workspace_id=context.workspace_id,
                    agent_key=request.agent_key,
                    semantic_version=version.semantic_version,
                    permission_key="SOURCE_READ_INTERNAL",
                    effect="ALLOW",
                    resource_scope={"access_mode": "READ_ONLY", "classification": "INTERNAL"},
                ),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
            )
            results.append(
                {
                    "control": f"{request.agent_key}:SOURCE_READ_INTERNAL",
                    "status": f"PERMISSION_{policy.lifecycle_status}",
                    "permission_policy_id": str(policy.permission_policy_id),
                }
            )
        else:
            results.append(
                {
                    "control": f"{request.agent_key}:SOURCE_READ_INTERNAL",
                    "status": f"PERMISSION_{existing.lifecycle_status}",
                    "permission_policy_id": str(existing.permission_policy_id),
                }
            )
    return results


def main() -> None:
    print(json.dumps(prepare_validation_controls(), ensure_ascii=False))


if __name__ == "__main__":
    main()

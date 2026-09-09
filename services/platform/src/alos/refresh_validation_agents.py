"""Create source-enabled successor drafts for the three MVP1 validation agents.

The command is deliberately local/test only and idempotent.  It never creates
 tools, permissions, approvals, releases, or active agents. Genesis compiles
 only the generic agent requirements from ``validation_catalog`` locally.
"""

from __future__ import annotations

import json
from uuid import uuid4

from alos.agents.registry import (
    AgentDraftBuilder,
    AgentNotFoundError,
    AgentRegistryRepository,
    DeterministicAgentDraftGenerator,
    LocalBootstrapRequest,
)
from alos.agents.validation_catalog import validation_agent_requests
from alos.config import get_settings


def refresh_validation_agents() -> list[dict[str, str]]:
    """Create one source-enabled DRAFT successor per existing validation agent."""
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        raise RuntimeError("validation-agent refresh is limited to local/test")
    repository = AgentRegistryRepository(settings.database_url)
    context = repository.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
    builder = AgentDraftBuilder(DeterministicAgentDraftGenerator())
    results: list[dict[str, str]] = []
    for request in validation_agent_requests(context.workspace_id):
        try:
            existing = repository.get_agent(context.organization_id, request.agent_key)
        except AgentNotFoundError as error:
            raise RuntimeError(
                f"{request.agent_key} must exist as a Genesis DRAFT before it can be refreshed"
            ) from error
        latest = existing.versions[0]
        snapshot = latest.contract_snapshot
        if (
            latest.lifecycle_status == "DRAFT"
            and snapshot.get("tool_keys") == request.tool_keys
            and snapshot.get("permission_keys") == request.permission_keys
            and snapshot.get("model_policy") == request.model_policy
        ):
            results.append(
                {
                    "agent_key": request.agent_key,
                    "semantic_version": latest.semantic_version,
                    "status": "ALREADY_SOURCE_ENABLED_DRAFT",
                }
            )
            continue
        contract = builder.build(request, context.user_id)
        updated = repository.update_draft(
            contract,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason=(
                "Genesis MVP1 created a source-enabled successor draft; "
                "human Tool/Permission approval remains required"
            ),
        )
        results.append(
            {
                "agent_key": updated.agent_key,
                "semantic_version": updated.semantic_version,
                "status": "CREATED_SOURCE_ENABLED_DRAFT",
            }
        )
    return results


def main() -> None:
    print(json.dumps(refresh_validation_agents(), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Create the three local MVP1 validation Agent Contract records once.

This is intentionally idempotent: existing agent keys are reported and never
overwritten. Gemini is only used to draft safe text fields; the catalog holds
all deterministic controls.
"""

from __future__ import annotations

import json
from uuid import uuid4

from alos.agents.registry import (
    AgentConflictError,
    AgentDraftBuilder,
    AgentNotFoundError,
    AgentRegistryRepository,
    LocalBootstrapRequest,
    ModelGatewayAgentDraftGenerator,
)
from alos.agents.validation_catalog import validation_agent_requests
from alos.config import get_settings


def bootstrap_validation_agents() -> list[dict[str, str]]:
    """Persist missing validation agents as DRAFT records in the local Registry."""
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        raise RuntimeError("validation-agent bootstrap is limited to local/test")
    if settings.llm_provider != "gemini":
        raise RuntimeError("validation-agent bootstrap requires the local Gemini Model Gateway")
    repository = AgentRegistryRepository(settings.database_url)
    context = repository.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
    builder = AgentDraftBuilder(ModelGatewayAgentDraftGenerator(settings))
    results: list[dict[str, str]] = []
    for request in validation_agent_requests(context.workspace_id):
        try:
            existing = repository.get_agent(context.organization_id, request.agent_key)
        except AgentNotFoundError:
            contract = builder.build(request, context.user_id)
            created = repository.create_draft(
                contract,
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
                reason="Genesis MVP1 registered a required validation Agent Contract",
            )
            results.append(
                {
                    "agent_key": created.agent_key,
                    "semantic_version": created.semantic_version,
                    "status": "CREATED_DRAFT",
                }
            )
        except AgentConflictError:
            raise
        else:
            results.append(
                {
                    "agent_key": existing.agent_key,
                    "semantic_version": existing.versions[0].semantic_version,
                    "status": "ALREADY_EXISTS",
                }
            )
    return results


def main() -> None:
    print(json.dumps(bootstrap_validation_agents(), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Register local-only synthetic evidence for the three MVP1 validation agents."""

from __future__ import annotations

import json
from uuid import uuid4

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.config import get_settings
from alos.sources.registry import (
    SourceConflictError,
    SourceRegistrationRequest,
    SourceRegistryRepository,
)


def bootstrap_validation_sources() -> list[dict[str, str]]:
    """Create/verify safe fixtures; no company source or provider call is involved."""
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        raise RuntimeError("validation source bootstrap is limited to local/test")
    agents = AgentRegistryRepository(settings.database_url)
    context = agents.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
    sources = SourceRegistryRepository(settings.database_url)
    definitions = (
        (
            "DAILY_BRIEF_FIXTURE",
            "Synthetic Daily Brief Fixture",
            "daily-v1",
            "Daily operational priorities: Property due diligence is open.\n"
            "Sales pipeline status: current synthetic value is Rp1.55B.\n"
            "Finance cash collection review is due today.",
        ),
        (
            "EVIDENCE_CHECKER_FIXTURE",
            "Synthetic Evidence Checker Fixture",
            "evidence-v1",
            "Claim: revenue reached Rp1.80B.\n"
            "Finance verified report: approved synthetic revenue is Rp1.55B.\n"
            "Gap: invoice-level evidence for the Rp1.80B claim is unavailable.",
        ),
        (
            "PERMIT_OVERDUE_FIXTURE",
            "Synthetic Permit Monitor Fixture",
            "permit-v1",
            "PRM-001 status=DUE_SOON; legal memo approval=PENDING.\n"
            "PRM-002 status=OVERDUE; project condition=BLOCKED.\n"
            "No external notification or side effect is authorized.",
        ),
    )
    results: list[dict[str, str]] = []
    for source_key, name, version_label, content in definitions:
        try:
            record = sources.register(
                SourceRegistrationRequest(
                    workspace_id=context.workspace_id,
                    source_key=source_key,
                    name=name,
                    version_label=version_label,
                    locator=f"synthetic://alos/mvp1/{source_key.lower()}",
                    content=content,
                ),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
            )
            status = f"REGISTERED_{record.version_label}"
        except SourceConflictError:
            status = "ALREADY_REGISTERED"
        verified = sources.verify(
            context.workspace_id,
            source_key,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="Director verified synthetic MVP1 local validation evidence.",
        )
        results.append(
            {
                "source_key": source_key,
                "status": status,
                "verified_version": verified.version_label,
            }
        )
    return results


def main() -> None:
    print(json.dumps(bootstrap_validation_sources(), ensure_ascii=False))


if __name__ == "__main__":
    main()

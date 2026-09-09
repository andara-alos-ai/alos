import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.genesis.factory.persistence import FactoryRepository
from alos.genesis.governed_foundations import ResearchStatus, Scope
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.release.governance import ReleaseGovernanceRepository
from alos.research import ResearchArtifactRequest, ResearchProjectCreate, ResearchRepository
from alos.research.repository import (
    ResearchArtifactType,
    ResearchConflictError,
)
from alos.security.tokens import ActorContext

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _actor(context, *, role, division_code=DivisionCode.IT):
    now = datetime.now(UTC)
    return ActorContext(
        user_id=context.user_id,
        organization_id=context.organization_id,
        roles=[role],
        division_codes=[division_code],
        workspace_ids=[context.workspace_id],
        data_scope=DataScope.DIVISION,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_generic_research_requires_independent_decision_before_factory_handoff() -> None:
    from alos.config import get_settings

    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_research_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, root / "infra" / "database")
        bootstrap = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        team = ReleaseGovernanceRepository(temporary_url).bootstrap_local_release_team(
            bootstrap.workspace_id, uuid4()
        )
        reviewer = next(item for item in team.participants if item.duty == "BUSINESS_REVIEWER")
        requester = _actor(bootstrap, role=HumanRole.IT_LEAD)
        reviewer_context = type(bootstrap)(
            organization_id=bootstrap.organization_id,
            user_id=reviewer.user_id,
            workspace_id=bootstrap.workspace_id,
        )
        decider = _actor(
            reviewer_context,
            role=HumanRole.BUSINESS_REVIEWER,
            division_code=team.division_code,
        )
        scope = Scope(
            organization_id=bootstrap.organization_id,
            workspace_id=bootstrap.workspace_id,
        )
        repository = ResearchRepository(temporary_url)
        project = repository.create(
            ResearchProjectCreate(
                scope=scope,
                research_type="PROCESS_DIAGNOSTIC",
                domain="operations",
                title="Why process X is slow",
                objective=(
                    "Research why process X is slow and produce an evidence-based "
                    "recommendation."
                ),
                questions=("Where does process X wait the longest?",),
                idempotency_key="research-process-x",
            ),
            requester,
            correlation_id=uuid4(),
        )
        artifacts = (
            ResearchArtifactRequest(
                artifact_type=ResearchArtifactType.METHOD,
                payload={"method": "cycle-time observation"},
            ),
            ResearchArtifactRequest(
                artifact_type=ResearchArtifactType.EVIDENCE,
                payload={"observation": "verification queue accounts for most wait time"},
                source_reference="source://process-x/cycle-time",
                confidence=0.9,
            ),
            ResearchArtifactRequest(
                artifact_type=ResearchArtifactType.FINDING,
                payload={"finding": "manual verification is the primary bottleneck"},
                confidence=0.85,
            ),
            ResearchArtifactRequest(
                artifact_type=ResearchArtifactType.RECOMMENDATION,
                payload={
                    "recommendation": (
                        "Every day identify records waiting for verification over 48 hours "
                        "and prepare an owner escalation task."
                    )
                },
            ),
        )
        for artifact in artifacts:
            repository.add_artifact(
                project.research_id, artifact, requester, correlation_id=uuid4()
            )
        for target in (
            ResearchStatus.SCOPING,
            ResearchStatus.RESEARCH,
            ResearchStatus.EVIDENCE_COLLECTION,
            ResearchStatus.ANALYSIS,
            ResearchStatus.FINDINGS,
            ResearchStatus.RECOMMENDATION,
            ResearchStatus.REVIEW,
        ):
            project = repository.transition(
                project.research_id, target, requester, correlation_id=uuid4()
            )
        with pytest.raises(ResearchConflictError, match="own handoff"):
            repository.decide(
                project.research_id,
                "APPROVE_HANDOFF",
                "The evidence supports a controlled Factory proposal.",
                requester.model_copy(update={"roles": [HumanRole.DIRECTOR]}),
                correlation_id=uuid4(),
            )
        decided = repository.decide(
            project.research_id,
            "APPROVE_HANDOFF",
            "The evidence supports a controlled Factory proposal.",
            decider,
            correlation_id=uuid4(),
        )
        assert decided.status == ResearchStatus.DECISION

        handoff = repository.create_factory_handoff(
            project.research_id,
            FactoryRepository(temporary_url),
            decider,
            idempotency_key="research-process-x-handoff",
            correlation_id=uuid4(),
        )
        assert handoff.source_type == "RESEARCH"
        assert handoff.source_research_id == project.research_id
        assert "48 hours" in handoff.requirement
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))

"""Create the three GENESIS MVP1 validation agents through the shared pipeline.

This script is intentionally limited to synthetic source packs and local versioned
definitions. It neither deploys production code nor contacts an LLM provider.
"""

from pathlib import Path
from uuid import uuid4

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentDefinition, AgentKind, AgentStatus
from alos.agents.registry import AgentRegistry
from alos.genesis import GenesisDesignService, GenesisPipelineService, SourceRegistry
from alos.genesis.models import (
    GenesisReviewCreate,
    GenesisReviewDecision,
    GenesisReviewGate,
    GenesisStrategy,
    GenesisSubmitRequest,
)
from alos.genesis.repository import InMemoryGenesisStore
from alos.security import Principal, Role

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = REPOSITORY_ROOT / "definitions"
SOURCE_REFERENCE = "ALOS-SP-SYNTHETIC-PILOT@1.0.0"
DIVISIONS = ("FINANCE", "SALES_MARKETING", "PROPERTY", "HR", "LEGAL", "IT")


def actor(organization_id: object, role: Role) -> Principal:
    return Principal(user_id=uuid4(), organization_id=organization_id, roles=frozenset({role}))


def contract(
    *,
    agent_id: str,
    name: str,
    purpose: str,
    capabilities: tuple[str, ...],
    tools_allowed: tuple[str, ...],
    division_scope: tuple[str, ...] = DIVISIONS,
) -> AgentDefinition:
    return AgentDefinition(
        contract_version="1.0.0",
        agent_id=agent_id,
        name=name,
        agent_kind=AgentKind.LOGICAL,
        domain="shared-enterprise",
        division_scope=division_scope,
        purpose=purpose,
        human_owner="AI Executive Operating Layer",
        triggers=("ON_DEMAND", "SCHEDULED"),
        inputs=("synthetic_source_record", "workspace_context"),
        source_of_truth=("Registered synthetic source", "Verified source metadata"),
        capabilities=capabilities,
        outputs=("structured_result", "citation_references"),
        tools_allowed=tools_allowed,
        approval_boundary=("Human review is required before any material action",),
        evidence_requirement=("Every result references registered source evidence",),
        forbidden_actions=(
            "write production data",
            "approve its own release",
            "create or modify a tool",
        ),
        metrics=("citation coverage", "test pass rate", "cost per run"),
        escalation=("Escalate blocked or unsupported results to the domain owner",),
        prompt_ref="genesis.validation@0.1.0",
        model_policy_ref="openai-primary-claude-fallback@0.1.0",
        permission_policy_ref="read-only-evidence@0.1.0",
        risk_level="LOW",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": False},
        version="0.1.0",
        status=AgentStatus.DRAFT,
    )


def main() -> None:
    agents = AgentRegistry(DEFINITIONS)
    pipeline = GenesisPipelineService(
        GenesisDesignService(agents),
        CapabilityRegistry(DEFINITIONS),
        InMemoryGenesisStore(),
        SourceRegistry(DEFINITIONS),
        agents,
    )
    organization_id = uuid4()
    requester = actor(organization_id, Role.AI_EXECUTIVE)
    business_reviewer = actor(organization_id, Role.DIRECTOR)
    technical_reviewer = actor(organization_id, Role.IT_ADMIN)
    releaser = actor(organization_id, Role.DIRECTOR)
    candidates = (
        contract(
            agent_id="DAILY_BRIEF",
            name="Daily Brief Agent",
            purpose="Menyusun ringkasan kondisi harian dari fakta terverifikasi dengan citation yang dapat ditelusuri.",
            capabilities=("aggregate_verified_facts",),
            tools_allowed=("alos.audit.read",),
        ),
        contract(
            agent_id="EVIDENCE_CHECKER",
            name="Evidence Checker Agent",
            purpose="Memeriksa metadata, checksum, dan status evidence tanpa membuat keputusan atau perubahan data.",
            capabilities=("validate_evidence_metadata",),
            tools_allowed=("alos.evidence.read",),
        ),
        contract(
            agent_id="PERMIT_OVERDUE_MONITOR",
            name="Permit and Overdue Monitor Agent",
            purpose="Menghitung status tenggat permit dan overdue secara deterministik serta menyiapkan alert read-only.",
            capabilities=("monitor_capa_deadline",),
            tools_allowed=("alos.legal.read",),
            division_scope=("PROPERTY", "LEGAL"),
        ),
    )
    for candidate in candidates:
        submitted = pipeline.submit(
            GenesisSubmitRequest(
                strategy=GenesisStrategy.CREATE,
                justification=f"Membuat {candidate.name} untuk validasi GENESIS MVP1 dengan data sintetis.",
                source_references=(SOURCE_REFERENCE,),
                candidate=candidate,
            ),
            requester,
        )
        pipeline.review(
            submitted.request_id,
            GenesisReviewCreate(
                gate=GenesisReviewGate.BUSINESS,
                decision=GenesisReviewDecision.APPROVED,
                notes="Owner bisnis menyetujui tujuan, evidence, KPI, dan forbidden actions.",
            ),
            business_reviewer,
        )
        pipeline.review(
            submitted.request_id,
            GenesisReviewCreate(
                gate=GenesisReviewGate.TECHNICAL,
                decision=GenesisReviewDecision.APPROVED,
                notes="IT menyetujui schema, tool allowlist, model policy, dan test baseline.",
            ),
            technical_reviewer,
        )
        pipeline.stage(submitted.request_id, technical_reviewer)
        pipeline.release(submitted.request_id, releaser)
        print(f"released {candidate.agent_id}@{candidate.version}")


if __name__ == "__main__":
    main()

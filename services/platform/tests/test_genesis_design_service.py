from pathlib import Path

from alos.agents.contract import AgentDefinition, AgentKind, AgentReference, AgentStatus
from alos.agents.registry import AgentRegistry
from alos.genesis import (
    GenesisChangeRequest,
    GenesisDesignService,
    GenesisProposalStatus,
    GenesisStrategy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def service() -> GenesisDesignService:
    return GenesisDesignService(AgentRegistry(REPOSITORY_ROOT / "definitions"))


def candidate_contract(*, extends_base: bool) -> AgentDefinition:
    registry = AgentRegistry(REPOSITORY_ROOT / "definitions")
    base = registry.get("BCA", "0.1.0")
    payload = base.model_dump(mode="json")
    payload.update(
        {
            "agent_id": "BCA_BUDGET_REVIEW",
            "name": "Budget Review Sub-Agent",
            "agent_kind": AgentKind.SUB_AGENT,
            "parent_agent_id": "BCA",
            "parent_agent_version": "0.1.0",
            "extends": (
                {"agent_id": "BCA", "version": "0.1.0"} if extends_base else None
            ),
            "purpose": (
                "Menyiapkan pemeriksaan tambahan anggaran untuk review manusia tanpa "
                "mengubah keputusan atau data keuangan."
            ),
            "version": "1.0.0",
            "status": AgentStatus.DRAFT,
        }
    )
    return AgentDefinition.model_validate(payload)


def test_reuse_returns_existing_contract_without_production_effect() -> None:
    proposal = service().propose(
        GenesisChangeRequest(
            strategy=GenesisStrategy.REUSE,
            requested_by="IT Platform",
            justification="Menggunakan capability anggaran yang sudah tersedia.",
            source_references=("specification:finance-pilot",),
            target=AgentReference(agent_id="BCA", version="0.1.0"),
        )
    )

    assert proposal.status == GenesisProposalStatus.AWAITING_HUMAN_REVIEW
    assert proposal.resolved_reference == AgentReference(agent_id="BCA", version="0.1.0")
    assert proposal.diff == ()
    assert proposal.production_effect is False
    assert proposal.next_allowed_action == "HUMAN_REVIEW"


def test_extend_validates_base_and_returns_deterministic_diff() -> None:
    proposal = service().propose(
        GenesisChangeRequest(
            strategy=GenesisStrategy.EXTEND,
            requested_by="IT Platform",
            justification="Memperluas BCA untuk kebutuhan pemeriksaan pilot yang terisolasi.",
            source_references=("specification:budget-review-pilot",),
            base=AgentReference(agent_id="BCA", version="0.1.0"),
            candidate=candidate_contract(extends_base=True),
        )
    )

    assert proposal.status == GenesisProposalStatus.AWAITING_HUMAN_REVIEW
    assert proposal.resolved_reference == AgentReference(
        agent_id="BCA_BUDGET_REVIEW", version="1.0.0"
    )
    assert proposal.diff
    assert all(validation.passed for validation in proposal.validations)


def test_create_accepts_new_draft_sub_agent_without_extends() -> None:
    proposal = service().propose(
        GenesisChangeRequest(
            strategy=GenesisStrategy.CREATE,
            requested_by="IT Platform",
            justification="Membuat candidate baru setelah REUSE dan EXTEND tidak dipilih.",
            source_references=("specification:new-budget-review",),
            candidate=candidate_contract(extends_base=False),
        )
    )

    assert proposal.status == GenesisProposalStatus.AWAITING_HUMAN_REVIEW
    assert proposal.resolved_contract is not None
    assert proposal.resolved_contract.status == AgentStatus.DRAFT
    assert proposal.production_effect is False


def test_genesis_allows_core_agent_creation_through_governance_gates() -> None:
    core = AgentRegistry(REPOSITORY_ROOT / "definitions").get("BCA").model_copy(
        update={
            "agent_id": "NEW_FINANCE_CORE",
            "name": "New Finance Core Agent",
            "status": AgentStatus.DRAFT,
        }
    )
    proposal = service().propose(
        GenesisChangeRequest(
            strategy=GenesisStrategy.CREATE,
            requested_by="IT Platform",
            justification="Pengujian pembuatan top-level agent melalui Genesis.",
            source_references=("specification:new-core",),
            candidate=core,
        )
    )

    assert proposal.status == GenesisProposalStatus.AWAITING_HUMAN_REVIEW
    organization_check = next(
        item for item in proposal.validations if item.code == "ORGANIZATION_LOCK"
    )
    assert organization_check.passed is True


def test_design_service_has_no_release_or_deploy_operation() -> None:
    genesis = service()

    assert not hasattr(genesis, "release")
    assert not hasattr(genesis, "deploy")
    assert not hasattr(genesis, "write_registry")

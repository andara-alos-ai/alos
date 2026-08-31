from pathlib import Path
from uuid import uuid4

import pytest

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentReference
from alos.agents.registry import AgentRegistry
from alos.genesis import GenesisDesignService
from alos.genesis.models import (
    GenesisReviewCreate,
    GenesisReviewDecision,
    GenesisReviewGate,
    GenesisStrategy,
    GenesisSubmitRequest,
)
from alos.genesis.pipeline import GenesisPipelineService
from alos.genesis.repository import InMemoryGenesisStore
from alos.genesis.source import SourceRegistry, SourceRegistryError
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def principal(organization_id: object, role: Role) -> Principal:
    return Principal(
        user_id=uuid4(),
        organization_id=organization_id,
        roles=frozenset({role}),
    )


def pipeline() -> GenesisPipelineService:
    definitions = REPOSITORY_ROOT / "definitions"
    return GenesisPipelineService(
        GenesisDesignService(AgentRegistry(definitions)),
        CapabilityRegistry(definitions),
        InMemoryGenesisStore(),
        SourceRegistry(definitions),
    )


def request() -> GenesisSubmitRequest:
    return GenesisSubmitRequest(
        strategy=GenesisStrategy.REUSE,
        justification="Menggunakan capability BCA yang telah dirilis untuk kebutuhan pilot.",
        source_references=("ALOS-SP-SYNTHETIC-PILOT@1.0.0",),
        target=AgentReference(agent_id="BCA", version="0.1.0"),
    )


def test_genesis_full_pipeline_requires_two_reviews_and_never_deploys() -> None:
    service = pipeline()
    organization_id = uuid4()
    requester = principal(organization_id, Role.AI_EXECUTIVE)
    business = principal(organization_id, Role.DIRECTOR)
    technical = principal(organization_id, Role.IT_ADMIN)
    releaser = principal(organization_id, Role.DIRECTOR)

    submitted = service.submit(request(), requester)
    business_reviewed = service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.BUSINESS,
            decision=GenesisReviewDecision.APPROVED,
            notes="Kebutuhan bisnis dan owner telah diverifikasi.",
        ),
        business,
    )
    approved = service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.TECHNICAL,
            decision=GenesisReviewDecision.APPROVED,
            notes="Kontrak, tools, security, dan pengujian telah diverifikasi.",
        ),
        technical,
    )
    staged = service.stage(submitted.request_id, technical)
    released = service.release(submitted.request_id, releaser)

    assert business_reviewed.status == "AWAITING_HUMAN_REVIEW"
    assert approved.status == "APPROVED"
    assert staged.status == "STAGED"
    assert released.status == "RELEASED"
    assert released.production_effect is False
    assert released.release is not None
    assert released.release.production_effect is False
    assert released.next_allowed_action == "SEPARATE_DEPLOYMENT_APPROVAL"


def test_genesis_requester_cannot_review_own_request() -> None:
    service = pipeline()
    organization_id = uuid4()
    requester = principal(organization_id, Role.DIRECTOR)
    submitted = service.submit(request(), requester)

    with pytest.raises(AuthorizationDenied, match="tidak boleh mereview"):
        service.review(
            submitted.request_id,
            GenesisReviewCreate(
                gate=GenesisReviewGate.BUSINESS,
                decision=GenesisReviewDecision.APPROVED,
                notes="Review diri sendiri harus ditolak oleh separation of duties.",
            ),
            requester,
        )


def test_genesis_draft_source_can_be_analyzed_but_cannot_enter_staging() -> None:
    service = pipeline()
    organization_id = uuid4()
    requester = principal(organization_id, Role.AI_EXECUTIVE)
    business = principal(organization_id, Role.DIRECTOR)
    technical = principal(organization_id, Role.IT_ADMIN)
    submitted = service.submit(
        GenesisSubmitRequest(
            strategy=GenesisStrategy.REUSE,
            justification="Menganalisis reuse BCA terhadap source pack A-N yang belum final.",
            source_references=("ALOS-SP-MASTER-AN-DRAFT@0.1.0",),
            target=AgentReference(agent_id="BCA", version="0.1.0"),
        ),
        requester,
    )
    service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.BUSINESS,
            decision=GenesisReviewDecision.APPROVED,
            notes="Analisis bisnis diperbolehkan tanpa mengesahkan isi sumber.",
        ),
        business,
    )
    service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.TECHNICAL,
            decision=GenesisReviewDecision.APPROVED,
            notes="Validasi teknis hanya untuk baseline draft dan data sintetis.",
        ),
        technical,
    )

    with pytest.raises(SourceRegistryError, match="tidak mengizinkan STAGE"):
        service.stage(submitted.request_id, technical)

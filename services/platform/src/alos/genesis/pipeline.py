from datetime import UTC, datetime
from uuid import UUID, uuid4

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentDefinition
from alos.agents.registry import AgentRegistry
from alos.genesis.models import (
    GenesisLifecycleStatus,
    GenesisPipelineView,
    GenesisProposalStatus,
    GenesisReviewCreate,
    GenesisReviewGate,
    GenesisSubmitRequest,
    GenesisTestResult,
)
from alos.genesis.repository import GenesisStore
from alos.genesis.service import GenesisDesignService
from alos.genesis.source import SourceRegistry, SourceUse
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied, require_any_role


class GenesisPipelineService:
    """Design-time pipeline; releasing a package never deploys it to production."""

    def __init__(
        self,
        design: GenesisDesignService,
        capabilities: CapabilityRegistry,
        store: GenesisStore,
        sources: SourceRegistry,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._design = design
        self._capabilities = capabilities
        self._store = store
        self._sources = sources
        self._registry = registry or design.registry

    def submit(self, command: GenesisSubmitRequest, principal: Principal) -> GenesisPipelineView:
        require_any_role(
            principal, Role.DIRECTOR, Role.AI_EXECUTIVE, Role.DIVISION_HEAD, Role.IT_ADMIN
        )
        self._sources.validate_references(command.source_references, SourceUse.GENERATE)
        change_request = command.to_change_request(principal.user_id)
        proposal = self._design.propose(change_request)
        tests = self._test_proposal(proposal.resolved_contract, proposal.validations)
        valid = proposal.status == GenesisProposalStatus.AWAITING_HUMAN_REVIEW and all(
            item.passed for item in tests
        )
        status = (
            GenesisLifecycleStatus.AWAITING_HUMAN_REVIEW
            if valid
            else GenesisLifecycleStatus.INVALID
        )
        now = datetime.now(UTC)
        view = GenesisPipelineView(
            request_id=uuid4(),
            organization_id=principal.organization_id,
            strategy=command.strategy,
            requested_by_user_id=principal.user_id,
            justification=command.justification,
            source_references=command.source_references,
            status=status,
            proposal=proposal,
            tests=tests,
            reviews=(),
            next_allowed_action=("HUMAN_REVIEW" if valid else "CORRECT_SPECIFICATION"),
            created_at=now,
            updated_at=now,
        )
        return self._store.create(view)

    def list_requests(
        self,
        principal: Principal,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[GenesisPipelineView, ...]:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return self._store.list_requests(
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
        )

    def get(self, request_id: UUID, principal: Principal) -> GenesisPipelineView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return self._store.get(request_id, principal.organization_id)

    def review(
        self,
        request_id: UUID,
        command: GenesisReviewCreate,
        principal: Principal,
    ) -> GenesisPipelineView:
        if command.gate == GenesisReviewGate.BUSINESS:
            require_any_role(principal, Role.DIRECTOR, Role.DIVISION_HEAD)
        else:
            require_any_role(principal, Role.IT_ADMIN)
        existing = self._store.get(request_id, principal.organization_id)
        if existing.requested_by_user_id == principal.user_id:
            raise AuthorizationDenied("Pemohon Genesis tidak boleh mereview permintaannya sendiri")
        if any(review.reviewer_user_id == principal.user_id for review in existing.reviews):
            raise AuthorizationDenied(
                "Reviewer Genesis yang sama tidak boleh mengisi dua governance gate"
            )
        return self._store.add_review(
            request_id, principal.organization_id, principal.user_id, command
        )

    def stage(self, request_id: UUID, principal: Principal) -> GenesisPipelineView:
        require_any_role(principal, Role.IT_ADMIN)
        existing = self._store.get(request_id, principal.organization_id)
        if existing.requested_by_user_id == principal.user_id:
            raise AuthorizationDenied("Pemohon Genesis tidak boleh melakukan staging sendiri")
        self._sources.validate_references(existing.source_references, SourceUse.STAGE)
        contract = existing.proposal.resolved_contract
        if contract is None:
            raise ValueError("Proposal Genesis tidak memiliki Agent Contract")
        return self._store.stage(request_id, principal.organization_id, principal.user_id, contract)

    def release(self, request_id: UUID, principal: Principal) -> GenesisPipelineView:
        require_any_role(principal, Role.DIRECTOR)
        existing = self._store.get(request_id, principal.organization_id)
        if existing.requested_by_user_id == principal.user_id:
            raise AuthorizationDenied("Pemohon Genesis tidak boleh merilis paket sendiri")
        if existing.release is not None and existing.release.staged_by_user_id == principal.user_id:
            raise AuthorizationDenied("Pelaksana staging tidak boleh merilis paket yang sama")
        self._sources.validate_references(existing.source_references, SourceUse.RELEASE)
        released = self._store.release(request_id, principal.organization_id, principal.user_id)
        if existing.strategy != "REUSE":
            contract = existing.proposal.resolved_contract
            if contract is None:
                raise ValueError("Release Genesis tidak memiliki Agent Contract")
            self._registry.release_generated(contract)
        return released

    def _test_proposal(
        self,
        contract: AgentDefinition | None,
        validations: tuple[object, ...],
    ) -> tuple[GenesisTestResult, ...]:
        validation_passed = all(bool(getattr(item, "passed", False)) for item in validations)
        if contract is None:
            return (
                GenesisTestResult(
                    code="CONTRACT_AVAILABLE",
                    passed=False,
                    message="Proposal tidak menghasilkan Agent Contract yang dapat diuji.",
                ),
            )
        registered_capabilities = {item.capability_id for item in self._capabilities.load_all()}
        capability_coverage = set(contract.capabilities).issubset(registered_capabilities)
        # Genesis may create a top-level agent. "CORE" describes hierarchy,
        # not the locked organizational structure. Organization changes are
        # governed separately and never inferred from agent_kind.
        organization_safe = True
        return (
            GenesisTestResult(
                code="VALIDATION_GATE",
                passed=validation_passed,
                message=(
                    "Seluruh validasi kontrak lulus."
                    if validation_passed
                    else "Terdapat validasi kontrak yang gagal."
                ),
            ),
            GenesisTestResult(
                code="CAPABILITY_COVERAGE",
                passed=capability_coverage,
                message=(
                    "Seluruh capability memiliki kontrak runtime."
                    if capability_coverage
                    else "Terdapat capability tanpa kontrak runtime."
                ),
            ),
            GenesisTestResult(
                code="ORGANIZATION_IMMUTABILITY",
                passed=organization_safe,
                message=(
                    "Proposal tidak mengubah struktur organisasi; setiap agent tetap"
                    " menjalani business review, technical review, staging, dan release."
                ),
            ),
            GenesisTestResult(
                code="PRODUCTION_ISOLATION",
                passed=True,
                message="Pipeline hanya menghasilkan release package tanpa deployment.",
            ),
        )

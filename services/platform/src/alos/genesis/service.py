from datetime import UTC, datetime
from uuid import uuid4

from alos.agents.contract import AgentDefinition, AgentKind, AgentReference, AgentStatus
from alos.agents.registry import AgentRegistry, RegistryError
from alos.genesis.models import (
    GenesisChangeRequest,
    GenesisFieldDiff,
    GenesisProposal,
    GenesisProposalStatus,
    GenesisStrategy,
    GenesisValidation,
)


class GenesisDesignService:
    """Build and validate proposals only; this service cannot stage, release, or deploy."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def propose(self, request: GenesisChangeRequest) -> GenesisProposal:
        if request.strategy == GenesisStrategy.REUSE:
            return self._propose_reuse(request)
        return self._propose_candidate(request)

    def _propose_reuse(self, request: GenesisChangeRequest) -> GenesisProposal:
        assert request.target is not None
        validations: list[GenesisValidation] = []
        resolved: AgentDefinition | None = None
        try:
            resolved = self._registry.get(request.target.agent_id, request.target.version)
            runnable = resolved.status in {AgentStatus.STAGED, AgentStatus.RELEASED}
            validations.append(
                GenesisValidation(
                    code="TARGET_RUNNABLE",
                    passed=runnable,
                    message=(
                        "Target terdaftar dan dapat digunakan ulang."
                        if runnable
                        else f"Status target {resolved.status} belum dapat digunakan ulang."
                    ),
                )
            )
        except KeyError:
            validations.append(
                GenesisValidation(
                    code="TARGET_EXISTS",
                    passed=False,
                    message="Target REUSE tidak ditemukan dalam Agent Registry.",
                )
            )
        return self._proposal(request, resolved, validations, ())

    def _propose_candidate(self, request: GenesisChangeRequest) -> GenesisProposal:
        assert request.candidate is not None
        candidate = request.candidate
        validations = [
            GenesisValidation(
                code="DESIGN_TIME_ONLY",
                passed=candidate.status == AgentStatus.DRAFT,
                message=(
                    "Candidate tetap DRAFT dan tidak memiliki efek production."
                    if candidate.status == AgentStatus.DRAFT
                    else "Candidate Genesis wajib berstatus DRAFT."
                ),
            ),
            GenesisValidation(
                code="ORGANIZATION_LOCK",
                passed=candidate.agent_kind != AgentKind.CORE,
                message=(
                    "Candidate tidak mengubah struktur Core atau organisasi."
                    if candidate.agent_kind != AgentKind.CORE
                    else "Genesis tidak boleh membuat atau mengubah Core Agent."
                ),
            ),
        ]

        base: AgentDefinition | None = None
        if request.strategy == GenesisStrategy.EXTEND:
            assert request.base is not None
            base = self._resolve_base(request.base, validations)
            validations.extend(self._validate_extension(candidate, request.base, base))
        elif candidate.extends is not None:
            validations.append(
                GenesisValidation(
                    code="CREATE_WITHOUT_BASE",
                    passed=False,
                    message="CREATE wajib menghasilkan kontrak baru tanpa extends.",
                )
            )

        if request.strategy == GenesisStrategy.CREATE:
            identity_is_new = not any(
                agent.agent_id == candidate.agent_id for agent in self._registry.load_all()
            )
            validations.append(
                GenesisValidation(
                    code="NEW_AGENT_IDENTITY",
                    passed=identity_is_new,
                    message=(
                        "CREATE menggunakan identitas agent baru."
                        if identity_is_new
                        else (
                            "CREATE wajib menggunakan agent_id baru; gunakan EXTEND "
                            "untuk identitas yang ada."
                        )
                    ),
                )
            )

        try:
            self._registry.validate_candidate(candidate)
            validations.append(
                GenesisValidation(
                    code="REGISTRY_COMPATIBLE",
                    passed=True,
                    message="Candidate kompatibel dengan hierarchy, versi, dan Tool Registry.",
                )
            )
        except RegistryError as exc:
            validations.append(
                GenesisValidation(
                    code="REGISTRY_COMPATIBLE",
                    passed=False,
                    message=str(exc),
                )
            )

        diff = self._build_diff(base, candidate)
        return self._proposal(request, candidate, validations, diff)

    def _resolve_base(
        self, reference: AgentReference, validations: list[GenesisValidation]
    ) -> AgentDefinition | None:
        try:
            base = self._registry.get(reference.agent_id, reference.version)
            validations.append(
                GenesisValidation(
                    code="BASE_EXISTS",
                    passed=True,
                    message="Base EXTEND ditemukan dalam Agent Registry.",
                )
            )
            runnable = base.status in {AgentStatus.STAGED, AgentStatus.RELEASED}
            validations.append(
                GenesisValidation(
                    code="BASE_RUNNABLE",
                    passed=runnable,
                    message=(
                        "Base berada pada release gate yang dapat digunakan."
                        if runnable
                        else f"Status base {base.status} belum dapat digunakan."
                    ),
                )
            )
            return base
        except KeyError:
            validations.append(
                GenesisValidation(
                    code="BASE_EXISTS",
                    passed=False,
                    message="Base EXTEND tidak ditemukan dalam Agent Registry.",
                )
            )
            return None

    @staticmethod
    def _validate_extension(
        candidate: AgentDefinition,
        reference: AgentReference,
        base: AgentDefinition | None,
    ) -> tuple[GenesisValidation, ...]:
        exact_reference = candidate.extends == reference
        validations = [
            GenesisValidation(
                code="EXTENDS_EXACT_BASE",
                passed=exact_reference,
                message=(
                    "Candidate merujuk tepat ke base yang dipilih."
                    if exact_reference
                    else "Field extends candidate tidak sama dengan base yang dipilih."
                ),
            )
        ]
        if base is not None:
            preserves_capabilities = set(base.capabilities).issubset(candidate.capabilities)
            preserves_tools = set(base.tools_allowed).issubset(candidate.tools_allowed)
            validations.extend(
                (
                    GenesisValidation(
                        code="BASE_CAPABILITIES_PRESERVED",
                        passed=preserves_capabilities,
                        message=(
                            "Seluruh capability base dipertahankan."
                            if preserves_capabilities
                            else "EXTEND tidak boleh menghapus capability base."
                        ),
                    ),
                    GenesisValidation(
                        code="BASE_TOOLS_PRESERVED",
                        passed=preserves_tools,
                        message=(
                            "Seluruh tool base dipertahankan."
                            if preserves_tools
                            else "EXTEND tidak boleh menghapus tool base."
                        ),
                    ),
                )
            )
        return tuple(validations)

    @staticmethod
    def _build_diff(
        before: AgentDefinition | None, after: AgentDefinition
    ) -> tuple[GenesisFieldDiff, ...]:
        before_payload = before.canonical_payload() if before is not None else {}
        after_payload = after.canonical_payload()
        fields = sorted(set(before_payload) | set(after_payload))
        return tuple(
            GenesisFieldDiff(
                field=field,
                before=before_payload.get(field),
                after=after_payload.get(field),
            )
            for field in fields
            if before_payload.get(field) != after_payload.get(field)
        )

    @staticmethod
    def _proposal(
        request: GenesisChangeRequest,
        resolved: AgentDefinition | None,
        validations: list[GenesisValidation],
        diff: tuple[GenesisFieldDiff, ...],
    ) -> GenesisProposal:
        valid = bool(validations) and all(item.passed for item in validations)
        reference = (
            AgentReference(agent_id=resolved.agent_id, version=resolved.version)
            if resolved is not None
            else None
        )
        return GenesisProposal(
            proposal_id=uuid4(),
            strategy=request.strategy,
            status=(
                GenesisProposalStatus.AWAITING_HUMAN_REVIEW
                if valid
                else GenesisProposalStatus.INVALID
            ),
            requested_by=request.requested_by,
            source_references=request.source_references,
            resolved_contract=resolved,
            resolved_reference=reference,
            validations=tuple(validations),
            diff=diff,
            created_at=datetime.now(UTC),
        )

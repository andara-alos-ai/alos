"""Deterministic research source decisions without retrieval or authority mutation."""

from __future__ import annotations

from alos.genesis.governed_foundations import SourceKind, SourceRequirement
from alos.runtime.context.models import (
    ContextBuildRequest,
    ContextErrorCode,
    ResearchEvidenceState,
    ResearchRiskLevel,
    ResearchSourceDecision,
    ResearchSourceDecisionKind,
)

_RISK_RANK: dict[ResearchRiskLevel, int] = {
    ResearchRiskLevel.LOW: 0,
    ResearchRiskLevel.MEDIUM: 1,
    ResearchRiskLevel.HIGH: 2,
    ResearchRiskLevel.CRITICAL: 3,
}


class ResearchSourceResolver:
    """Choose internal versus approved external research from explicit semantic facts."""

    def decide(self, request: ContextBuildRequest) -> ResearchSourceDecision:
        if request.research_domain is None:
            return _terminal_decision(
                ResearchSourceDecisionKind.NEEDS_INFORMATION,
                ContextErrorCode.RESEARCH_DOMAIN_REQUIRED,
                "A governed research domain is required before source selection.",
                request,
            )

        access = next(
            (
                item
                for item in request.research_domain_access
                if item.domain == request.research_domain
            ),
            None,
        )
        if access is None:
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.RESEARCH_DOMAIN_NOT_AUTHORIZED,
                "The research domain is absent from the authoritative access envelope.",
                request,
            )
        if not access.scope.contains(request.requested_scope):
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.RESEARCH_DOMAIN_SCOPE_MISMATCH,
                "The requested scope is outside the authorized research domain scope.",
                request,
            )
        if not request.source_requirements:
            return _terminal_decision(
                ResearchSourceDecisionKind.NEEDS_INFORMATION,
                ContextErrorCode.RESEARCH_SOURCE_REQUIREMENTS_MISSING,
                "Research source requirements must be explicit before source selection.",
                request,
            )
        requested_source_kinds = {item.kind for item in request.source_requirements}
        if not requested_source_kinds.issubset(set(access.allowed_source_kinds)):
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.RESEARCH_SOURCE_NOT_AUTHORIZED,
                "A requested source kind is outside the authorized domain source envelope.",
                request,
            )
        external_requirements = tuple(
            item for item in request.source_requirements if item.kind == SourceKind.EXTERNAL
        )
        if any(
            not item.provenance_required
            or not item.citation_required
            or not item.reliability_required
            for item in external_requirements
        ):
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.EXTERNAL_SOURCE_GOVERNANCE_REQUIRED,
                "External research requires provenance, citation, and reliability controls.",
                request,
            )
        if request.research_context is None:
            return _terminal_decision(
                ResearchSourceDecisionKind.NEEDS_INFORMATION,
                ContextErrorCode.RESEARCH_CONTEXT_REQUIRED,
                "Evidence, risk, cost, and source policy facts are required for research.",
                request,
            )

        facts = request.research_context
        external_required = SourceKind.EXTERNAL in requested_source_kinds
        if facts.internal_evidence_state != ResearchEvidenceState.SUFFICIENT:
            if not external_required:
                return _terminal_decision(
                    ResearchSourceDecisionKind.NEEDS_INFORMATION,
                    ContextErrorCode.INTERNAL_EVIDENCE_INSUFFICIENT,
                    "Internal evidence is insufficient and external research was not requested.",
                    request,
                )
        elif not external_required:
            return ResearchSourceDecision(
                decision=ResearchSourceDecisionKind.INTERNAL_SUFFICIENT,
                rationale=(
                    "Approved internal evidence satisfies the explicit research source "
                    "requirements within the authorized domain scope."
                ),
                source_requirements=_ordered_requirements(request.source_requirements),
                evidence_gaps=(),
            )

        policy = facts.source_policy
        if not (
            policy.external_research_allowed
            and policy.approved_external_tool_available
            and policy.external_egress_approved
        ):
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.EXTERNAL_RESEARCH_NOT_AUTHORIZED,
                "External research lacks an approved tool, egress path, or policy allowance.",
                request,
            )
        if _RISK_RANK[facts.risk_level] > _RISK_RANK[policy.maximum_external_risk]:
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.EXTERNAL_RESEARCH_RISK_EXCEEDED,
                "External research risk exceeds the authoritative policy threshold.",
                request,
            )
        if facts.estimated_external_cost_usd > policy.max_external_cost_usd:
            return _terminal_decision(
                ResearchSourceDecisionKind.BLOCKED,
                ContextErrorCode.EXTERNAL_RESEARCH_COST_EXCEEDED,
                "Estimated external research cost exceeds the authoritative policy budget.",
                request,
            )
        return ResearchSourceDecision(
            decision=ResearchSourceDecisionKind.EXTERNAL_RESEARCH_REQUIRED,
            rationale=(
                "External research is semantically required and all supplied policy, risk, "
                "cost, tool, egress, domain, and scope constraints permit the governed path."
            ),
            source_requirements=_ordered_requirements(request.source_requirements),
            evidence_gaps=tuple(sorted(facts.evidence_gaps)),
        )


def _terminal_decision(
    decision: ResearchSourceDecisionKind,
    error_code: ContextErrorCode,
    rationale: str,
    request: ContextBuildRequest,
) -> ResearchSourceDecision:
    evidence_gaps = (
        tuple(sorted(request.research_context.evidence_gaps))
        if request.research_context is not None
        else ()
    )
    return ResearchSourceDecision(
        decision=decision,
        rationale=rationale,
        source_requirements=_ordered_requirements(request.source_requirements),
        evidence_gaps=evidence_gaps,
        error_code=error_code,
    )


def _ordered_requirements(
    requirements: tuple[SourceRequirement, ...],
) -> tuple[SourceRequirement, ...]:
    return tuple(
        sorted(
            requirements,
            key=lambda item: (
                item.kind.value,
                item.purpose,
                item.provenance_required,
                item.citation_required,
                item.freshness_required,
                item.reliability_required,
            ),
        )
    )

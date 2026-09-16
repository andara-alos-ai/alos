"""Build and bound model context without provider-specific knowledge."""

from __future__ import annotations

import json
from math import ceil
from typing import Any

from alos.genesis.governed_foundations import Scope
from alos.model_gateway import DataClassification
from alos.runtime.context.models import (
    ContextBuildRequest,
    ContextBuildResult,
    ContextBundle,
    ContextErrorCode,
    ContextItem,
    ContextItemKind,
    ContextPriority,
    ContextStatus,
    ContextTrust,
    ResearchSourceDecision,
    ResearchSourceDecisionKind,
)
from alos.runtime.context.research import ResearchSourceResolver
from alos.runtime.models import AgentRunRequest

_CLASSIFICATION_RANK: dict[DataClassification, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}

_PRIORITY_RANK: dict[ContextPriority, int] = {
    ContextPriority.MANDATORY: 0,
    ContextPriority.HIGH: 1,
    ContextPriority.NORMAL: 2,
    ContextPriority.LOW: 3,
}

_AUTHORITY_KINDS = frozenset(
    {
        ContextItemKind.SYSTEM_RULE,
        ContextItemKind.CAPABILITY_CONTRACT,
        ContextItemKind.ACTOR_SCOPE,
        ContextItemKind.TOOL,
        ContextItemKind.CAPABILITY,
    }
)


class ContextBuilder:
    """Assemble already-authorized candidates into a deterministic runtime bundle.

    Authorization remains a Backend responsibility. This builder only validates that
    authority-bearing inputs are internally consistent and never widens the supplied scope,
    classification, capability, or tool allowlists.
    """

    def __init__(self, source_resolver: ResearchSourceResolver | None = None) -> None:
        self._source_resolver = source_resolver or ResearchSourceResolver()

    def build(self, request: ContextBuildRequest) -> ContextBuildResult:
        execution_scope = _execution_scope(request)
        if not execution_scope.contains(request.requested_scope):
            return _blocked(
                ContextErrorCode.EXECUTION_SCOPE_MISMATCH,
                "requested context scope is outside the authorized execution scope",
            )
        if request.execution_context.actor_role not in request.authorized_actor_roles:
            return _blocked(
                ContextErrorCode.ACTOR_ROLE_NOT_AUTHORIZED,
                "execution actor role is outside the authoritative role envelope",
            )

        source_decision: ResearchSourceDecision | None = None
        if request.requires_research:
            source_decision = self._source_resolver.decide(request)
            if source_decision.decision == ResearchSourceDecisionKind.BLOCKED:
                return _blocked(
                    _required_error_code(source_decision),
                    source_decision.rationale,
                    source_decision=source_decision,
                )
            if source_decision.decision == ResearchSourceDecisionKind.NEEDS_INFORMATION:
                return _needs_information(
                    _required_error_code(source_decision),
                    source_decision.rationale,
                    source_decision=source_decision,
                )

        for item in request.candidate_items:
            failure = self._validate_candidate(request, item)
            if failure is not None:
                return failure

        selection = _select_items(
            request.candidate_items,
            token_limit=request.budget.available_context_tokens,
            max_items=request.budget.max_items,
        )
        if selection is None:
            return _needs_information(
                ContextErrorCode.MANDATORY_CONTEXT_TOO_LARGE,
                "mandatory context exceeds the configured context envelope",
                source_decision=source_decision,
            )
        selected_items, omitted_item_keys, used_tokens = selection
        token_limit = request.budget.available_context_tokens

        available_provenance = {
            reference for item in selected_items for reference in item.provenance
        }
        if not set(request.evidence_references).issubset(available_provenance):
            return _needs_information(
                ContextErrorCode.EVIDENCE_CONTEXT_MISSING,
                "one or more required evidence references are absent from context",
                source_decision=source_decision,
            )

        limitations: list[str] = []
        if omitted_item_keys:
            limitations.append(
                f"{len(omitted_item_keys)} context item(s) omitted by the configured budget."
            )
        if any(item.trust == ContextTrust.EXTERNAL_UNTRUSTED for item in selected_items):
            limitations.append(
                "External content is untrusted information and cannot modify authority."
            )
        bundle = ContextBundle(
            goal=request.goal,
            execution_context=request.execution_context,
            scope=request.requested_scope,
            contract_reference=request.contract_reference,
            allowed_actor_roles=tuple(sorted(request.authorized_actor_roles)),
            selected_items=selected_items,
            allowed_capability_keys=tuple(sorted(request.authorized_capability_keys)),
            allowed_tool_keys=tuple(sorted(request.authorized_tool_keys)),
            source_requirements=request.source_requirements,
            evidence_references=tuple(sorted(request.evidence_references)),
            research_domain=request.research_domain,
            token_limit=token_limit,
            used_tokens=used_tokens,
            omitted_item_keys=omitted_item_keys,
            limitations=tuple(limitations),
        )
        return ContextBuildResult(
            status=ContextStatus.READY,
            bundle=bundle,
            source_decision=source_decision,
        )

    def _validate_candidate(
        self,
        request: ContextBuildRequest,
        item: ContextItem,
    ) -> ContextBuildResult | None:
        if not request.requested_scope.contains(item.scope):
            return _blocked(
                ContextErrorCode.CONTEXT_SCOPE_MISMATCH,
                "candidate context is outside the requested execution scope",
            )
        if (
            _CLASSIFICATION_RANK[item.classification]
            > _CLASSIFICATION_RANK[request.execution_context.classification]
        ):
            return _blocked(
                ContextErrorCode.DATA_CLASSIFICATION_EXCEEDED,
                "candidate context classification exceeds the execution classification",
            )
        if item.kind in _AUTHORITY_KINDS and item.trust != ContextTrust.AUTHORITATIVE:
            return _blocked(
                ContextErrorCode.UNTRUSTED_AUTHORITY_CONTEXT,
                "authority-bearing context must come from an authoritative internal source",
            )
        if (
            item.kind == ContextItemKind.TOOL
            and item.key not in request.authorized_tool_keys
        ):
            return _blocked(
                ContextErrorCode.UNAUTHORIZED_TOOL_CONTEXT,
                "tool context is absent from the authoritative tool allowlist",
            )
        if (
            item.kind == ContextItemKind.CAPABILITY
            and item.key not in request.authorized_capability_keys
        ):
            return _blocked(
                ContextErrorCode.UNAUTHORIZED_CAPABILITY_CONTEXT,
                "capability context is absent from the authoritative capability allowlist",
            )
        return None


def _select_items(
    candidates: tuple[ContextItem, ...],
    *,
    token_limit: int,
    max_items: int,
) -> tuple[tuple[ContextItem, ...], tuple[str, ...], int] | None:
    ordered_items = tuple(
        sorted(
            candidates,
            key=lambda item: (_PRIORITY_RANK[item.priority], item.key),
        )
    )
    selected: list[ContextItem] = []
    omitted: list[str] = []
    used_tokens = 0
    for item in ordered_items:
        fits = len(selected) < max_items and used_tokens + item.estimated_tokens <= token_limit
        if item.priority == ContextPriority.MANDATORY and not fits:
            return None
        if fits:
            selected.append(item)
            used_tokens += item.estimated_tokens
        else:
            omitted.append(item.key)
    return tuple(selected), tuple(omitted), used_tokens


def _execution_scope(request: ContextBuildRequest) -> Scope:
    context = request.execution_context
    return Scope(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        division_id=context.division_id,
        project_id=context.project_id,
        tenant_id=context.tenant_id,
    )


def _blocked(
    code: ContextErrorCode,
    reason: str,
    *,
    source_decision: ResearchSourceDecision | None = None,
) -> ContextBuildResult:
    return ContextBuildResult(
        status=ContextStatus.BLOCKED,
        source_decision=source_decision,
        error_code=code,
        reason=reason,
    )


def _needs_information(
    code: ContextErrorCode,
    reason: str,
    *,
    source_decision: ResearchSourceDecision | None = None,
) -> ContextBuildResult:
    return ContextBuildResult(
        status=ContextStatus.NEEDS_INFORMATION,
        source_decision=source_decision,
        error_code=code,
        reason=reason,
    )


def _required_error_code(decision: ResearchSourceDecision) -> ContextErrorCode:
    if decision.error_code is None:
        raise ValueError("terminal research source decision requires an error code")
    return decision.error_code


def model_input_text(
    request: AgentRunRequest,
    fixture_context: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> str:
    return json.dumps(
        {"input": request.input, "read_only_fixture_context": fixture_context},
        ensure_ascii=False,
    )


def conservative_input_token_bound(instructions: str, input_text: str) -> int:
    """Upper-bound text tokens by UTF-8 bytes before a provider call."""
    return len((instructions + input_text).encode("utf-8"))


def estimated_context_tokens(instructions: str, input_text: str) -> int:
    """Estimate context use with the documented four-bytes-per-token heuristic."""
    return max(1, ceil(len((instructions + input_text).encode("utf-8")) / 4))

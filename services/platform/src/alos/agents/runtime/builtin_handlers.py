import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import CapabilityExecutionMode
from alos.agents.runtime.handlers import CapabilityHandlerRegistry
from alos.agents.runtime.models import (
    AgentExecutionPlan,
    CapabilityHandlerOutput,
    CapabilityVerificationStatus,
)
from alos.llm import DataClassification, LLMGateway, LLMRequest, LLMResultStatus


def _payload_digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _finite_decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _generic_deterministic(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    return CapabilityHandlerOutput(
        output_reference={
            "result": "PROCESSED",
            "capability": plan.capability,
            "input_digest": _payload_digest(payload),
            "evaluated_fields": sorted(str(key) for key in payload),
        },
        evidence_references=plan.input_references,
    )


def _lead_validation(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    has_contact = bool(payload.get("phone") or payload.get("email"))
    consent = payload.get("consent_recorded") is True
    valid = has_contact and consent
    return CapabilityHandlerOutput(
        output_reference={
            "valid": valid,
            "has_contact_channel": has_contact,
            "consent_recorded": consent,
        },
        warnings=(() if valid else ("Lead tidak memenuhi consent atau kanal kontak wajib.",)),
    )


def _progress_variance(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    claimed = _finite_decimal(payload.get("claimed_progress"))
    measured = _finite_decimal(payload.get("measured_progress"))
    if claimed is not None and measured is not None:
        variance = measured - claimed
        warnings: tuple[str, ...] = ()
    else:
        claimed = measured = variance = Decimal("0")
        warnings = ("Data progres belum lengkap atau bukan angka valid.",)
    return CapabilityHandlerOutput(
        output_reference={
            "claimed_progress": str(claimed),
            "measured_progress": str(measured),
            "variance": str(variance),
        },
        evidence_references=plan.input_references,
        warnings=warnings,
    )


def _completeness(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    required_value = payload.get("required_items", [])
    provided_value = payload.get("provided_items", [])
    required = {str(item) for item in required_value} if isinstance(required_value, list) else set()
    provided = {str(item) for item in provided_value} if isinstance(provided_value, list) else set()
    missing = sorted(required - provided)
    return CapabilityHandlerOutput(
        output_reference={"complete": not missing, "missing_items": missing},
        evidence_references=plan.input_references,
        warnings=(("Persyaratan belum lengkap.",) if missing else ()),
    )


def _budget_check(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    amount = _finite_decimal(payload.get("amount"))
    available = _finite_decimal(payload.get("available_amount"))
    if amount is None or available is None:
        return CapabilityHandlerOutput(
            output_reference={"database_verification_required": True},
            evidence_references=plan.input_references,
            warnings=(
                "Nilai budget tidak tersedia atau tidak valid; verifikasi database diperlukan.",
            ),
            verification_status=CapabilityVerificationStatus.PROVISIONAL,
        )
    return CapabilityHandlerOutput(
        output_reference={
            "amount": str(amount),
            "available_amount": str(available),
            "available": available >= amount,
        },
        evidence_references=plan.input_references,
    )


def _reconcile(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    expected = _finite_decimal(payload.get("payment_amount"))
    actual = _finite_decimal(payload.get("transaction_amount"))
    if expected is None or actual is None:
        return CapabilityHandlerOutput(
            output_reference={"database_verification_required": True},
            evidence_references=plan.input_references,
            warnings=(
                "Nilai pembayaran tidak tersedia atau tidak valid; verifikasi database diperlukan.",
            ),
            verification_status=CapabilityVerificationStatus.PROVISIONAL,
        )
    difference = actual - expected
    return CapabilityHandlerOutput(
        output_reference={"difference": str(difference), "matched": difference == 0},
        evidence_references=plan.input_references,
    )


def _ai_handler(gateway: LLMGateway):
    def handle(
        plan: AgentExecutionPlan, payload: Mapping[str, object]
    ) -> CapabilityHandlerOutput:
        classification_name = str(payload.get("data_classification", "INTERNAL"))
        classification = DataClassification.__members__.get(
            classification_name, DataClassification.INTERNAL
        )
        result = gateway.generate(
            LLMRequest(
                prompt_id="agent.structured-analysis",
                input_data={"capability": plan.capability, "input": dict(payload)},
                classification=classification,
                safety_identifier=str(plan.correlation_id),
            )
        )
        verification = (
            CapabilityVerificationStatus.PROVISIONAL
            if result.status == LLMResultStatus.COMPLETED
            else CapabilityVerificationStatus.UNVERIFIED
        )
        metadata: dict[str, object] = {
            "llm_status": result.status.value,
            "provider": result.provider.value,
            "model": result.model or "",
            "prompt_id": result.prompt_id,
            "prompt_version": result.prompt_version,
            "prompt_digest": result.prompt_digest,
            "provider_request_id": result.provider_request_id or "",
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "latency_ms": result.latency_ms,
            "redacted_fields": list(result.redacted_fields),
        }
        return CapabilityHandlerOutput(
            output_reference=result.output,
            evidence_references=plan.input_references,
            warnings=result.warnings or ("Hasil AI wajib diverifikasi manusia.",),
            verification_status=verification,
            provider_metadata=metadata,
        )

    return handle


def build_default_handler_registry(
    capabilities: CapabilityRegistry, gateway: LLMGateway
) -> CapabilityHandlerRegistry:
    registry = CapabilityHandlerRegistry()
    special = {
        "validate_lead_fields": _lead_validation,
        "calculate_progress_variance": _progress_variance,
        "check_completeness": _completeness,
        "identify_missing_evidence": _completeness,
        "check_budget_deterministically": _budget_check,
        "match_transactions_deterministically": _reconcile,
    }
    ai = _ai_handler(gateway)
    for contract in capabilities.load_all():
        handler = (
            ai
            if contract.execution_mode == CapabilityExecutionMode.AI_ASSISTED
            else special.get(contract.capability_id, _generic_deterministic)
        )
        registry.register(contract.capability_id, contract.handler_id, handler)
    return registry

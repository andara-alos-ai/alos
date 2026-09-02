import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import CapabilityExecutionMode
from alos.agents.runtime.handlers import CapabilityHandlerRegistry
from alos.agents.runtime.models import (
    AgentExecutionPlan,
    CapabilityHandlerOutput,
    CapabilityVerificationStatus,
)
from alos.llm import LLMGateway


def _payload_digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _provisional(plan: AgentExecutionPlan, message: str) -> CapabilityHandlerOutput:
    return CapabilityHandlerOutput(
        output_reference={"database_verification_required": True},
        evidence_references=plan.input_references,
        warnings=(message,),
        verification_status=CapabilityVerificationStatus.PROVISIONAL,
    )


def _aggregate_verified_facts(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    facts = payload.get("verified_facts")
    references = payload.get("source_references")
    if not isinstance(facts, list) or not isinstance(references, list):
        return _provisional(
            plan,
            "verified_facts dan source_references wajib berasal dari data terverifikasi.",
        )
    ready = bool(facts) and bool(references)
    return CapabilityHandlerOutput(
        output_reference={
            "fact_count": len(facts),
            "source_count": len({str(item) for item in references}),
            "facts_digest": _payload_digest({"facts": facts}),
            "ready": ready,
        },
        evidence_references=plan.input_references,
        warnings=() if ready else ("Fakta atau referensi sumber belum lengkap.",),
    )


def _validate_evidence_metadata(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    checksum_valid = payload.get("checksum_valid") is True
    scan_status = str(payload.get("scan_status", ""))
    valid = checksum_valid and scan_status in {"CLEAN", "NOT_CONFIGURED"}
    return CapabilityHandlerOutput(
        output_reference={
            "valid": valid,
            "checksum_valid": checksum_valid,
            "scan_status": scan_status,
        },
        evidence_references=plan.input_references,
        warnings=() if valid else ("Metadata atau scan evidence belum valid.",),
        verification_status=(
            CapabilityVerificationStatus.VERIFIED
            if checksum_valid and scan_status == "CLEAN"
            else CapabilityVerificationStatus.PROVISIONAL
        ),
    )


def _monitor_deadline(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    evaluated_at = _timestamp(payload.get("evaluated_at")) or datetime.now(UTC)
    due_dates = payload.get("due_dates")
    if not isinstance(due_dates, list):
        return _provisional(plan, "due_dates wajib berupa daftar timestamp ISO-8601.")
    parsed = sorted(item for value in due_dates if (item := _timestamp(value)) is not None)
    invalid_count = len(due_dates) - len(parsed)
    overdue = [due for due in parsed if due < evaluated_at]
    return CapabilityHandlerOutput(
        output_reference={
            "evaluated_at": evaluated_at.isoformat(),
            "total_count": len(parsed),
            "overdue_count": len(overdue),
            "next_due_at": parsed[0].isoformat() if parsed else None,
        },
        evidence_references=plan.input_references,
        warnings=(
            (f"{invalid_count} deadline tidak valid.",)
            if invalid_count
            else (() if not overdue else ("Terdapat deadline melewati tenggat.",))
        ),
        verification_status=(
            CapabilityVerificationStatus.PROVISIONAL
            if invalid_count
            else CapabilityVerificationStatus.VERIFIED
        ),
    )


def build_default_handler_registry(
    capabilities: CapabilityRegistry, _gateway: LLMGateway
) -> CapabilityHandlerRegistry:
    registry = CapabilityHandlerRegistry()
    handlers = {
        "aggregate_verified_facts": _aggregate_verified_facts,
        "validate_evidence_metadata": _validate_evidence_metadata,
        "monitor_capa_deadline": _monitor_deadline,
    }
    deterministic_ids = {
        item.capability_id
        for item in capabilities.load_all()
        if item.execution_mode == CapabilityExecutionMode.DETERMINISTIC
    }
    if deterministic_ids != set(handlers):
        raise ValueError("Capability Registry tidak konsisten dengan shared runtime kernel")
    for capability in capabilities.load_all():
        registry.register(
            capability.capability_id,
            capability.handler_id,
            handlers[capability.capability_id],
        )
    return registry

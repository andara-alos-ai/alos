import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import CapabilityExecutionMode
from alos.agents.runtime.handlers import CapabilityHandler, CapabilityHandlerRegistry
from alos.agents.runtime.models import (
    AgentExecutionPlan,
    CapabilityHandlerOutput,
    CapabilityVerificationStatus,
)
from alos.governance.approval_policy import (
    PaymentApprovalPolicy,
    PaymentApprovalPolicyRegistry,
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


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _provisional(
    plan: AgentExecutionPlan, message: str
) -> CapabilityHandlerOutput:
    return CapabilityHandlerOutput(
        output_reference={"database_verification_required": True},
        evidence_references=plan.input_references,
        warnings=(message,),
        verification_status=CapabilityVerificationStatus.PROVISIONAL,
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


def _document_metadata(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    valid = payload.get("document_metadata_valid") is True
    count = payload.get("document_version_count")
    return CapabilityHandlerOutput(
        output_reference={"valid": valid, "document_version_count": count},
        evidence_references=plan.input_references,
        warnings=(() if valid else ("Metadata dokumen belum terverifikasi server.",)),
        verification_status=(
            CapabilityVerificationStatus.VERIFIED
            if valid
            else CapabilityVerificationStatus.PROVISIONAL
        ),
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


def _approval_route_handler(policy: PaymentApprovalPolicy) -> CapabilityHandler:
    def handle(
        plan: AgentExecutionPlan, payload: Mapping[str, object]
    ) -> CapabilityHandlerOutput:
        amount = _finite_decimal(payload.get("amount"))
        if amount is None:
            return CapabilityHandlerOutput(
                output_reference={"database_verification_required": True},
                evidence_references=plan.input_references,
                warnings=("Nominal tidak tersedia untuk routing approval.",),
                verification_status=CapabilityVerificationStatus.PROVISIONAL,
            )
        tier = policy.route_for(amount)
        return CapabilityHandlerOutput(
            output_reference={
                "route": tier.route,
                "required_role": tier.required_role,
                "sla_hours": tier.sla_hours,
                "policy_id": policy.policy_id,
                "policy_version": policy.version,
                "self_approval_allowed": False,
            },
            evidence_references=plan.input_references,
        )

    return handle


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
    expected_reference = payload.get("payment_reference")
    actual_reference = payload.get("transaction_reference")
    expected_currency = payload.get("payment_currency")
    actual_currency = payload.get("currency")
    reference_match = expected_reference == actual_reference
    currency_match = expected_currency == actual_currency
    return CapabilityHandlerOutput(
        output_reference={
            "difference": str(difference),
            "reference_match": reference_match,
            "currency_match": currency_match,
            "matched": difference == 0 and reference_match and currency_match,
        },
        evidence_references=plan.input_references,
    )


def _verified_fact_aggregate(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    facts = payload.get("verified_facts")
    references = _strings(payload.get("source_references"))
    if not isinstance(facts, list):
        return _provisional(plan, "verified_facts wajib berasal dari data sistem terverifikasi.")
    ready = bool(facts) and bool(references)
    return CapabilityHandlerOutput(
        output_reference={
            "fact_count": len(facts),
            "source_count": len(set(references)),
            "facts_digest": _payload_digest({"facts": facts}),
            "ready": ready,
        },
        evidence_references=plan.input_references,
        warnings=(() if ready else ("Fakta atau referensi sumber belum lengkap.",)),
    )


def _cashflow_impact(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    amount = _finite_decimal(payload.get("amount"))
    available = _finite_decimal(payload.get("available_cash"))
    committed = _finite_decimal(payload.get("committed_cash", 0))
    if amount is None or available is None or committed is None:
        return _provisional(plan, "Data cashflow belum lengkap atau bukan angka valid.")
    projected = available - committed - amount
    return CapabilityHandlerOutput(
        output_reference={
            "amount": str(amount),
            "projected_available_cash": str(projected),
            "sufficient": projected >= 0,
        },
        evidence_references=plan.input_references,
        warnings=(() if projected >= 0 else ("Dampak cashflow melampaui kas tersedia.",)),
    )


def _sales_assignment(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    candidates = sorted(set(_strings(payload.get("candidate_user_ids"))))
    workload_value = payload.get("open_workload", {})
    workload = workload_value if isinstance(workload_value, Mapping) else {}
    if not candidates:
        return _provisional(plan, "Tidak ada kandidat Sales PIC yang aktif.")
    selected = min(
        candidates,
        key=lambda item: (_finite_decimal(workload.get(item)) or Decimal(0), item),
    )
    return CapabilityHandlerOutput(
        output_reference={
            "assigned_user_id": selected,
            "assignment_rule": "LOWEST_OPEN_WORKLOAD_THEN_ID",
        },
        evidence_references=plan.input_references,
    )


def _kpi_calculation(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    numerator = _finite_decimal(payload.get("numerator"))
    denominator = _finite_decimal(payload.get("denominator"))
    target = _finite_decimal(payload.get("target"))
    if numerator is None or denominator is None or denominator == 0:
        return _provisional(plan, "Komponen KPI tidak valid atau denominator bernilai nol.")
    value = numerator / denominator
    if target is None:
        return CapabilityHandlerOutput(
            output_reference={"value": str(value)},
            evidence_references=plan.input_references,
            warnings=("Target KPI belum dikonfigurasi; nilai hanya bersifat observasi.",),
            verification_status=CapabilityVerificationStatus.PROVISIONAL,
        )
    return CapabilityHandlerOutput(
        output_reference={
            "value": str(value),
            "target": str(target),
            "variance": str(value - target),
            "target_met": value >= target,
        },
        evidence_references=plan.input_references,
    )


def _finance_variance(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    expected = _finite_decimal(payload.get("expected_value"))
    actual = _finite_decimal(payload.get("actual_value"))
    if expected is None or actual is None:
        return _provisional(plan, "Nilai expected dan actual wajib berupa angka valid.")
    return CapabilityHandlerOutput(
        output_reference={
            "expected_value": str(expected),
            "actual_value": str(actual),
            "variance": str(actual - expected),
        },
        evidence_references=plan.input_references,
    )


def _requirements_by_capability(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    keys = {
        "check_brand_requirements": ("required_requirements", "provided_requirements"),
        "check_permit_requirements": ("required_permits", "available_permits"),
        "check_personnel_file_completeness": (
            "required_documents",
            "provided_documents",
        ),
        "check_site_evidence": ("required_evidence", "provided_evidence"),
    }
    required_key, provided_key = keys[plan.capability]
    required = set(_strings(payload.get(required_key)))
    provided = set(_strings(payload.get(provided_key)))
    missing = sorted(required - provided)
    all_verified = payload.get("all_verified") is True
    output: dict[str, object] = {
        "complete": not missing,
        "required_count": len(required),
        "provided_count": len(required & provided),
        "missing_items": missing,
    }
    if plan.capability == "check_site_evidence":
        output.update(
            {"all_verified": all_verified, "acceptable": not missing and all_verified}
        )
    warnings: tuple[str, ...] = (
        () if not missing else ("Persyaratan wajib belum lengkap.",)
    )
    if plan.capability == "check_site_evidence" and not all_verified:
        warnings += ("Bukti lokasi belum terverifikasi.",)
    return CapabilityHandlerOutput(
        output_reference=output,
        evidence_references=plan.input_references,
        warnings=warnings,
    )


def _separation_of_duties(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    requester = str(payload.get("requester_user_id", ""))
    approver = str(payload.get("approver_user_id", ""))
    separated = bool(requester and approver and requester != approver)
    return CapabilityHandlerOutput(
        output_reference={"separated": separated, "self_approval_allowed": False},
        evidence_references=plan.input_references,
        warnings=(() if separated else ("Requester dan approver wajib berbeda.",)),
    )


def _attendance_exception(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    scheduled = _finite_decimal(payload.get("scheduled_minutes"))
    worked = _finite_decimal(payload.get("worked_minutes"))
    tolerance = _finite_decimal(payload.get("tolerance_minutes", 0))
    if scheduled is None or worked is None or tolerance is None:
        return _provisional(plan, "Data kehadiran belum lengkap atau bukan angka valid.")
    shortage = max(Decimal(0), scheduled - worked)
    classification = "EXCEPTION" if shortage > tolerance else "NORMAL"
    return CapabilityHandlerOutput(
        output_reference={
            "classification": classification,
            "shortage_minutes": str(shortage),
            "requires_human_review": classification == "EXCEPTION",
        },
        evidence_references=plan.input_references,
        warnings=(() if classification == "NORMAL" else ("Exception kehadiran.",)),
    )


def _document_access(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    role = str(payload.get("requested_role", ""))
    allowed = role in set(_strings(payload.get("allowed_roles")))
    return CapabilityHandlerOutput(
        output_reference={
            "classification": str(payload.get("classification", "INTERNAL")),
            "access_allowed": allowed,
        },
        evidence_references=plan.input_references,
        warnings=(() if allowed else ("Role tidak memiliki akses dokumen.",)),
    )


def _risk_classification(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    impact = _finite_decimal(payload.get("impact_score"))
    probability = _finite_decimal(payload.get("probability_score"))
    if impact is None or probability is None:
        return _provisional(plan, "Skor dampak dan probabilitas wajib tersedia.")
    score = impact * probability
    severity = (
        "CRITICAL"
        if score >= 16
        else "HIGH"
        if score >= 10
        else "MEDIUM"
        if score >= 5
        else "LOW"
    )
    return CapabilityHandlerOutput(
        output_reference={"risk_score": str(score), "severity": severity},
        evidence_references=plan.input_references,
    )


def _sop_plan(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    items = list(_strings(payload.get("released_steps") or payload.get("required_items")))
    if plan.capability == "create_checklist":
        checklist = [
            {"sequence": index, "item": item, "status": "OPEN"}
            for index, item in enumerate(items, 1)
        ]
        output: dict[str, object] = {"checklist": checklist, "item_count": len(items)}
    else:
        output = {
            "ordered_steps": items,
            "step_count": len(items),
            "plan_digest": _payload_digest({"steps": items}),
        }
    return CapabilityHandlerOutput(
        output_reference=output,
        evidence_references=plan.input_references,
        warnings=(() if items else ("Konfigurasi SOP belum memiliki item.",)),
    )


def _interview_task(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    scheduled_at = _timestamp(payload.get("scheduled_at"))
    if scheduled_at is None:
        return _provisional(plan, "Jadwal interview tidak valid.")
    return CapabilityHandlerOutput(
        output_reference={
            "candidate_id": str(payload.get("candidate_id")),
            "interviewer_user_id": str(payload.get("interviewer_user_id")),
            "scheduled_at": scheduled_at.isoformat(),
            "status": "PROPOSED",
        },
        evidence_references=plan.input_references,
    )


def _lead_deduplication(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    known = {item.lower() for item in _strings(payload.get("existing_identifiers"))}
    identifiers = {
        str(value).strip().lower()
        for value in (payload.get("email"), payload.get("phone"))
        if value
    }
    matches = sorted(known & identifiers)
    return CapabilityHandlerOutput(
        output_reference={"duplicate": bool(matches), "matched_identifiers": matches},
        evidence_references=plan.input_references,
        warnings=(() if not matches else ("Lead berpotensi duplikat.",)),
    )


def _duplicate_payment(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    fingerprint = str(payload.get("payment_fingerprint", ""))
    duplicate = fingerprint in set(_strings(payload.get("existing_fingerprints")))
    return CapabilityHandlerOutput(
        output_reference={"duplicate": duplicate, "payment_fingerprint": fingerprint},
        evidence_references=plan.input_references,
        warnings=(() if not duplicate else ("Fingerprint pembayaran sudah terdaftar.",)),
    )


def _invoice_rules(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    amount = _finite_decimal(payload.get("amount"))
    tax_amount = _finite_decimal(payload.get("tax_amount"))
    corrections: list[str] = []
    if amount is None or amount <= 0:
        corrections.append("amount_invalid")
    if tax_amount is None or tax_amount < 0:
        corrections.append("tax_amount_invalid")
    if not str(payload.get("invoice_number", "")).strip():
        corrections.append("invoice_number_missing")
    return CapabilityHandlerOutput(
        output_reference={"valid": not corrections, "corrections": corrections},
        evidence_references=plan.input_references,
        warnings=(() if not corrections else ("Invoice memerlukan koreksi.",)),
    )


def _project_blocker(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    blockers = sorted(
        set(_strings(payload.get("required_permits")))
        - set(_strings(payload.get("active_permits")))
    )
    return CapabilityHandlerOutput(
        output_reference={"blocked": bool(blockers), "blockers": blockers},
        evidence_references=plan.input_references,
        warnings=(() if not blockers else ("Proyek memiliki blocker izin.",)),
    )


def _deadline_monitor(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    evaluated_at = _timestamp(payload.get("evaluated_at")) or datetime.now(UTC)
    due_dates_value = payload.get("due_dates")
    if isinstance(due_dates_value, list):
        parsed = sorted(
            due
            for value in due_dates_value
            if (due := _timestamp(value)) is not None
        )
        overdue = [due for due in parsed if due < evaluated_at]
        invalid_count = len(due_dates_value) - len(parsed)
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
                else (() if not overdue else ("Terdapat CAPA melewati deadline.",))
            ),
            verification_status=(
                CapabilityVerificationStatus.PROVISIONAL
                if invalid_count
                else CapabilityVerificationStatus.VERIFIED
            ),
        )
    due_at = _timestamp(payload.get("due_at"))
    if due_at is None:
        return _provisional(plan, "Deadline tidak valid.")
    overdue_seconds = max(0, int((evaluated_at - due_at).total_seconds()))
    return CapabilityHandlerOutput(
        output_reference={
            "due_at": due_at.isoformat(),
            "evaluated_at": evaluated_at.isoformat(),
            "overdue": overdue_seconds > 0,
            "overdue_seconds": overdue_seconds,
        },
        evidence_references=plan.input_references,
        warnings=(() if not overdue_seconds else ("Deadline telah terlewati.",)),
    )


def _reconciliation_case(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    result = _reconcile(plan, payload)
    output = dict(result.output_reference)
    required = output.get("matched") is not True
    output.update(
        {"case_required": required, "case_status": "PROPOSED" if required else "NOT_REQUIRED"}
    )
    warnings = result.warnings + (() if not required else ("Kasus rekonsiliasi diperlukan.",))
    return result.model_copy(update={"output_reference": output, "warnings": warnings})


def _effectiveness_review(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    baseline = _finite_decimal(payload.get("baseline_value"))
    current = _finite_decimal(payload.get("current_value"))
    target = _finite_decimal(payload.get("target_value"))
    if baseline is None or current is None or target is None:
        return _provisional(plan, "Data efektivitas CAPA belum lengkap.")
    return CapabilityHandlerOutput(
        output_reference={
            "improvement": str(current - baseline),
            "target_met": current >= target,
            "review_status": "READY",
        },
        evidence_references=plan.input_references,
    )


def _kpi_snapshot(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    metrics = payload.get("verified_metrics")
    if not isinstance(metrics, list):
        return _provisional(plan, "Snapshot KPI hanya menerima metric terverifikasi.")
    return CapabilityHandlerOutput(
        output_reference={
            "metric_count": len(metrics),
            "snapshot_digest": _payload_digest({"metrics": metrics}),
            "publishable": bool(metrics),
        },
        evidence_references=plan.input_references,
        warnings=(() if metrics else ("Tidak ada metric untuk dipublikasikan.",)),
    )


def _schedule_escalation(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    due_dates_value = payload.get("due_dates")
    if isinstance(due_dates_value, list):
        parsed = sorted(
            due
            for value in due_dates_value
            if (due := _timestamp(value)) is not None
        )
        invalid_count = len(due_dates_value) - len(parsed)
        return CapabilityHandlerOutput(
            output_reference={
                "scheduled_count": len(parsed),
                "next_escalation_at": parsed[0].isoformat() if parsed else None,
            },
            evidence_references=plan.input_references,
            warnings=(
                (f"{invalid_count} jadwal eskalasi tidak valid.",)
                if invalid_count
                else ()
            ),
            verification_status=(
                CapabilityVerificationStatus.PROVISIONAL
                if invalid_count
                else CapabilityVerificationStatus.VERIFIED
            ),
        )
    due_at = _timestamp(payload.get("due_at"))
    lead_hours = _finite_decimal(payload.get("lead_hours"))
    if due_at is None or lead_hours is None:
        return _provisional(plan, "Due date atau lead time eskalasi tidak valid.")
    return CapabilityHandlerOutput(
        output_reference={
            "due_at": due_at.isoformat(),
            "escalation_at": (due_at - timedelta(hours=float(lead_hours))).isoformat(),
            "lead_hours": str(lead_hours),
        },
        evidence_references=plan.input_references,
    )


def _schedule_reminder(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    expires_at = _timestamp(payload.get("expires_at"))
    lead_days = _finite_decimal(payload.get("lead_days"))
    if expires_at is None or lead_days is None:
        return _provisional(plan, "Tanggal kedaluwarsa atau lead days tidak valid.")
    return CapabilityHandlerOutput(
        output_reference={
            "expires_at": expires_at.isoformat(),
            "reminder_at": (expires_at - timedelta(days=float(lead_days))).isoformat(),
            "lead_days": str(lead_days),
        },
        evidence_references=plan.input_references,
    )


def _schedule_follow_up(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    base_at = _timestamp(payload.get("base_at"))
    delay_hours = _finite_decimal(payload.get("delay_hours"))
    if base_at is None or delay_hours is None:
        return _provisional(plan, "Waktu dasar atau interval follow-up tidak valid.")
    return CapabilityHandlerOutput(
        output_reference={
            "due_at": (base_at + timedelta(hours=float(delay_hours))).isoformat(),
            "status": "PROPOSED",
            "assigned_user_id": str(payload.get("assigned_user_id")),
        },
        evidence_references=plan.input_references,
    )


def _released_sop(
    plan: AgentExecutionPlan, payload: Mapping[str, object]
) -> CapabilityHandlerOutput:
    value = payload.get("released_versions")
    candidates = value if isinstance(value, list) else []
    released = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("status") == "RELEASED"
    ]
    if not released:
        return _provisional(plan, "Tidak ada versi SOP RELEASED untuk konteks ini.")
    selected = max(released, key=lambda item: str(item.get("version", "")))
    return CapabilityHandlerOutput(
        output_reference={
            "sop_id": str(selected.get("sop_id", "")),
            "version": str(selected.get("version", "")),
            "status": "RELEASED",
        },
        evidence_references=plan.input_references,
    )


def _evidence_metadata(
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
        warnings=(() if valid else ("Metadata atau scan evidence belum valid.",)),
        verification_status=(
            CapabilityVerificationStatus.VERIFIED
            if checksum_valid and scan_status == "CLEAN"
            else CapabilityVerificationStatus.PROVISIONAL
        ),
    )


_DOCUMENT_CONTENT_CAPABILITIES = frozenset(
    {
        "classify_document",
        "compare_contract_versions",
        "compare_versions",
        "extract_candidate_profile",
        "extract_contract_clauses",
        "extract_invoice_fields",
        "extract_obligations",
        "extract_permit_fields",
        "extract_structured_fields",
        "identify_clause_findings",
        "identify_defects",
        "screen_administrative_requirements",
        "summarize_document",
        "summarize_findings",
    }
)


def _ai_handler(gateway: LLMGateway) -> CapabilityHandler:
    def handle(
        plan: AgentExecutionPlan, payload: Mapping[str, object]
    ) -> CapabilityHandlerOutput:
        content = payload.get("content")
        if plan.capability in _DOCUMENT_CONTENT_CAPABILITIES and not (
            isinstance(content, str) and content.strip()
        ):
            return CapabilityHandlerOutput(
                output_reference={
                    "summary": "Konten sumber belum tersedia untuk dianalisis.",
                    "findings": [],
                    "confidence": 0.0,
                    "human_review_required": True,
                },
                evidence_references=plan.input_references,
                warnings=(
                    "Konten sumber belum dimaterialisasi; AI tidak dijalankan dan "
                    "hasil wajib ditinjau manusia.",
                ),
                verification_status=CapabilityVerificationStatus.UNVERIFIED,
                provider_metadata={
                    "llm_status": "NOT_MATERIALIZED",
                    "provider": "disabled",
                    "model": "",
                },
            )
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
        completed = result.status == LLMResultStatus.COMPLETED
        verification = (
            CapabilityVerificationStatus.PROVISIONAL
            if completed
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
            output_reference=(
                result.output
                if completed
                else {
                    "summary": "Analisis AI belum dijalankan.",
                    "findings": [],
                    "confidence": 0.0,
                    "human_review_required": True,
                }
            ),
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
    approval_policy = PaymentApprovalPolicyRegistry(capabilities.definitions_root).load()
    special = {
        "aggregate_verified_facts": _verified_fact_aggregate,
        "assess_cashflow_impact": _cashflow_impact,
        "assign_sales_pic": _sales_assignment,
        "calculate_kpi_deterministically": _kpi_calculation,
        "validate_lead_fields": _lead_validation,
        "calculate_progress_variance": _progress_variance,
        "calculate_variance": _finance_variance,
        "check_brand_requirements": _requirements_by_capability,
        "check_completeness": _completeness,
        "check_permit_requirements": _requirements_by_capability,
        "check_personnel_file_completeness": _requirements_by_capability,
        "check_separation_of_duties": _separation_of_duties,
        "check_site_evidence": _requirements_by_capability,
        "classify_attendance_exception": _attendance_exception,
        "classify_document_access": _document_access,
        "classify_exception": _risk_classification,
        "compare_target": _kpi_calculation,
        "compose_work_plan": _sop_plan,
        "create_checklist": _sop_plan,
        "create_interview_task": _interview_task,
        "deduplicate_lead": _lead_deduplication,
        "detect_duplicate_payment": _duplicate_payment,
        "identify_missing_evidence": _completeness,
        "identify_project_blocker": _project_blocker,
        "identify_tax_corrections": _invoice_rules,
        "validate_document_metadata": _document_metadata,
        "validate_evidence_metadata": _evidence_metadata,
        "check_budget_deterministically": _budget_check,
        "route_approval_deterministically": _approval_route_handler(approval_policy),
        "match_transactions_deterministically": _reconcile,
        "monitor_capa_deadline": _deadline_monitor,
        "open_reconciliation_case": _reconciliation_case,
        "prepare_effectiveness_review": _effectiveness_review,
        "publish_kpi_snapshot": _kpi_snapshot,
        "schedule_escalation": _schedule_escalation,
        "schedule_expiry_reminder": _schedule_reminder,
        "schedule_follow_up_task": _schedule_follow_up,
        "schedule_permit_reminder": _schedule_reminder,
        "select_released_sop": _released_sop,
        "validate_invoice_rules": _invoice_rules,
    }
    deterministic_ids = {
        contract.capability_id
        for contract in capabilities.load_all()
        if contract.execution_mode == CapabilityExecutionMode.DETERMINISTIC
    }
    missing = sorted(deterministic_ids - set(special))
    unused = sorted(set(special) - deterministic_ids)
    if missing or unused:
        raise ValueError(
            "Handler deterministik tidak konsisten dengan Capability Registry; "
            f"missing={missing}, unused={unused}"
        )
    ai = _ai_handler(gateway)
    for contract in capabilities.load_all():
        handler = (
            ai
            if contract.execution_mode == CapabilityExecutionMode.AI_ASSISTED
            else special[contract.capability_id]
        )
        registry.register(contract.capability_id, contract.handler_id, handler)
    return registry

"""Genesis design-time analysis for logical agents in one shared runtime."""

import re
from typing import Any

from alos.agents.contract import AgentDefinition, AgentKind, AgentStatus
from alos.agents.registry import AgentRegistry, RegistryError
from alos.genesis.analysis.models import (
    GenesisAnalyzeContractDraft,
    GenesisAnalyzeLLMMetadata,
    GenesisAnalyzeRequest,
    GenesisAnalyzeResult,
    GenesisAnalyzeWorkflowProposal,
    GenesisAnalyzeWorkflowStep,
)
from alos.genesis.models import GenesisStrategy, GenesisValidation
from alos.genesis.source import SourceRegistry, SourceUse
from alos.llm import DataClassification, LLMGateway, LLMRequest, LLMResult, LLMResultStatus
from alos.security import Principal, Role
from alos.security.authorization import require_any_role

DIVISIONS = ("FINANCE", "SALES_MARKETING", "PROPERTY", "HR", "LEGAL", "IT")


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    pattern = r"\b(" + "|".join(re.escape(word) for word in words) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


class GenesisAnalyzeService:
    """Create fail-closed logical-agent blueprints; it never changes production."""

    def __init__(
        self,
        gateway: LLMGateway,
        agent_registry: AgentRegistry,
        source_registry: SourceRegistry,
    ) -> None:
        self._gateway = gateway
        self._registry = agent_registry
        self._sources = source_registry

    def analyze(
        self,
        request: GenesisAnalyzeRequest,
        principal: Principal,
    ) -> GenesisAnalyzeResult:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
        )
        if request.source_references:
            self._sources.validate_references(request.source_references, SourceUse.ANALYZE)
        llm_result = self._gateway.generate(
            LLMRequest(
                prompt_id="genesis.analyze",
                input_data={
                    "prompt": request.prompt,
                    "division_code": request.division_code,
                    "source_references": list(request.source_references),
                    "shared_runtime": True,
                },
                classification=DataClassification.INTERNAL,
                safety_identifier=f"user_{principal.user_id}",
                max_output_tokens=3000,
            )
        )
        if llm_result.status == LLMResultStatus.COMPLETED and llm_result.output:
            return self._build_from_llm_output(llm_result.output, request, llm_result)
        return self._build_deterministic_fallback(request, llm_result)

    def _build_from_llm_output(
        self,
        output: dict[str, Any],
        request: GenesisAnalyzeRequest,
        llm_result: LLMResult,
    ) -> GenesisAnalyzeResult:
        raw = output.get("agent_contract_draft")
        raw_contract = raw if isinstance(raw, dict) else {}
        division_scope = self._division_scope(
            raw_contract.get("division_scope"), request.division_code
        )
        draft = self._draft(
            agent_id=str(raw_contract.get("agent_id") or self._agent_id(division_scope)),
            name=str(raw_contract.get("name") or "Genesis Logical Agent"),
            purpose=str(
                raw_contract.get("purpose")
                or output.get("understanding")
                or request.prompt
            ),
            division_scope=division_scope,
            owner=str(
                raw_contract.get("human_owner")
                or output.get("business_owner")
                or "Pemilik proses terkait"
            ),
            capabilities=_items(raw_contract.get("capabilities")),
            tools=_items(raw_contract.get("tools_allowed")),
            inputs=_items(raw_contract.get("inputs")),
            outputs=_items(raw_contract.get("outputs")),
            source_of_truth=_items(raw_contract.get("source_of_truth")),
            approval_boundary=_items(raw_contract.get("approval_boundary")),
            evidence_requirement=_items(raw_contract.get("evidence_requirement")),
            forbidden_actions=_items(raw_contract.get("forbidden_actions")),
            metrics=_items(raw_contract.get("kpi_metrics")),
            escalation=_items(raw_contract.get("escalation")),
            risk_level=str(raw_contract.get("risk_level") or "LOW"),
            prompt_ref=str(raw_contract.get("prompt_ref") or "genesis.validation@0.1.0"),
            model_policy_ref=str(
                raw_contract.get("model_policy_ref")
                or "openai-primary-claude-fallback@0.1.0"
            ),
            permission_policy_ref=str(
                raw_contract.get("permission_policy_ref") or "read-only-evidence@0.1.0"
            ),
        )
        workflow = self._workflow_from_output(output.get("workflow_proposal"), draft.name)
        validations = self._run_governance_validations(
            draft, request.source_references, raw_contract
        )
        return GenesisAnalyzeResult(
            understanding=str(output.get("understanding") or request.prompt),
            strategy=GenesisStrategy.CREATE,
            strategy_justification=(
                "Genesis mengusulkan logical agent baru dalam shared Agent Runtime; "
                "reuse atau extend hanya dipilih pada proposal contract berikutnya."
            ),
            runtime_scope="SHARED_AGENT_RUNTIME",
            business_owner=draft.human_owner,
            domain=draft.domain,
            agent_contract_draft=draft,
            workflow_proposal=workflow,
            risks_and_blockers=_items(output.get("risks_and_blockers")),
            unanswered_questions=_items(output.get("unanswered_questions")),
            governance_notes=(
                "Draf design-time. Genesis tidak dapat auto-approve, membuat tool, "
                "mengaktifkan agent, atau mengubah production."
            ),
            validations=validations,
            production_effect=False,
            source_references=request.source_references,
            llm_result_status=llm_result.status.value,
            llm_metadata=self._llm_metadata(llm_result),
        )

    def _build_deterministic_fallback(
        self,
        request: GenesisAnalyzeRequest,
        llm_result: LLMResult,
    ) -> GenesisAnalyzeResult:
        division, capability, tool, owner = self._profile(request)
        division_scope = self._division_scope(None, request.division_code or division)
        name = f"{division.replace('_', ' ').title()} Validation Agent"
        draft = self._draft(
            agent_id=self._agent_id(division_scope),
            name=name,
            purpose=(
                "Menganalisis requirement secara read-only, menghasilkan evidence dan "
                "rekomendasi yang harus ditinjau manusia sebelum tindakan material."
            ),
            division_scope=division_scope,
            owner=owner,
            capabilities=(capability,),
            tools=(tool,),
            inputs=("registered_source", "workspace_context"),
            outputs=("structured_result", "citation_references"),
            source_of_truth=("Registered source and version",),
            approval_boundary=("Human review is required before any material action",),
            evidence_requirement=("Every result includes registered source evidence",),
            forbidden_actions=(
                "write production data",
                "approve its own release",
                "create or modify a tool",
            ),
            metrics=("citation coverage", "test pass rate", "cost per run"),
            escalation=("Escalate unsupported or conflicting evidence to the owner",),
            risk_level="LOW",
            prompt_ref="genesis.validation@0.1.0",
            model_policy_ref="openai-primary-claude-fallback@0.1.0",
            permission_policy_ref="read-only-evidence@0.1.0",
        )
        validations = self._run_governance_validations(
            draft, request.source_references, None
        )
        return GenesisAnalyzeResult(
            understanding=f"Analisis requirement: {request.prompt}",
            strategy=GenesisStrategy.CREATE,
            strategy_justification=(
                "Requirement dirancang sebagai logical agent baru pada shared runtime, "
                "bukan aplikasi atau microservice baru."
            ),
            runtime_scope="SHARED_AGENT_RUNTIME",
            business_owner=owner,
            domain="shared-enterprise",
            agent_contract_draft=draft,
            workflow_proposal=GenesisAnalyzeWorkflowProposal(
                workflow_name=f"Genesis proposal — {name}",
                steps=(
                    GenesisAnalyzeWorkflowStep(
                        step_id="ANALYZE",
                        name="Analyze source and requirement",
                        actor="Genesis",
                        description="Analisis design-time dengan source reference terdaftar.",
                    ),
                    GenesisAnalyzeWorkflowStep(
                        step_id="REVIEW",
                        name="Human review",
                        actor="Business and Technical Reviewers",
                        description="Dua reviewer berbeda memeriksa contract dan evidence test.",
                    ),
                    GenesisAnalyzeWorkflowStep(
                        step_id="RUN",
                        name="Shared runtime execution",
                        actor="Shared Agent Runtime",
                        description="Runtime menjalankan capability yang diizinkan contract.",
                    ),
                ),
            ),
            risks_and_blockers=(
                "Capability, tool, permission, cost cap, dan source evidence harus tetap "
                "lulus validasi sebelum release proposal.",
            ),
            unanswered_questions=(
                "Siapa owner bisnis yang menyetujui hasil dan KPI agent ini?",
            ),
            governance_notes=(
                "Fallback deterministik digunakan; tidak ada LLM, approval, aktivasi, "
                "atau perubahan production yang dilakukan."
            ),
            validations=validations,
            production_effect=False,
            source_references=request.source_references,
            llm_result_status=llm_result.status.value,
            llm_metadata=self._llm_metadata(llm_result),
        )

    @staticmethod
    def _workflow_from_output(value: object, name: str) -> GenesisAnalyzeWorkflowProposal:
        raw = value if isinstance(value, dict) else {}
        raw_steps_value = raw.get("steps")
        raw_steps: list[object] = list(raw_steps_value) if isinstance(raw_steps_value, list) else []
        steps = tuple(
            GenesisAnalyzeWorkflowStep(
                step_id=str(item.get("step_id") or f"STEP_{index}"),
                name=str(item.get("name") or f"Step {index}"),
                actor=str(item.get("actor") or "Human reviewer"),
                description=str(item.get("description") or "Review required."),
            )
            for index, item in enumerate(raw_steps, 1)
            if isinstance(item, dict)
        )
        return GenesisAnalyzeWorkflowProposal(
            workflow_name=str(raw.get("workflow_name") or f"Genesis proposal — {name}"),
            steps=steps,
        )

    @staticmethod
    def _division_scope(value: object, requested: str | None) -> tuple[str, ...]:
        candidates = (
            _items(value)
            if value is not None
            else ((requested,) if requested else DIVISIONS)
        )
        normalized = tuple(
            dict.fromkeys(item.upper() for item in candidates if item.upper() in DIVISIONS)
        )
        return normalized or DIVISIONS

    @staticmethod
    def _agent_id(division_scope: tuple[str, ...]) -> str:
        scope = "ALL" if set(division_scope) == set(DIVISIONS) else "_".join(division_scope)
        return f"GENESIS_{scope}_AGENT"[:64]

    @staticmethod
    def _profile(request: GenesisAnalyzeRequest) -> tuple[str, str, str, str]:
        text = request.prompt
        if request.division_code in DIVISIONS:
            division = request.division_code
        elif _has_word(text, ("invoice", "payment", "vendor", "budget", "pajak", "finance")):
            division = "FINANCE"
        elif _has_word(text, ("sales", "lead", "prospek", "customer", "marketing")):
            division = "SALES_MARKETING"
        elif _has_word(text, ("property", "properti", "permit", "deadline", "lapangan")):
            division = "PROPERTY"
        elif _has_word(text, ("hr", "recruitment", "karyawan", "personnel")):
            division = "HR"
        elif _has_word(text, ("legal", "kontrak", "compliance", "izin")):
            division = "LEGAL"
        elif _has_word(text, ("it", "security", "evidence", "audit")):
            division = "IT"
        else:
            division = "ALL"
        profiles = {
            "FINANCE": ("validate_invoice_rules", "alos.invoice.read", "Kepala Keuangan"),
            "SALES_MARKETING": (
                "validate_lead_fields",
                "alos.lead.read",
                "Kepala Sales & Marketing",
            ),
            "PROPERTY": ("calculate_progress_variance", "alos.property.read", "Kepala Property"),
            "HR": ("check_personnel_file_completeness", "alos.hr.read", "Kepala HR"),
            "LEGAL": ("monitor_capa_deadline", "alos.legal.read", "Kepala Legal"),
            "IT": ("validate_evidence_metadata", "alos.evidence.read", "Kepala IT"),
            "ALL": ("aggregate_verified_facts", "alos.audit.read", "AI Executive Operating Layer"),
        }
        capability, tool, owner = profiles[division]
        return division, capability, tool, owner

    @staticmethod
    def _draft(
        *,
        agent_id: str,
        name: str,
        purpose: str,
        division_scope: tuple[str, ...],
        owner: str,
        capabilities: tuple[str, ...],
        tools: tuple[str, ...],
        inputs: tuple[str, ...],
        outputs: tuple[str, ...],
        source_of_truth: tuple[str, ...],
        approval_boundary: tuple[str, ...],
        evidence_requirement: tuple[str, ...],
        forbidden_actions: tuple[str, ...],
        metrics: tuple[str, ...],
        escalation: tuple[str, ...],
        risk_level: str,
        prompt_ref: str,
        model_policy_ref: str,
        permission_policy_ref: str,
    ) -> GenesisAnalyzeContractDraft:
        return GenesisAnalyzeContractDraft(
            agent_id=agent_id.upper().replace("-", "_"),
            name=name,
            purpose=purpose,
            agent_kind="LOGICAL",
            domain="shared-enterprise",
            division_scope=division_scope,
            human_owner=owner,
            triggers=("ON_DEMAND", "SOURCE_UPDATED"),
            inputs=inputs,
            outputs=outputs,
            source_of_truth=source_of_truth,
            capabilities=capabilities,
            tools_allowed=tools,
            approval_boundary=approval_boundary,
            evidence_requirement=evidence_requirement,
            forbidden_actions=forbidden_actions,
            kpi_metrics=metrics,
            escalation=escalation,
            prompt_ref=prompt_ref,
            model_policy_ref=model_policy_ref,
            permission_policy_ref=permission_policy_ref,
            risk_level=risk_level.upper(),
            status="DRAFT",
        )

    @staticmethod
    def _llm_metadata(result: LLMResult) -> GenesisAnalyzeLLMMetadata:
        return GenesisAnalyzeLLMMetadata(
            provider=result.provider.value,
            model=result.model,
            prompt_id=result.prompt_id,
            prompt_version=result.prompt_version,
            prompt_digest=result.prompt_digest,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            latency_ms=result.latency_ms,
            estimated_cost_usd=result.estimated_cost_usd,
            redacted_fields=result.redacted_fields,
            warnings=result.warnings,
        )

    def _run_governance_validations(
        self,
        draft: GenesisAnalyzeContractDraft,
        source_references: tuple[str, ...],
        raw_contract: dict[str, Any] | None,
    ) -> tuple[GenesisValidation, ...]:
        validations = [
            GenesisValidation(
                code="ORGANIZATION_LOCK",
                passed=True,
                message="Proposal tidak dapat mengubah struktur organisasi perusahaan.",
            ),
            GenesisValidation(
                code="SHARED_RUNTIME_ONLY",
                passed=draft.agent_kind == "LOGICAL" and draft.domain == "shared-enterprise",
                message="Agent adalah logical agent pada shared runtime, bukan service baru.",
            ),
            GenesisValidation(
                code="SOURCE_CITATION_REQUIRED",
                passed=bool(source_references),
                message=(
                    "Source reference tersedia untuk citation."
                    if source_references
                    else "Tambahkan source reference sebelum proposal dapat masuk pipeline."
                ),
            ),
            GenesisValidation(
                code="HUMAN_AUTHORITY_BOUNDARY",
                passed=bool(draft.approval_boundary) and bool(draft.forbidden_actions),
                message="Approval boundary dan forbidden actions harus eksplisit.",
            ),
        ]
        required_fields = {
            "agent_id", "name", "purpose", "division_scope", "human_owner", "capabilities",
            "tools_allowed", "approval_boundary", "evidence_requirement", "forbidden_actions",
            "kpi_metrics", "prompt_ref", "model_policy_ref", "permission_policy_ref", "risk_level",
        }
        missing = sorted(required_fields - set(raw_contract)) if raw_contract is not None else []
        contract_valid = False
        message = "Agent Contract belum tervalidasi."
        if not missing and draft.status == "DRAFT":
            try:
                self._registry.validate_candidate(self._to_agent_definition(draft))
                contract_valid = True
                message = "Logical Agent Contract lengkap dan kompatibel dengan registry."
            except (RegistryError, ValueError) as exc:
                message = f"Agent Contract tidak valid: {exc}"
        elif missing:
            message = "Output analisis belum memuat field wajib: " + ", ".join(missing)
        validations.extend(
            (
                GenesisValidation(
                    code="AGENT_CONTRACT_VALID", passed=contract_valid, message=message
                ),
                GenesisValidation(
                    code="DESIGN_TIME_ONLY",
                    passed=True,
                    message="Genesis hanya menghasilkan DRAFT tanpa efek production.",
                ),
            )
        )
        return tuple(validations)

    @staticmethod
    def _to_agent_definition(draft: GenesisAnalyzeContractDraft) -> AgentDefinition:
        return AgentDefinition(
            contract_version=draft.contract_version,
            agent_id=draft.agent_id,
            name=draft.name,
            agent_kind=AgentKind.LOGICAL,
            domain=draft.domain,
            division_scope=draft.division_scope,
            purpose=draft.purpose,
            human_owner=draft.human_owner,
            triggers=draft.triggers,
            inputs=draft.inputs,
            source_of_truth=draft.source_of_truth,
            capabilities=draft.capabilities,
            outputs=draft.outputs,
            tools_allowed=draft.tools_allowed,
            approval_boundary=draft.approval_boundary,
            evidence_requirement=draft.evidence_requirement,
            forbidden_actions=draft.forbidden_actions,
            metrics=draft.kpi_metrics,
            escalation=draft.escalation,
            prompt_ref=draft.prompt_ref,
            model_policy_ref=draft.model_policy_ref,
            permission_policy_ref=draft.permission_policy_ref,
            risk_level=draft.risk_level,
            input_schema=draft.input_schema,
            output_schema=draft.output_schema,
            version=draft.version,
            status=AgentStatus.DRAFT,
        )

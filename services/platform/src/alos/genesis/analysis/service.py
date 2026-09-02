import re
from typing import Any

from alos.agents.contract import AgentDefinition, AgentKind, AgentReference, AgentStatus
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


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


class GenesisAnalyzeService:
    """Analyze natural language workforce requirements into structured, fail-closed proposals."""

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

        llm_request = LLMRequest(
            prompt_id="genesis.analyze",
            input_data={
                "prompt": request.prompt,
                "division_code": request.division_code,
                "source_references": list(request.source_references),
            },
            classification=DataClassification.INTERNAL,
            safety_identifier=f"user_{principal.user_id}",
            max_output_tokens=3000,
        )
        llm_result = self._gateway.generate(llm_request)

        if llm_result.status == LLMResultStatus.COMPLETED and llm_result.output:
            return self._build_from_llm_output(
                llm_result.output,
                request.source_references,
                llm_result,
            )

        return self._build_deterministic_fallback(
            request,
            llm_result,
        )

    def _build_from_llm_output(
        self,
        output: dict[str, Any],
        source_references: tuple[str, ...],
        llm_result: LLMResult,
    ) -> GenesisAnalyzeResult:
        strategy_str = str(output.get("strategy", "EXTEND")).upper()
        strategy = (
            GenesisStrategy(strategy_str)
            if strategy_str in GenesisStrategy.__members__
            else GenesisStrategy.EXTEND
        )

        parent_core = str(output.get("parent_core_agent_id") or "UNRESOLVED").upper().strip()

        raw_contract = output.get("agent_contract_draft") or {}
        if not isinstance(raw_contract, dict):
            raw_contract = {}
        extends_val = raw_contract.get("extends") or (
            parent_core if strategy == GenesisStrategy.EXTEND else None
        )
        contract_draft = GenesisAnalyzeContractDraft(
            agent_id=str(raw_contract.get("agent_id") or f"SUB_{parent_core}_CUSTOM"),
            name=str(raw_contract.get("name") or "Custom Digital Workforce Agent"),
            purpose=str(raw_contract.get("purpose") or output.get("understanding", "")),
            agent_kind=str(raw_contract.get("agent_kind") or "SUB_AGENT"),
            parent_agent_id=parent_core,
            domain=str(raw_contract.get("domain") or output.get("domain") or "operations")
            .strip()
            .lower(),
            parent_agent_version=(
                str(raw_contract.get("parent_agent_version"))
                if raw_contract.get("parent_agent_version")
                else self._latest_core_version(parent_core)
            ),
            extends=extends_val,
            contract_version=str(raw_contract.get("contract_version") or "1.0.0"),
            human_owner=str(raw_contract.get("human_owner") or output.get("business_owner") or ""),
            triggers=tuple(str(item) for item in raw_contract.get("triggers", [])),
            inputs=tuple(str(item) for item in raw_contract.get("inputs", [])),
            outputs=tuple(str(item) for item in raw_contract.get("outputs", [])),
            source_of_truth=tuple(str(item) for item in raw_contract.get("source_of_truth", [])),
            capabilities=tuple(str(item) for item in raw_contract.get("capabilities", [])),
            tools_allowed=tuple(str(item) for item in raw_contract.get("tools_allowed", [])),
            approval_boundary=tuple(
                str(item) for item in raw_contract.get("approval_boundary", [])
            ),
            evidence_requirement=tuple(
                str(item) for item in raw_contract.get("evidence_requirement", [])
            ),
            forbidden_actions=tuple(
                str(item) for item in raw_contract.get("forbidden_actions", [])
            ),
            kpi_metrics=tuple(str(item) for item in raw_contract.get("kpi_metrics", [])),
            escalation=tuple(str(item) for item in raw_contract.get("escalation", [])),
            version=str(raw_contract.get("version") or "0.1.0"),
            status=str(raw_contract.get("status") or "DRAFT").upper(),
        )

        raw_workflow = output.get("workflow_proposal") or {}
        raw_steps = raw_workflow.get("steps") or []
        steps = tuple(
            GenesisAnalyzeWorkflowStep(
                step_id=str(s.get("step_id") or f"STEP-{idx + 1}"),
                name=str(s.get("name") or f"Langkah {idx + 1}"),
                actor=str(s.get("actor") or "Human / Agent"),
                description=str(s.get("description") or ""),
            )
            for idx, s in enumerate(raw_steps)
        )
        workflow_proposal = GenesisAnalyzeWorkflowProposal(
            workflow_name=str(raw_workflow.get("workflow_name") or "Alur Kerja Digital Workforce"),
            steps=steps,
        )

        required_contract_fields = {
            "agent_id",
            "name",
            "purpose",
            "agent_kind",
            "parent_agent_id",
            "parent_agent_version",
            "contract_version",
            "human_owner",
            "triggers",
            "domain",
            "inputs",
            "outputs",
            "source_of_truth",
            "capabilities",
            "tools_allowed",
            "approval_boundary",
            "evidence_requirement",
            "forbidden_actions",
            "kpi_metrics",
            "escalation",
            "version",
            "status",
        }
        missing_contract_fields = tuple(
            sorted(field for field in required_contract_fields if field not in raw_contract)
        )
        validations = self._run_governance_validations(
            contract_draft,
            strategy,
            parent_core,
            missing_contract_fields=missing_contract_fields,
        )

        return GenesisAnalyzeResult(
            understanding=str(output.get("understanding") or ""),
            strategy=strategy,
            strategy_justification=str(output.get("strategy_justification") or ""),
            parent_core_agent_id=parent_core,
            business_owner=str(output.get("business_owner") or "Divisi Terkait"),
            domain=str(output.get("domain") or "OPERATIONS"),
            agent_contract_draft=contract_draft,
            workflow_proposal=workflow_proposal,
            risks_and_blockers=tuple(str(r) for r in output.get("risks_and_blockers", [])),
            unanswered_questions=tuple(str(q) for q in output.get("unanswered_questions", [])),
            governance_notes=str(
                output.get("governance_notes")
                or "Draf hasil analisis Genesis. production_effect=false."
            ),
            validations=validations,
            production_effect=False,
            source_references=source_references,
            llm_result_status=llm_result.status.value,
            llm_metadata=self._llm_metadata(llm_result),
        )

    def _build_deterministic_fallback(
        self,
        request: GenesisAnalyzeRequest,
        llm_result: LLMResult,
    ) -> GenesisAnalyzeResult:
        prompt_text = request.prompt

        inputs: tuple[str, ...]
        outputs: tuple[str, ...]
        capabilities: tuple[str, ...]
        tools_allowed: tuple[str, ...]
        approval_boundary: tuple[str, ...]
        forbidden_actions: tuple[str, ...]
        steps: tuple[GenesisAnalyzeWorkflowStep, ...]

        # Keyword mapping for fallback analysis
        if _has_word(
            prompt_text,
            ("lead", "sales", "crm", "customer", "prospek", "pembeli", "follow up", "follow-up"),
        ):
            parent_core = "SLA"
            domain = "SALES"
            business_owner = "Kepala Sales & Marketing"
            strategy = GenesisStrategy.EXTEND
            strategy_justification = (
                "Kebutuhan terkait kualifikasi dan follow-up prospek memperluas fungsi SLA dan CFA."
            )
            agent_id = "SUB_SLA_QUALIFICATION_ASSISTANT"
            name = "Sales Lead Qualification Assistant"
            purpose = (
                "Membantu tim Sales mengkualifikasi lead masuk dan menyusun rekomendasi"
                " follow-up terstruktur."
            )
            inputs = ("lead_contact_info", "interaction_notes", "project_catalog")
            outputs = ("lead_score", "qualification_tier", "recommended_follow_up")
            capabilities = ("classify_lead", "recommend_follow_up", "schedule_follow_up_task")
            tools_allowed = ("alos.lead.read", "alos.crm.read", "alos.work_item.create")
            approval_boundary = (
                "Tidak boleh memberikan diskon di luar wewenang",
                "Reservasi unit wajib konfirmasi Sales Manager",
            )
            forbidden_actions = (
                "Mengubah harga unit resmi",
                "Menjanjikan ketersediaan unit tanpa verifikasi sistem",
            )
            steps = (
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-1",
                    name="Intake Lead",
                    actor="SLA",
                    description="Penerimaan dan deduplikasi kontak prospek",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-2",
                    name="Kualifikasi Prospek",
                    actor="SUB_SLA_QUALIFICATION_ASSISTANT",
                    description="Skoring minat dan daya beli prospek",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-3",
                    name="Follow-Up Sales",
                    actor="Sales PIC",
                    description="Interaksi langsung dan presentasi unit",
                ),
            )
        elif _has_word(
            prompt_text,
            ("invoice", "pembayaran", "vendor", "tagihan", "pajak", "anggaran", "kas", "rab"),
        ):
            parent_core = "FRA"
            domain = "FINANCE"
            business_owner = "Kepala Keuangan"
            strategy = GenesisStrategy.EXTEND
            strategy_justification = (
                "Kebutuhan terkait verifikasi invoice dan pengajuan pembayaran vendor memperluas"
                " fungsi FRA (Finance Reconciliation Agent) dan BCA."
            )
            agent_id = "SUB_FRA_VENDOR_INVOICE_CHECK"
            name = "Vendor Payment & Invoice Verifier"
            purpose = (
                "Membantu Keuangan memverifikasi kelengkapan invoice, kesesuaian anggaran, dan"
                " evidence pekerjaan vendor tanpa melakukan approval atau pembayaran mandiri."
            )
            inputs = (
                "invoice_document",
                "work_evidence",
                "rab_budget_line",
                "vendor_tax_data",
            )
            outputs = (
                "invoice_verification_result",
                "budget_match_status",
                "tax_compliance_notes",
            )
            capabilities = (
                "extract_invoice_fields",
                "check_budget_deterministically",
                "validate_invoice_rules",
            )
            tools_allowed = (
                "alos.invoice.read",
                "alos.budget.read",
                "alos.tax_rule.read",
            )
            approval_boundary = (
                "Tidak boleh menyetujui payment request secara mandiri",
                "Approval wajib dilakukan Finance Human",
            )
            forbidden_actions = (
                "Melakukan transfer dana atau eksekusi bank",
                "Mengubah nominal anggaran RAB",
                "Menyetujui approval step secara mandiri",
            )
            steps = (
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-1",
                    name="Intake Dokumen",
                    actor="Pemohon / DIA",
                    description="Unggah invoice dan bukti pekerjaan",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-2",
                    name="Pemeriksaan Anggaran & Pajak",
                    actor="SUB_FRA_VENDOR_INVOICE_CHECK",
                    description="Verifikasi invoice terhadap RAB dan validasi pajak",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-3",
                    name="Approval Pembayaran",
                    actor="Finance Human (ARA)",
                    description="Review dan persetujuan pejabat berwenang",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-4",
                    name="Eksekusi & Rekonsiliasi",
                    actor="Finance Human & FRA",
                    description="Pembayaran perbankan dan rekonsiliasi akhir",
                ),
            )
        elif _has_word(
            prompt_text,
            (
                "progres",
                "lapangan",
                "opname",
                "konstruksi",
                "defect",
                "inspeksi",
                "properti",
                "property",
            ),
        ):
            parent_core = "TPA"
            domain = "PROPERTY"
            business_owner = "Kepala Property"
            strategy = GenesisStrategy.EXTEND
            strategy_justification = (
                "Kebutuhan inspeksi progres lapangan memperluas fungsi TPA"
                " (Technical Progress Agent)."
            )
            agent_id = "SUB_TPA_SITE_INSPECTION_CHECK"
            name = "Site Progress & Inspection Assistant"
            purpose = (
                "Membantu tim Property memverifikasi foto dan evidence fisik progres pekerjaan"
                " kontraktor."
            )
            inputs = (
                "site_photo_evidence",
                "contractor_progress_claim",
                "spk_milestone",
            )
            outputs = ("verified_physical_progress", "deviation_notes", "defect_list")
            capabilities = (
                "check_site_evidence",
                "calculate_progress_variance",
                "identify_defects",
            )
            tools_allowed = ("alos.evidence.read", "alos.property.read")
            approval_boundary = (
                "Opname resmi wajib diverifikasi Site Engineer manusia",
                "Pembayaran progres bergantung pada persetujuan Property Head",
            )
            forbidden_actions = (
                "Mengesahkan BAST tanpa verifikasi fisik Site Engineer",
                "Menyetujui klaim progres kontraktor secara otonom",
            )
            steps = (
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-1",
                    name="Unggah Evidence Progres",
                    actor="Kontraktor / CEA",
                    description="Pengunggahan bukti foto dan laporan fisik",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-2",
                    name="Evaluasi Progres Fisik",
                    actor="SUB_TPA_SITE_INSPECTION_CHECK",
                    description="Analisis kesesuaian fisik terhadap milestone SPK",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-3",
                    name="Verifikasi Opname",
                    actor="Property Human",
                    description="Pemeriksaan langsung dan persetujuan opname lapangan",
                ),
            )
        else:
            parent_core = "DIA"
            domain = (
                "EXECUTIVE"
                if _has_word(prompt_text, ("direktur", "direksi", "eksekutif", "brief"))
                else "OPERATIONS"
            )
            business_owner = "Divisi Terkait"
            strategy = GenesisStrategy.CREATE
            strategy_justification = (
                "Kebutuhan umum dianalisis sebagai proposal kapabilitas baru dengan"
                " basis Document Intelligence Agent (DIA)."
            )
            agent_id = f"SUB_{parent_core}_ASSISTANT"
            name = "Digital Workforce Task Assistant"
            purpose = f"Membantu operasi terkait: {request.prompt[:120]}..."
            inputs = ("input_document", "context_parameters")
            outputs = ("analysis_summary", "structured_findings")
            capabilities = ("classify_document", "summarize_document")
            tools_allowed = ("alos.document.read", "ai.document.analyze")
            approval_boundary = ("Keputusan akhir tetap berada di tangan PIC manusia",)
            forbidden_actions = ("Mengubah data master atau produksi secara sepihak",)
            steps = (
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-1",
                    name="Pengumpulan Data",
                    actor="Pemohon / DIA",
                    description="Pengumpulan berkas dan konteks kasus",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-2",
                    name="Pemrosesan Draf",
                    actor=agent_id,
                    description="Ekstraksi dan penyusunan rekomendasi terstruktur",
                ),
                GenesisAnalyzeWorkflowStep(
                    step_id="STEP-3",
                    name="Review Manusia",
                    actor="Human PIC",
                    description="Verifikasi dan keputusan resmi",
                ),
            )

        contract_draft = GenesisAnalyzeContractDraft(
            agent_id=agent_id,
            name=name,
            purpose=purpose,
            agent_kind="SUB_AGENT",
            parent_agent_id=parent_core,
            domain=domain.lower(),
            parent_agent_version=self._latest_core_version(parent_core),
            contract_version="1.0.0",
            human_owner=business_owner,
            triggers=("Permintaan pengguna berwenang", "Data terkait berubah"),
            extends=parent_core if strategy == GenesisStrategy.EXTEND else None,
            inputs=inputs,
            outputs=outputs,
            source_of_truth=("Database ALOS", "Dokumen Terverifikasi"),
            capabilities=capabilities,
            tools_allowed=tools_allowed,
            approval_boundary=approval_boundary,
            evidence_requirement=("Dokumen pendukung valid", "Metadata lengkap"),
            forbidden_actions=forbidden_actions,
            kpi_metrics=("Tingkat kepatuhan validasi", "Latensi pemeriksaan"),
            escalation=(
                "Eskalasi ke pemilik proses manusia",
                "Eskalasi ke AI Executive bila lintas divisi",
            ),
            version="0.1.0",
            status="DRAFT",
        )
        workflow_proposal = GenesisAnalyzeWorkflowProposal(
            workflow_name=f"Workflow Usulan - {name}",
            steps=steps,
        )
        validations = self._run_governance_validations(contract_draft, strategy, parent_core)

        return GenesisAnalyzeResult(
            understanding=f"Analisis kebutuhan: {request.prompt}",
            strategy=strategy,
            strategy_justification=strategy_justification,
            parent_core_agent_id=parent_core,
            business_owner=business_owner,
            domain=domain,
            agent_contract_draft=contract_draft,
            workflow_proposal=workflow_proposal,
            risks_and_blockers=(
                "Aturan SLA dan ambang batas approval spesifik harus dikonfirmasi pemilik bisnis"
                " sebelum rilis.",
            ),
            unanswered_questions=(
                "Apakah ada batasan nominal spesifik yang memerlukan eskalasi ke Direktur Utama?",
                "Format dokumen apa saja yang diterima sebagai bukti sah?",
            ),
            governance_notes=(
                "Draf dihasilkan secara fail-closed pada design-time. production_effect=false."
            ),
            validations=validations,
            production_effect=False,
            source_references=request.source_references,
            llm_result_status=llm_result.status.value,
            llm_metadata=self._llm_metadata(llm_result),
        )

    def _latest_core_version(self, agent_id: str) -> str | None:
        try:
            agent = self._registry.get(agent_id)
        except (KeyError, RegistryError):
            return None
        return agent.version if agent.agent_kind == AgentKind.CORE else None

    def _to_agent_definition(
        self,
        draft: GenesisAnalyzeContractDraft,
        parent_core: str,
    ) -> AgentDefinition:
        kind = AgentKind(draft.agent_kind.upper())
        parent: AgentDefinition | None = None
        if kind != AgentKind.CORE:
            parent = self._registry.get(parent_core)
            if parent.agent_kind != AgentKind.CORE:
                raise RegistryError(f"Parent {parent_core} bukan Core Agent")
        parent_version = (draft.parent_agent_version or parent.version) if parent else None
        extends = None
        if draft.extends:
            extends_agent = self._registry.get(draft.extends)
            extends = AgentReference(
                agent_id=extends_agent.agent_id,
                version=extends_agent.version,
            )
        return AgentDefinition(
            contract_version=draft.contract_version,
            agent_id=draft.agent_id,
            name=draft.name,
            agent_kind=kind,
            parent_agent_id=None if parent is None else parent.agent_id,
            parent_agent_version=None if kind == AgentKind.CORE else parent_version,
            extends=extends,
            domain=draft.domain,
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
            version=draft.version,
            status=AgentStatus.DRAFT,
        )

    def _llm_metadata(self, result: LLMResult) -> GenesisAnalyzeLLMMetadata:
        return GenesisAnalyzeLLMMetadata(
            provider=result.provider.value,
            model=result.model,
            prompt_id=result.prompt_id,
            prompt_version=result.prompt_version,
            prompt_digest=result.prompt_digest,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            latency_ms=result.latency_ms,
            redacted_fields=result.redacted_fields,
            warnings=result.warnings,
        )

    def _run_governance_validations(
        self,
        draft: GenesisAnalyzeContractDraft,
        strategy: GenesisStrategy,
        parent_core: str,
        *,
        missing_contract_fields: tuple[str, ...] = (),
    ) -> tuple[GenesisValidation, ...]:
        validations: list[GenesisValidation] = []
        try:
            core_ids = {agent.agent_id for agent in self._registry.load_top_level()}
        except RegistryError:
            core_ids = set()

        validations.append(
            GenesisValidation(
                code="ORGANIZATION_LOCK",
                passed=True,
                message=(
                    "Proposal tidak mengubah struktur organisasi; agent top-level maupun"
                    " turunan tetap wajib melewati governance gate."
                ),
            )
        )

        is_top_level = draft.agent_kind.upper() == "CORE"
        parent_valid = is_top_level or parent_core in core_ids
        validations.append(
            GenesisValidation(
                code="VALID_PARENT_CORE",
                passed=parent_valid,
                message=(
                    "Agent top-level tidak memerlukan parent."
                    if is_top_level
                    else f"Parent Core Agent {parent_core} terdaftar dalam Agent Registry."
                    if parent_valid
                    else f"Parent Core Agent {parent_core} tidak ditemukan pada Agent Registry."
                ),
            )
        )

        has_boundaries = bool(draft.approval_boundary) and bool(draft.forbidden_actions)
        validations.append(
            GenesisValidation(
                code="HUMAN_AUTHORITY_BOUNDARY",
                passed=has_boundaries,
                message=(
                    "Batas kewenangan manusia dan larangan tindakan material "
                    "ditetapkan secara eksplisit."
                    if has_boundaries
                    else "Approval boundary dan forbidden actions wajib diisi."
                ),
            )
        )

        contract_valid = False
        contract_error = "Agent Contract belum tervalidasi terhadap schema dan registry."
        if (
            not missing_contract_fields
            and parent_valid
            and draft.status.upper() == "DRAFT"
        ):
            try:
                candidate = self._to_agent_definition(draft, parent_core)
                self._registry.validate_candidate(candidate)
                contract_valid = True
                contract_error = "Agent Contract lengkap dan seluruh referensi terdaftar."
            except (KeyError, RegistryError, ValueError) as exc:
                contract_error = f"Agent Contract tidak valid: {exc}"
        elif missing_contract_fields:
            contract_error = (
                "Output analisis belum memuat field Agent Contract wajib: "
                + ", ".join(missing_contract_fields)
            )

        validations.append(
            GenesisValidation(
                code="AGENT_CONTRACT_VALID",
                passed=contract_valid,
                message=contract_error,
            )
        )

        validations.append(
            GenesisValidation(
                code="DESIGN_TIME_ONLY",
                passed=True,
                message=(
                    "Draf berstatus design-time tanpa efek perubahan langsung ke production"
                    " (production_effect=false)."
                ),
            )
        )
        return tuple(validations)

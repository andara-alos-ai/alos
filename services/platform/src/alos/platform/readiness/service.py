from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from alos.agents.registry import AgentRegistry
from alos.config import Settings
from alos.platform.readiness.models import (
    PilotReadinessCheck,
    PilotReadinessProfile,
    PilotReadinessReport,
    ReadinessCheckStatus,
    ReadinessOverallStatus,
)
from alos.platform.readiness.repository import ActiveRole, PostgresPilotReadinessRepository
from alos.uat.catalog import load_uat_catalog
from alos.workflow.registry import WorkflowRegistry


def load_pilot_readiness_profile(definitions_root: Path) -> PilotReadinessProfile:
    path = definitions_root / "pilot" / "controlled-pilot" / "profile.json"
    if not path.is_file():
        raise ValueError(f"Profil controlled pilot tidak ditemukan: {path}")
    return PilotReadinessProfile.model_validate_json(path.read_text(encoding="utf-8"))


class PilotReadinessService:
    def __init__(
        self,
        repository: PostgresPilotReadinessRepository,
        settings: Settings,
        agents: AgentRegistry,
        workflows: WorkflowRegistry,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._agents = agents
        self._workflows = workflows
        self._profile = load_pilot_readiness_profile(settings.definitions_root)
        self._uat_catalog = load_uat_catalog(settings.definitions_root)

    def evaluate(self, organization_id: UUID, project_id: UUID) -> PilotReadinessReport:
        now = datetime.now(UTC)
        facts = self._repository.collect(organization_id, project_id)
        checks: list[PilotReadinessCheck] = []
        checks.append(
            self._count_check(
                "PILOT-PROJECT-ACTIVE",
                "CONFIGURATION",
                "Proyek pilot aktif",
                int(facts.project_status == "ACTIVE"),
                1,
                "Proyek ditemukan dengan status ACTIVE.",
                "Aktifkan atau pilih proyek pilot yang berada pada organisasi pengguna.",
            )
        )
        missing_divisions = sorted(self._profile.required_divisions - facts.division_codes)
        checks.append(
            self._count_check(
                "PILOT-DIVISION-STRUCTURE",
                "CONFIGURATION",
                "Enam divisi tersedia",
                len(self._profile.required_divisions & facts.division_codes),
                len(self._profile.required_divisions),
                "Struktur divisi ALOS tersedia.",
                f"Provision divisi yang belum tersedia: {', '.join(missing_divisions)}.",
            )
        )
        checks.extend(self._role_checks(facts.active_roles))
        checks.append(
            self._count_check(
                "PILOT-AGENT-REGISTRY",
                "RUNTIME",
                "18 Core Agent tervalidasi",
                len(self._agents.load_core()),
                self._profile.expected_core_agents,
                "Shared Agent Runtime memiliki 18 Core Agent.",
                "Perbaiki Agent Contract atau registry sebelum membuka pilot.",
            )
        )
        checks.append(
            self._count_check(
                "PILOT-WORKFLOW-REGISTRY",
                "RUNTIME",
                "Enam workflow utama tervalidasi",
                len(self._workflows.load_all()),
                self._profile.expected_workflows,
                "Enam workflow utama tersedia pada registry.",
                "Lengkapi atau validasi Workflow Contract yang belum tersedia.",
            )
        )
        checks.append(
            self._count_check(
                "PILOT-DOCUMENT-EVIDENCE",
                "DATA",
                "Dokumen pilot aman tersedia",
                facts.document_count,
                self._profile.minimum_safe_documents,
                "Minimal satu dokumen non-rejected tersedia pada proyek.",
                "Unggah dokumen sintetis atau tersanitasi sebelum menjalankan UAT.",
            )
        )
        checks.append(
            self._count_check(
                "PILOT-DEAD-LETTER",
                "OBSERVABILITY",
                "Tidak ada dead-letter event",
                int(facts.dead_letter_count == 0),
                1,
                "Antrean integrasi tidak memiliki dead-letter event.",
                "Periksa, perbaiki penyebab, lalu requeue atau tutup dead-letter event.",
            )
        )
        recent_worker = (
            facts.last_worker_status in {"COMPLETED", "PARTIAL"}
            and facts.last_worker_completed_at is not None
            and facts.last_worker_completed_at
            >= now - timedelta(minutes=self._profile.worker_max_age_minutes)
        )
        checks.append(
            self._count_check(
                "PILOT-WORKER-HEARTBEAT",
                "OBSERVABILITY",
                "Worker operasional memiliki heartbeat baru",
                int(recent_worker),
                1,
                (
                    "Worker selesai dalam "
                    f"{self._profile.worker_max_age_minutes} menit terakhir."
                ),
                "Jalankan worker ALOS dan pastikan siklusnya COMPLETED atau PARTIAL.",
            )
        )
        checks.extend(self._environment_checks(facts.recovery_evidence_count))
        return self._report(organization_id, project_id, now, checks)

    def evaluate_go_live(
        self, organization_id: UUID, project_id: UUID
    ) -> PilotReadinessReport:
        now = datetime.now(UTC)
        facts = self._repository.collect(organization_id, project_id)
        base = self.evaluate(organization_id, project_id)
        checks = list(base.checks)
        checks.append(
            self._count_check(
                "PILOT-UAT-SCENARIOS",
                "UAT",
                "Seluruh skenario UAT lulus",
                facts.latest_uat_scenario_count,
                len(self._uat_catalog.scenarios),
                "Seluruh skenario UAT memiliki hasil dan evidence.",
                "Selesaikan skenario UAT yang belum PASSED atau PASSED_WITH_RISK.",
            )
        )
        checks.append(
            self._count_check(
                "PILOT-UAT-SIGNOFFS",
                "UAT",
                "Seluruh sign-off manusia tersedia",
                facts.latest_uat_signoff_count,
                len(self._uat_catalog.required_signoff_scopes),
                "Business owner, IT, AI Executive, dan Direktur telah memberi sign-off.",
                "Lengkapi sign-off manusia yang masih kosong pada siklus UAT terbaru.",
            )
        )
        checks.append(self._uat_acceptance_check(facts.latest_uat_status))
        return self._report(organization_id, project_id, now, checks)

    def _report(
        self,
        organization_id: UUID,
        project_id: UUID,
        now: datetime,
        checks: list[PilotReadinessCheck],
    ) -> PilotReadinessReport:
        passed = sum(check.status == ReadinessCheckStatus.PASS for check in checks)
        warnings = sum(check.status == ReadinessCheckStatus.WARNING for check in checks)
        blocked = sum(check.status == ReadinessCheckStatus.BLOCKED for check in checks)
        overall = (
            ReadinessOverallStatus.BLOCKED
            if blocked
            else ReadinessOverallStatus.ATTENTION
            if warnings
            else ReadinessOverallStatus.READY
        )
        return PilotReadinessReport(
            organization_id=organization_id,
            project_id=project_id,
            environment=self._settings.environment,
            evaluated_at=now,
            overall_status=overall,
            passed_checks=passed,
            warning_checks=warnings,
            blocked_checks=blocked,
            checks=tuple(checks),
        )

    @staticmethod
    def _uat_acceptance_check(status: str | None) -> PilotReadinessCheck:
        if status == "ACCEPTED":
            return PilotReadinessCheck(
                check_id="PILOT-UAT-ACCEPTANCE",
                category="UAT",
                title="Siklus UAT diterima",
                status=ReadinessCheckStatus.PASS,
                required=True,
                detail="Siklus UAT terbaru diterima tanpa risk terbuka.",
            )
        if status == "ACCEPTED_WITH_RISK":
            return PilotReadinessCheck(
                check_id="PILOT-UAT-ACCEPTANCE",
                category="UAT",
                title="Siklus UAT diterima dengan risk",
                status=ReadinessCheckStatus.WARNING,
                required=True,
                detail="Siklus UAT diterima dengan risk LOW atau MEDIUM yang terdokumentasi.",
                remediation="Pastikan owner, due date, dan mitigasi risk dipantau sebelum go-live.",
            )
        return PilotReadinessCheck(
            check_id="PILOT-UAT-ACCEPTANCE",
            category="UAT",
            title="Siklus UAT diterima",
            status=ReadinessCheckStatus.BLOCKED,
            required=True,
            detail=f"Status siklus UAT terbaru: {status or 'BELUM ADA'}.",
            remediation="Selesaikan UAT dan seluruh sign-off manusia sebelum go-live.",
        )

    def _role_checks(self, roles: tuple[ActiveRole, ...]) -> list[PilotReadinessCheck]:
        return [
            self._role_check(
                roles,
                requirement.check_id,
                requirement.title,
                requirement.role_code,
                requirement.division_code,
                requirement.minimum_active_users,
                project_required=requirement.project_assignment_required,
                division_head_allowed=requirement.division_head_allowed,
            )
            for requirement in self._profile.role_requirements
        ]

    def _role_check(
        self,
        roles: tuple[ActiveRole, ...],
        check_id: str,
        title: str,
        role_code: str,
        division_code: str | None,
        target: int,
        *,
        project_required: bool = False,
        division_head_allowed: bool = False,
    ) -> PilotReadinessCheck:
        users = {
            role.user_id
            for role in roles
            if (
                role.role_code == role_code
                or (division_head_allowed and role.role_code == "DIVISION_HEAD")
            )
            and (division_code is None or role.division_code == division_code)
            and (not project_required or role.project_assigned)
        }
        return self._count_check(
            check_id,
            "ACCESS",
            title,
            len(users),
            target,
            "Pengguna aktif dan project assignment memenuhi kebutuhan workflow.",
            "Aktifkan pengguna berbeda, role/divisi yang benar, dan project assignment aktif.",
        )

    def _environment_checks(self, recovery_evidence_count: int) -> list[PilotReadinessCheck]:
        oidc_ready = self._settings.oidc_provider == "google"
        oidc_required = self._settings.environment in {"staging", "production"}
        storage_ready = self._settings.object_storage_provider == "s3"
        scan_ready = self._settings.document_scan_mode == "external"
        return [
            self._optional_check(
                "PILOT-OIDC",
                "SECURITY",
                "Google OIDC dikonfigurasi",
                oidc_ready,
                oidc_required,
                "Login federasi Google siap digunakan.",
                "Konfigurasikan Google OIDC dan nonaktifkan login pilot lokal pada staging.",
            ),
            self._optional_check(
                "PILOT-OBJECT-STORAGE",
                "SECURITY",
                "Object storage terkelola",
                storage_ready,
                self._settings.environment == "production",
                "Dokumen menggunakan object storage S3-compatible.",
                "Gunakan object storage S3-compatible sebelum production.",
            ),
            self._optional_check(
                "PILOT-MALWARE-SCAN",
                "SECURITY",
                "Pemeriksaan malware dokumen",
                scan_ready,
                self._settings.environment == "production",
                "Scanner dokumen eksternal aktif.",
                "Aktifkan scanner dokumen sebelum production atau penggunaan data asli.",
            ),
            self._optional_check(
                "PILOT-RECOVERY-DRILL",
                "RECOVERY",
                "Backup dan restore telah diuji",
                recovery_evidence_count > 0,
                False,
                "Hasil uji recovery telah dicatat sebagai evidence UAT-07.",
                "Jalankan runbook backup/restore staging dan lampirkan hasilnya pada UAT-07.",
            ),
        ]

    @staticmethod
    def _count_check(
        check_id: str,
        category: str,
        title: str,
        actual: int,
        target: int,
        passed_detail: str,
        remediation: str,
    ) -> PilotReadinessCheck:
        passed = actual >= target
        return PilotReadinessCheck(
            check_id=check_id,
            category=category,
            title=title,
            status=ReadinessCheckStatus.PASS if passed else ReadinessCheckStatus.BLOCKED,
            required=True,
            detail=passed_detail if passed else f"Terpenuhi {actual} dari target {target}.",
            remediation=None if passed else remediation,
            actual_count=actual,
            target_count=target,
        )

    @staticmethod
    def _optional_check(
        check_id: str,
        category: str,
        title: str,
        passed: bool,
        required: bool,
        passed_detail: str,
        remediation: str,
    ) -> PilotReadinessCheck:
        status = (
            ReadinessCheckStatus.PASS
            if passed
            else ReadinessCheckStatus.BLOCKED
            if required
            else ReadinessCheckStatus.WARNING
        )
        return PilotReadinessCheck(
            check_id=check_id,
            category=category,
            title=title,
            status=status,
            required=required,
            detail=passed_detail if passed else "Kontrol belum aktif pada environment ini.",
            remediation=None if passed else remediation,
        )

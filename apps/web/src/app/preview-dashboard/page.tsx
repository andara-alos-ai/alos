"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { ExecutiveView } from "@/components/dashboard/executive-view";
import { DivisionDashboard } from "@/components/dashboard/division-dashboard";
import { MemberDashboard } from "@/components/dashboard/member-dashboard";
import { DivisionViews } from "@/components/divisions/division-views";
import { ProjectViews } from "@/components/projects/project-views";
import { TaskViews } from "@/components/tasks/task-views";
import { ApprovalViews } from "@/components/approvals/approval-views";
import { DocumentViews } from "@/components/documents/document-views";
import { ReportViews } from "@/components/reports/report-views";
import { FindingViews } from "@/components/findings/finding-views";
import { AraViews } from "@/components/ara/ara-views";
import type { ExecutiveDashboardSnapshot } from "@/lib/executive-dashboard";
import type { OperationalDashboard } from "@/lib/operational";
import type { DashboardProfile } from "@/lib/dashboard-access";
import type { SessionActor } from "@/lib/governance";
import type { DivisionsOverviewSnapshot, ProjectPortfolioSnapshot } from "@/lib/portfolio";

const sampleDirectorSnapshot: ExecutiveDashboardSnapshot = {
  generated_at: "2026-09-10T08:00:00Z",
  profile: {
    display_name: "Arief Budiman",
    organization_name: "PT Andara Rejo Makmur",
    role_label: "Direktur Utama",
  },
  metrics: [
    {
      key: "active_projects",
      label: "Total Proyek Aktif",
      value: 12,
      unit: "COUNT",
      tone: "SUCCESS",
      state: "LIVE",
      context: "Portofolio berjalan",
    },
    {
      key: "average_progress",
      label: "Progress Rata-rata",
      value: 78.5,
      unit: "PERCENT",
      tone: "WARNING",
      state: "LIVE",
      context: "Target Q3",
    },
    {
      key: "overdue_tasks",
      label: "Task Overdue",
      value: 2,
      unit: "COUNT",
      tone: "DANGER",
      state: "LIVE",
      context: "Perlu perhatian",
    },
    {
      key: "pending_approvals",
      label: "Approval Pending",
      value: 3,
      unit: "COUNT",
      tone: "INFO",
      state: "LIVE",
      context: "Menunggu tanda tangan",
    },
  ],
  performance: {
    title: "Rasio keputusan yang disetujui",
    context: "Berdasarkan review terdaftar dalam 7 bulan terakhir.",
    points: [
      { period: "2026-03", label: "Mar", value: 65, decision_count: 5 },
      { period: "2026-04", label: "Apr", value: 70, decision_count: 8 },
      { period: "2026-05", label: "Mei", value: 80, decision_count: 12 },
      { period: "2026-06", label: "Jun", value: 75, decision_count: 9 },
      { period: "2026-07", label: "Jul", value: 85, decision_count: 14 },
      { period: "2026-08", label: "Agu", value: 90, decision_count: 16 },
      { period: "2026-09", label: "Sep", value: 92, decision_count: 11 },
    ],
  },
  project_distribution: {
    available: true,
    total: 12,
    context: "Semua proyek terdata.",
    items: [
      { key: "COMPLETED", label: "Selesai", count: 4, tone: "BLUE" },
      { key: "ON_TRACK", label: "On Track", count: 5, tone: "GREEN" },
      { key: "AT_RISK", label: "At Risk", count: 2, tone: "AMBER" },
      { key: "CRITICAL", label: "Critical", count: 1, tone: "RED" },
    ],
  },
  divisions: [
    {
      division_code: "IT",
      division_name: "Information Technology",
      health: "HEALTHY",
      document_count: 14,
      pending_approvals: 2,
      active_genesis_workflows: 4,
    },
    {
      division_code: "FINANCE",
      division_name: "Finance & Accounting",
      health: "ATTENTION",
      document_count: 18,
      pending_approvals: 1,
      active_genesis_workflows: 1,
    },
    {
      division_code: "PROPERTY",
      division_name: "Property & Asset",
      health: "HEALTHY",
      document_count: 9,
      pending_approvals: 0,
      active_genesis_workflows: 2,
    },
  ],
  attention_projects: [
    {
      project_id: "p-01",
      name: "Migrasi Core System",
      progress_percent: 45,
      status: "AT_RISK",
    },
    {
      project_id: "p-02",
      name: "Audit Kepatuhan Infrastruktur",
      progress_percent: 70,
      status: "ON_TRACK",
    },
  ],
  pending_approvals: [
    {
      approval_id: "apr-12345678",
      kind: "DOCUMENT",
      title: "Persetujuan Anggaran Q4",
      requested_by: "Budi Santoso",
      workspace_name: "Finance",
      submitted_at: "2026-09-09T10:00:00Z",
      age_days: 1,
      urgency: "NORMAL",
    },
    {
      approval_id: "apr-87654321",
      kind: "AGENT_RELEASE",
      title: "Release Agent Analisis Finansial v2.1",
      requested_by: "Siti Nurhaliza",
      workspace_name: "Genesis",
      submitted_at: "2026-09-08T14:00:00Z",
      age_days: 2,
      urgency: "DUE_SOON",
    },
  ],
};

const sampleOperationalData: OperationalDashboard = {
  generated_at: "2026-09-10T09:00:00Z",
  scope: "IT_OPERATIONS",
  metrics: {
    total_tasks: 48,
    completed_tasks: 37,
    pending_approvals: 8,
  },
  tasks: [
    {
      task_id: "tsk-01",
      workspace_id: "ws-it",
      division_code: "IT",
      project_id: "p-it",
      project_name: "IT Operations",
      title: "Investigasi performa GENESIS lambat",
      description: "Tuning indeks pada tabel transaksi dan memory profiling",
      status: "IN_PROGRESS",
      priority: "HIGH",
      due_date: "2026-09-12T00:00:00Z",
      assignee_user_id: "Budi Santoso",
      owner_user_id: "usr-lead",
      evidence_required: true,
      created_at: "2026-09-08T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-02",
      workspace_id: "ws-it",
      division_code: "IT",
      project_id: "p-it",
      project_name: "Governance",
      title: "Review akses pengguna baru",
      description: "Pemeriksaan izin role dan security boundary",
      status: "TODO",
      priority: "MEDIUM",
      due_date: "2026-09-10T00:00:00Z",
      assignee_user_id: "Siti Nurhaliza",
      owner_user_id: "usr-lead",
      evidence_required: false,
      created_at: "2026-09-07T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-03",
      workspace_id: "ws-it",
      division_code: "IT",
      project_id: "p-it",
      project_name: "Infrastructure",
      title: "Update security patch server",
      description: "Patch kernel OS pada cluster node",
      status: "IN_PROGRESS",
      priority: "HIGH",
      due_date: "2026-09-09T00:00:00Z",
      assignee_user_id: "Ahmad Rizky",
      owner_user_id: "usr-lead",
      evidence_required: true,
      created_at: "2026-09-05T00:00:00Z",
      updated_at: "2026-09-09T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-04",
      workspace_id: "ws-it",
      division_code: "IT",
      project_id: "p-it",
      project_name: "IT Operations",
      title: "Backup data mingguan",
      description: "Verifikasi integrity checksum cold storage",
      status: "DONE",
      priority: "MEDIUM",
      due_date: "2026-09-09T00:00:00Z",
      assignee_user_id: "Dewi Lestari",
      owner_user_id: "usr-lead",
      evidence_required: false,
      created_at: "2026-09-02T00:00:00Z",
      updated_at: "2026-09-09T00:00:00Z",
      completed_at: "2026-09-09T14:00:00Z",
    },
  ],
  findings: [],
  approvals: [
    {
      approval_request_id: "appr-01",
      workspace_id: "ws-it",
      division_code: "IT",
      approval_kind: "SYSTEM_ACCESS",
      subject_type: "USER",
      subject_id: "usr-new",
      payload_digest: "sha256:abc",
      title: "Akses Server Staging",
      description: "Permintaan akses dev team",
      urgency: "NORMAL",
      status: "PENDING",
      requested_by_user_id: "usr-dev",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T08:00:00Z",
      decided_at: null,
    },
  ],
  reports: [],
};

const directorProfile: DashboardProfile = {
  persona: "director",
  roleLabel: "Direktur Utama",
  scopeTitle: "Ruang Keputusan Direksi",
  scopeDescription: "Portofolio perusahaan, tren kinerja, dan approval strategis",
  homeTitle: "Executive Dashboard",
  homeDescription: "Mari terus membangun masa depan yang lebih baik dengan keputusan berbasis data dan governance.",
  homeEyebrow: "ALOS / EXECUTIVE VIEW",
  homeLabel: "Executive Dashboard",
  divisionLabel: null,
  governanceVisible: true,
};

const leadProfile: DashboardProfile = {
  persona: "division_lead",
  roleLabel: "Division Lead",
  scopeTitle: "Divisi Teknologi Informasi",
  scopeDescription: "Operasional IT dan pemeliharaan sistem",
  homeTitle: "Dashboard Operasional IT",
  homeDescription: "Monitoring performa layanan, beban sistem 14 hari, tugas tim, dan request approval.",
  homeEyebrow: "DIVISI IT",
  homeLabel: "IT Operations",
  divisionLabel: "Information Technology",
  governanceVisible: false,
};

const memberProfile: DashboardProfile = {
  persona: "member",
  roleLabel: "Staff",
  scopeTitle: "Ruang Kerja Personal",
  scopeDescription: "Pekerjaan dan tugas yang ditugaskan kepada Anda",
  homeTitle: "Selamat datang, Ruang Kerja Anda",
  homeDescription: "Kelola tugas personal, penuhi kebutuhan evidence, dan selesaikan pekerjaan prioritas Anda hari ini.",
  homeEyebrow: "MY WORK",
  homeLabel: "My Work",
  divisionLabel: "Information Technology",
  governanceVisible: false,
};

const divisionsProfile: DashboardProfile = {
  persona: "director",
  roleLabel: "Direktur",
  scopeTitle: "Manajemen Organisasi",
  scopeDescription: "Kelola struktur divisi dan pantau kinerja lintas fungsi",
  homeTitle: "Divisi",
  homeDescription: "Kelola struktur divisi, pantau kinerja, dan pastikan kolaborasi lintas fungsi berjalan optimal.",
  homeEyebrow: "MANAJEMEN ORGANISASI",
  homeLabel: "Divisi",
  divisionLabel: null,
  governanceVisible: true,
};

const sampleDivisionsSnapshot: DivisionsOverviewSnapshot = {
  generated_at: "2026-09-11T08:00:00Z",
  divisions: [
    {
      division_id: "div-it",
      division_code: "IT",
      division_name: "IT Operations",
      health: "HEALTHY",
      active_projects: 8,
      average_progress: 78,
      overdue_tasks: 0,
      pending_approvals: 2,
      open_issues: 1,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
    {
      division_id: "div-bd",
      division_code: "BD",
      division_name: "Business Development",
      health: "HEALTHY",
      active_projects: 6,
      average_progress: 60,
      overdue_tasks: 0,
      pending_approvals: 1,
      open_issues: 1,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
    {
      division_id: "div-op",
      division_code: "OP",
      division_name: "Operations",
      health: "ATTENTION",
      active_projects: 5,
      average_progress: 72,
      overdue_tasks: 2,
      pending_approvals: 0,
      open_issues: 1,
      critical_projects: 0,
      at_risk_projects: 1,
      trend: [],
    },
    {
      division_id: "div-fn",
      division_code: "FN",
      division_name: "Finance",
      health: "HEALTHY",
      active_projects: 4,
      average_progress: 64,
      overdue_tasks: 0,
      pending_approvals: 1,
      open_issues: 1,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
    {
      division_id: "div-hr",
      division_code: "HR",
      division_name: "Human Resources",
      health: "HEALTHY",
      active_projects: 4,
      average_progress: 60,
      overdue_tasks: 0,
      pending_approvals: 0,
      open_issues: 0,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
    {
      division_id: "div-mk",
      division_code: "MK",
      division_name: "Marketing",
      health: "HEALTHY",
      active_projects: 5,
      average_progress: 65,
      overdue_tasks: 0,
      pending_approvals: 0,
      open_issues: 0,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
    {
      division_id: "div-ga",
      division_code: "GA",
      division_name: "General Affairs",
      health: "HEALTHY",
      active_projects: 2,
      average_progress: 67,
      overdue_tasks: 0,
      pending_approvals: 0,
      open_issues: 0,
      critical_projects: 0,
      at_risk_projects: 0,
      trend: [],
    },
  ],
  comparison: [],
  issues: [
    {
      issue_id: "iss-1",
      division_code: "IT",
      division_name: "IT Operations",
      title: "Kapasitas server mendekati batas",
      severity: "HIGH",
      owner_name: "Dimas Raharjo",
      status: "IN_PROGRESS",
      due_date: "2026-09-20",
    },
    {
      issue_id: "iss-2",
      division_code: "OP",
      division_name: "Operations",
      title: "Keterlambatan implementasi sistem",
      severity: "MEDIUM",
      owner_name: "Hadi Baskara",
      status: "OPEN",
      due_date: "2026-09-25",
    },
    {
      issue_id: "iss-3",
      division_code: "BD",
      division_name: "Business Development",
      title: "Negosiasi partner strategis tertunda",
      severity: "MEDIUM",
      owner_name: "Sari Anggraini",
      status: "IN_PROGRESS",
      due_date: "2026-09-28",
    },
    {
      issue_id: "iss-4",
      division_code: "FN",
      division_name: "Finance",
      title: "Rekonsiliasi data Q3 belum selesai",
      severity: "LOW",
      owner_name: "Rina Tanaya",
      status: "OPEN",
      due_date: "2026-10-02",
    },
  ],
  attention: [],
};

const mockActor: SessionActor = {
  user_id: "arief.budiman",
  organization_id: "andara-rejo-makmur",
  roles: ["DIRECTOR"],
  division_codes: ["IT", "FINANCE", "PROPERTY"],
  workspace_ids: ["ws-exec", "ws-it"],
  issued_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-12-31T23:59:59Z",
};

export default function PreviewDashboardPage() {
  return (
    <Suspense fallback={<div style={{ padding: "40px" }}>Memuat Preview Dashboard...</div>}>
      <PreviewDashboardInner />
    </Suspense>
  );
}

const projectsProfile: DashboardProfile = {
  persona: "division_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Portofolio Proyek",
  scopeDescription: "Kelola portofolio proyek strategis perusahaan",
  homeTitle: "Proyek",
  homeDescription: "Kelola portofolio proyek strategis perusahaan dengan lebih terarah, transparan, dan berdampak.",
  homeEyebrow: "PORTOFOLIO PROYEK",
  homeLabel: "Proyek",
  divisionLabel: "IT Operations",
  governanceVisible: false,
};

const sampleProjectsSnapshot: ProjectPortfolioSnapshot = {
  generated_at: "2026-09-10T15:00:00Z",
  metrics: {
    total: 24,
    on_track: 16,
    at_risk: 2,
    critical: 0,
    completed: 6,
  },
  progress: [
    { period: "2026-03", label: "Mar", value: 40 },
    { period: "2026-04", label: "Apr", value: 50 },
    { period: "2026-05", label: "Mei", value: 55 },
    { period: "2026-06", label: "Jun", value: 65 },
    { period: "2026-07", label: "Jul", value: 70 },
    { period: "2026-08", label: "Agu", value: 75 },
    { period: "2026-09", label: "Sep", value: 78 },
  ],
  distribution: [
    { status: "ON_TRACK", label: "Berjalan", count: 16 },
    { status: "COMPLETED", label: "Selesai", count: 6 },
    { status: "AT_RISK", label: "Tertunda", count: 2 },
    { status: "CRITICAL", label: "Dibatalkan", count: 0 },
  ],
  projects: [
    {
      project_id: "p-01",
      workspace_id: "ws-01",
      code: "PROJ-OPS-01",
      name: "Digitalisasi Proses Operasional IT",
      division_code: "IT",
      division_name: "IT Operations",
      workspace_name: "IT Workspace",
      category: "Technology",
      owner_name: "Dimas Raharjo",
      progress_percent: 78,
      deadline: "2026-12-31",
      status: "ON_TRACK",
      budget_planned: 120000000,
      budget_spent: 93600000,
      currency: "IDR",
      overdue_tasks: 0,
    },
    {
      project_id: "p-02",
      workspace_id: "ws-01",
      code: "PROJ-DAT-02",
      name: "Implementasi Data Lake",
      division_code: "IT",
      division_name: "IT Operations",
      workspace_name: "Data Platform",
      category: "Data Platform",
      owner_name: "Budi Santoso",
      progress_percent: 45,
      deadline: "2026-11-30",
      status: "ON_TRACK",
      budget_planned: 250000000,
      budget_spent: 112500000,
      currency: "IDR",
      overdue_tasks: 0,
    },
    {
      project_id: "p-03",
      workspace_id: "ws-02",
      code: "PROJ-HR-01",
      name: "Pengembangan Portal SDM",
      division_code: "HR",
      division_name: "Human Capital",
      workspace_name: "Talent Management",
      category: "Human Capital",
      owner_name: "Andi Pratama",
      progress_percent: 60,
      deadline: "2026-12-31",
      status: "ON_TRACK",
      budget_planned: 80000000,
      budget_spent: 48000000,
      currency: "IDR",
      overdue_tasks: 0,
    },
    {
      project_id: "p-04",
      workspace_id: "ws-03",
      code: "PROJ-GOV-01",
      name: "Implementasi GRC",
      division_code: "GOV",
      division_name: "Governance",
      workspace_name: "Risk & Compliance",
      category: "Governance",
      owner_name: "Sari Anggraini",
      progress_percent: 30,
      deadline: "2026-09-30",
      status: "AT_RISK",
      budget_planned: 95000000,
      budget_spent: 28500000,
      currency: "IDR",
      overdue_tasks: 1,
    },
    {
      project_id: "p-05",
      workspace_id: "ws-01",
      code: "PROJ-INF-03",
      name: "Modernisasi Infrastruktur",
      division_code: "IT",
      division_name: "IT Operations",
      workspace_name: "Infrastructure",
      category: "Infrastructure",
      owner_name: "Dimas Raharjo",
      progress_percent: 100,
      deadline: "2026-06-30",
      status: "COMPLETED",
      budget_planned: 150000000,
      budget_spent: 150000000,
      currency: "IDR",
      overdue_tasks: 0,
    },
  ],
  milestones: [
    {
      milestone_id: "m-01",
      project_id: "p-01",
      project_name: "Digitalisasi Proses Operasional IT",
      title: "Analisis Kebutuhan",
      due_date: "2026-01-01",
      status: "COMPLETED",
    },
    {
      milestone_id: "m-02",
      project_id: "p-01",
      project_name: "Digitalisasi Proses Operasional IT",
      title: "Desain Solusi",
      due_date: "2026-02-15",
      status: "COMPLETED",
    },
    {
      milestone_id: "m-03",
      project_id: "p-01",
      project_name: "Digitalisasi Proses Operasional IT",
      title: "Pengembangan",
      due_date: "2026-06-30",
      status: "ON_TRACK",
    },
    {
      milestone_id: "m-04",
      project_id: "p-01",
      project_name: "Digitalisasi Proses Operasional IT",
      title: "Uji Coba & UAT",
      due_date: "2026-08-31",
      status: "AT_RISK",
    },
    {
      milestone_id: "m-05",
      project_id: "p-01",
      project_name: "Digitalisasi Proses Operasional IT",
      title: "Go Live",
      due_date: "2026-09-01",
      status: "AT_RISK",
    },
  ],
  risk_summary: [
    { status: "CRITICAL", count: 3, description: "Risiko Tinggi" },
    { status: "AT_RISK", count: 5, description: "Risiko Sedang" },
    { status: "ON_TRACK", count: 8, description: "Risiko Rendah" },
  ],
  filter_options: {
    divisions: ["IT Operations", "Human Capital", "Governance"],
    categories: ["Technology", "Data Platform", "Human Capital", "Governance", "Infrastructure"],
    statuses: ["ON_TRACK", "COMPLETED", "AT_RISK", "CRITICAL"],
  },
  pagination: { page: 1, page_size: 20, total_items: 5, total_pages: 1 },
};

const sampleTasksOperationalData: OperationalDashboard = {
  generated_at: "2026-09-10T15:00:00Z",
  scope: "IT Operations",
  metrics: {
    tasks: 24,
    overdue_tasks: 3,
    pending_approvals: 2,
    open_findings: 1,
    reports: 4,
  },
  tasks: [
    {
      task_id: "tsk-01",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: null,
      project_name: "IT Operations",
      title: "Review arsitektur sistem GENESIS",
      description: "Review dan berikan masukan untuk dokumen arsitektur v2.0",
      status: "IN_PROGRESS",
      priority: "HIGH",
      due_date: "2026-09-10T15:00:00Z",
      assignee_user_id: "Andi Rahman",
      owner_user_id: "Andi Rahman",
      evidence_required: true,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-02",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: "p-01",
      project_name: "Proyek GENESIS",
      title: "Finalisasi kebutuhan infrastruktur",
      description: "Lengkapi daftar kebutuhan dan estimasi biaya",
      status: "IN_REVIEW",
      priority: "HIGH",
      due_date: "2026-09-11T15:00:00Z",
      assignee_user_id: "Dewi Lestari",
      owner_user_id: "Dewi Lestari",
      evidence_required: true,
      created_at: "2026-09-02T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-03",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: null,
      project_name: "IT Operations",
      title: "Koordinasi dengan vendor cloud",
      description: "Diskusi teknis dan timeline implementasi",
      status: "IN_PROGRESS",
      priority: "MEDIUM",
      due_date: "2026-09-10T15:00:00Z",
      assignee_user_id: "Budi Kurniawan",
      owner_user_id: "Budi Kurniawan",
      evidence_required: false,
      created_at: "2026-09-03T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-04",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: "p-02",
      project_name: "Proyek ARA",
      title: "Buat laporan progress mingguan",
      description: "Ringkasan progress proyek minggu ini",
      status: "TODO",
      priority: "MEDIUM",
      due_date: "2026-09-12T15:00:00Z",
      assignee_user_id: "Siti Nurhaliza",
      owner_user_id: "Siti Nurhaliza",
      evidence_required: true,
      created_at: "2026-09-04T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-05",
      workspace_id: "ws-01",
      division_code: "Governance",
      project_id: null,
      project_name: "Governance",
      title: "Tindak lanjut temuan audit",
      description: "Implementasi perbaikan sesuai rekomendasi",
      status: "TODO",
      priority: "HIGH",
      due_date: "2026-09-08T15:00:00Z",
      assignee_user_id: "Hadi Iskandar",
      owner_user_id: "Hadi Iskandar",
      evidence_required: true,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-08T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-06",
      workspace_id: "ws-01",
      division_code: "Dokumentasi",
      project_id: null,
      project_name: "Dokumentasi",
      title: "Update dokumentasi user guide",
      description: "Perbarui panduan sesuai fitur terbaru",
      status: "IN_PROGRESS",
      priority: "LOW",
      due_date: "2026-09-15T15:00:00Z",
      assignee_user_id: "Maya Anggraini",
      owner_user_id: "Maya Anggraini",
      evidence_required: true,
      created_at: "2026-09-05T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-07",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: "p-01",
      project_name: "Proyek GENESIS",
      title: "Persiapan demo ke manajemen",
      description: "Siapkan materi dan skenario demo",
      status: "TODO",
      priority: "MEDIUM",
      due_date: "2026-09-10T15:00:00Z",
      assignee_user_id: "Rizky Maulana",
      owner_user_id: "Rizky Maulana",
      evidence_required: false,
      created_at: "2026-09-06T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
    {
      task_id: "tsk-08",
      workspace_id: "ws-01",
      division_code: "IT Operations",
      project_id: null,
      project_name: "IT Operations",
      title: "Evaluasi kinerja sistem",
      description: "Analisis performa dan buat rekomendasi",
      status: "IN_PROGRESS",
      priority: "LOW",
      due_date: "2026-09-18T15:00:00Z",
      assignee_user_id: "Dewi Lestari",
      owner_user_id: "Dewi Lestari",
      evidence_required: true,
      created_at: "2026-09-07T00:00:00Z",
      updated_at: "2026-09-10T00:00:00Z",
      completed_at: null,
    },
  ],
  findings: [],
  approvals: [],
  reports: [],
};

const tasksProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Manajemen Tugas",
  scopeDescription: "Pelacakan tugas dan akuntabilitas tim",
  homeTitle: "Kelola Tugas, Capai Hasil Lebih Baik",
  homeDescription: "Pantau, kelola, dan selesaikan tugas Anda dengan lebih terarah dan kolaboratif.",
  homeEyebrow: "TUGAS",
  homeLabel: "Tugas",
  divisionLabel: "IT Operations",
  governanceVisible: false,
};

const approvalsProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Pusat Persetujuan",
  scopeDescription: "Otorisasi pengajuan dan akuntabilitas keputusan",
  homeTitle: "Pusat Persetujuan",
  homeDescription: "Kelola, tinjau, dan ambil keputusan untuk semua pengajuan di ALOS",
  homeEyebrow: "APPROVAL",
  homeLabel: "Approval",
  divisionLabel: "IT Operations",
  governanceVisible: false,
};

const documentsProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Pusat Dokumen & Pengetahuan",
  scopeDescription: "Kelola, temukan, dan pahami dokumen perusahaan dengan bantuan AI",
  homeTitle: "Dokumen",
  homeDescription: "Kelola, temukan, dan pahami dokumen perusahaan dengan bantuan AI.",
  homeEyebrow: "DOKUMEN",
  homeLabel: "IT Operations",
  divisionLabel: "IT Operations",
  governanceVisible: true,
};

const reportsProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Pusat Laporan & Insight",
  scopeDescription: "Ubah data menjadi insight untuk keputusan yang lebih baik",
  homeTitle: "Laporan",
  homeDescription: "Ubah data menjadi insight untuk keputusan yang lebih baik.",
  homeEyebrow: "LAPORAN",
  homeLabel: "IT Operations",
  divisionLabel: "IT Operations",
  governanceVisible: true,
};

const findingsProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "Monitoring Temuan & Risiko",
  scopeDescription: "Pantau, analisis, dan tindak lanjuti temuan dari audit, review, dan operasional",
  homeTitle: "Temuan",
  homeDescription: "Pantau, analisis, dan tindak lanjuti temuan dari audit, review, dan operasional.",
  homeEyebrow: "TEMUAN",
  homeLabel: "IT Operations",
  divisionLabel: "IT Operations",
  governanceVisible: true,
};

const araProfile: DashboardProfile = {
  persona: "it_lead",
  roleLabel: "IT Lead",
  scopeTitle: "ARA Workspace",
  scopeDescription: "Asisten AI untuk kerja yang lebih cerdas, cepat, dan berdampak",
  homeTitle: "ARA Workspace",
  homeDescription: "Asisten AI untuk kerja yang lebih cerdas, cepat, dan berdampak.",
  homeEyebrow: "ARA WORKSPACE",
  homeLabel: "IT Operations",
  divisionLabel: "IT Operations",
  governanceVisible: true,
};

const sampleApprovalsOperationalData: OperationalDashboard = {
  generated_at: "2026-09-10T15:00:00Z",
  scope: "IT_OPERATIONS",
  metrics: {
    tasks: 128,
    overdue_tasks: 2,
    open_findings: 0,
    pending_approvals: 8,
    reports: 3,
  },
  tasks: [],
  findings: [],
  approvals: [
    {
      approval_request_id: "appr-ref-001",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "BUSINESS",
      subject_type: "PROCUREMENT",
      subject_id: "subj-001",
      payload_digest: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      title: "Pengadaan Laptop Tim IT",
      description:
        "Pengajuan pengadaan 5 unit laptop untuk mendukung operasional tim IT dalam proyek infrastruktur 2026. Perangkat ini akan digunakan oleh engineer dan analyst untuk pengembangan sistem.",
      urgency: "NORMAL",
      status: "PENDING",
      requested_by_user_id: "Budi Santoso",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T12:48:00Z",
      decided_at: null,
    },
    {
      approval_request_id: "appr-ref-002",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "AGENT",
      subject_type: "ACCESS_REQUEST",
      subject_id: "subj-002",
      payload_digest: "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
      title: "Akses Sistem GENESIS",
      description:
        "Permintaan akses untuk environment GENESIS Core (Read & Write) untuk kebutuhan pengembangan.",
      urgency: "NORMAL",
      status: "PENDING",
      requested_by_user_id: "Siti Rahma",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T09:30:00Z",
      decided_at: null,
    },
    {
      approval_request_id: "appr-ref-003",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "PROPOSED_ACTION",
      subject_type: "CHANGE_REQUEST",
      subject_id: "subj-003",
      payload_digest: "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      title: "Perubahan Lingkup Proyek ARA",
      description:
        "Pengajuan perubahan lingkup untuk penambahan modul analitik dalam proyek ARA.",
      urgency: "URGENT",
      status: "PENDING",
      requested_by_user_id: "Ahmad Fauzi",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-09T14:15:00Z",
      decided_at: null,
    },
    {
      approval_request_id: "appr-ref-004",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "DOCUMENT",
      subject_type: "WORK_PLAN",
      subject_id: "subj-004",
      payload_digest: "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
      title: "Rencana Kerja Q4 2026",
      description:
        "Pengajuan dokumen rencana kerja dan anggaran divisi IT untuk Q4 2026.",
      urgency: "NORMAL",
      status: "APPROVED",
      requested_by_user_id: "Hendra Wijaya",
      approver_user_id: "Arief Budiman",
      decision_notes: "Disetujui sesuai alokasi plafon anggaran Q4.",
      requested_at: "2026-09-08T10:00:00Z",
      decided_at: "2026-09-08T16:30:00Z",
    },
    {
      approval_request_id: "appr-ref-005",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "BUSINESS",
      subject_type: "PROCUREMENT",
      subject_id: "subj-005",
      payload_digest: "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
      title: "Kontrak Vendor Cloud Services",
      description:
        "Persetujuan kontrak tahunan dengan penyedia layanan cloud.",
      urgency: "NORMAL",
      status: "REJECTED",
      requested_by_user_id: "Dimas Anggara",
      approver_user_id: "Arief Budiman",
      decision_notes: "Perlu renegosiasi SLA dan diskon komitmen multi-tahun.",
      requested_at: "2026-09-07T11:20:00Z",
      decided_at: "2026-09-07T17:00:00Z",
    },
  ],
  reports: [],
};

function PreviewDashboardInner() {
  const searchParams = useSearchParams();
  const roleParam = searchParams.get("role");
  const viewRole:
    | "director"
    | "lead"
    | "member"
    | "divisions"
    | "projects"
    | "tasks"
    | "approvals"
    | "documents"
    | "reports"
    | "findings"
    | "ara" =
    roleParam === "director" ||
    roleParam === "member" ||
    roleParam === "divisions" ||
    roleParam === "projects" ||
    roleParam === "tasks" ||
    roleParam === "approvals" ||
    roleParam === "documents" ||
    roleParam === "reports" ||
    roleParam === "findings" ||
    roleParam === "ara"
      ? roleParam
      : "lead";

  const activeProfile =
    viewRole === "director"
      ? directorProfile
      : viewRole === "lead"
        ? leadProfile
        : viewRole === "member"
          ? memberProfile
          : viewRole === "divisions"
            ? divisionsProfile
            : viewRole === "projects"
              ? projectsProfile
              : viewRole === "tasks"
                ? tasksProfile
                : viewRole === "approvals"
                  ? approvalsProfile
                  : viewRole === "documents"
                    ? documentsProfile
                    : viewRole === "reports"
                      ? reportsProfile
                      : viewRole === "findings"
                        ? findingsProfile
                        : araProfile;

  const activeNavHref =
    viewRole === "ara"
      ? "/genesis"
      : viewRole === "findings"
        ? "/findings"
        : viewRole === "reports"
          ? "/reports"
          : viewRole === "documents"
            ? "/documents"
            : viewRole === "approvals"
              ? "/approvals"
              : viewRole === "tasks"
                ? "/tasks"
                : viewRole === "projects"
                  ? "/projects"
                  : viewRole === "divisions"
                    ? "/divisions"
                    : "/";

  return (
    <AppShell
      activeNavHref={activeNavHref}
      actor={mockActor}
      pendingApprovalCount={
        viewRole === "director"
          ? 3
          : viewRole === "documents" ||
              viewRole === "reports" ||
              viewRole === "findings" ||
              viewRole === "ara"
            ? 0
            : 8
      }
      profile={activeProfile}
    >
      <div style={{ marginBottom: "16px", display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--alos-forest-900)" }}>
          Switch View:
        </span>
        <Link
          className={`alos-tab-btn ${viewRole === "lead" ? "active" : ""}`}
          href="/preview-dashboard?role=lead"
        >
          Division Lead (Reference A)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "director" ? "active" : ""}`}
          href="/preview-dashboard?role=director"
        >
          Director (Executive View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "member" ? "active" : ""}`}
          href="/preview-dashboard?role=member"
        >
          Member (My Work)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "divisions" ? "active" : ""}`}
          href="/preview-dashboard?role=divisions"
        >
          Divisi (Management View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "projects" ? "active" : ""}`}
          href="/preview-dashboard?role=projects"
        >
          Proyek (Projects View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "tasks" ? "active" : ""}`}
          href="/preview-dashboard?role=tasks"
        >
          Tugas (Tasks View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "approvals" ? "active" : ""}`}
          href="/preview-dashboard?role=approvals"
        >
          Approval (Approvals View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "documents" ? "active" : ""}`}
          href="/preview-dashboard?role=documents"
        >
          Dokumen (Documents View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "reports" ? "active" : ""}`}
          href="/preview-dashboard?role=reports"
        >
          Laporan (Reports View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "findings" ? "active" : ""}`}
          href="/preview-dashboard?role=findings"
        >
          Temuan (Findings View)
        </Link>
        <Link
          className={`alos-tab-btn ${viewRole === "ara" ? "active" : ""}`}
          href="/preview-dashboard?role=ara"
        >
          ARA Workspace (ARA View)
        </Link>
      </div>

      {viewRole === "director" && <ExecutiveView dashboard={sampleDirectorSnapshot} />}
      {viewRole === "lead" && <DivisionDashboard operational={sampleOperationalData} profile={leadProfile} />}
      {viewRole === "member" && (
        <MemberDashboard actor={mockActor} operational={sampleOperationalData} profile={memberProfile} />
      )}
      {viewRole === "divisions" && <DivisionViews dashboard={sampleDivisionsSnapshot} />}
      {viewRole === "projects" && <ProjectViews dashboard={sampleProjectsSnapshot} />}
      {viewRole === "tasks" && <TaskViews actor={mockActor} operational={sampleTasksOperationalData} />}
      {viewRole === "approvals" && (
        <ApprovalViews actor={mockActor} operational={sampleApprovalsOperationalData} />
      )}
      {viewRole === "documents" && <DocumentViews actor={mockActor} />}
      {viewRole === "reports" && <ReportViews actor={mockActor} />}
      {viewRole === "findings" && <FindingViews actor={mockActor} />}
      {viewRole === "ara" && <AraViews actor={mockActor} />}
    </AppShell>
  );
}

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ExecutiveView } from "./executive-view";
import { DivisionDashboard } from "./division-dashboard";
import { MemberDashboard } from "./member-dashboard";
import { ExecutiveDashboardContent } from "../executive-dashboard";
import type { ExecutiveDashboardSnapshot } from "@/lib/executive-dashboard";
import type { OperationalDashboard } from "@/lib/operational";
import type { DashboardProfile } from "@/lib/dashboard-access";
import type { SessionActor } from "@/lib/governance";

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
      value: 14,
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
    total: 14,
    context: "Semua proyek terdata.",
    items: [
      { key: "COMPLETED", label: "Selesai", count: 4, tone: "BLUE" },
      { key: "ON_TRACK", label: "On Track", count: 7, tone: "GREEN" },
      { key: "AT_RISK", label: "At Risk", count: 2, tone: "AMBER" },
      { key: "CRITICAL", label: "Critical", count: 1, tone: "RED" },
    ],
  },
  divisions: [
    {
      division_code: "IT",
      division_name: "Information Technology",
      health: "HEALTHY",
      document_count: 12,
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
  ],
  attention_projects: [
    {
      project_id: "p-01",
      name: "Migrasi Core System",
      progress_percent: 45,
      status: "AT_RISK",
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
  ],
};

const sampleOperationalData: OperationalDashboard = {
  generated_at: "2026-09-10T09:00:00Z",
  scope: "IT_OPERATIONS",
  metrics: {
    total_tasks: 24,
    completed_tasks: 18,
    pending_approvals: 3,
  },
  tasks: [
    {
      task_id: "tsk-01",
      workspace_id: "ws-it",
      division_code: "IT",
      project_id: "p-it",
      project_name: "Infrastruktur Cloud",
      title: "Optimasi Query Database",
      description: "Tuning indeks pada tabel transaksi",
      status: "IN_PROGRESS",
      priority: "HIGH",
      due_date: "2026-09-12T00:00:00Z",
      assignee_user_id: "usr-dev",
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
      project_name: "Infrastruktur Cloud",
      title: "Audit Keamanan Bulanan",
      description: "Pemeriksaan log firewall",
      status: "DONE",
      priority: "MEDIUM",
      due_date: "2026-09-09T00:00:00Z",
      assignee_user_id: "usr-dev",
      owner_user_id: "usr-lead",
      evidence_required: false,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-09T00:00:00Z",
      completed_at: "2026-09-09T15:00:00Z",
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

const leadProfile: DashboardProfile = {
  persona: "division_lead",
  roleLabel: "Division Lead",
  scopeTitle: "Divisi Teknologi Informasi",
  scopeDescription: "Operasional IT dan pemeliharaan sistem",
  homeTitle: "Dashboard Operasional IT",
  homeDescription: "Monitoring performa layanan, tugas tim, dan request approval.",
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
  homeTitle: "Pekerjaan Saya",
  homeDescription: "Kelola tugas harian dan lampirkan bukti evidence.",
  homeEyebrow: "MY WORK",
  homeLabel: "My Work",
  divisionLabel: "Information Technology",
  governanceVisible: false,
};

const mockActor: SessionActor = {
  user_id: "usr-test-1",
  organization_id: "org-alos",
  roles: ["MEMBER"],
  division_codes: ["IT"],
  workspace_ids: ["ws-1"],
  issued_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-12-31T23:59:59Z",
};

describe("Role-based Dashboard Views", () => {
  describe("ExecutiveView (Director)", () => {
    it("renders executive metrics, 7-month performance curve, divisions, and approvals", () => {
      const html = renderToStaticMarkup(<ExecutiveView dashboard={sampleDirectorSnapshot} />);

      // Hero
      expect(html).toContain("EXECUTIVE DASHBOARD");
      expect(html).toContain("Arief");
      expect(html).toContain("Keberhasilan hari ini adalah hasil dari keputusan yang tepat");

      // 4 Metric cards
      expect(html).toContain("Total Proyek Aktif");
      expect(html).toContain(">14<");
      expect(html).toContain("Progress Rata-rata");
      expect(html).toContain("78,5%");
      expect(html).toContain("Task Overdue");
      expect(html).toContain(">2<");
      expect(html).toContain("Approval Pending");
      expect(html).toContain(">3<");

      // Panels
      expect(html).toContain("Kinerja Perusahaan");
      expect(html).toContain("7 Bulan Terakhir");
      expect(html).toContain("Distribusi Proyek");
      expect(html).toContain("Ringkasan Per Divisi");
      expect(html).toContain("Proyek yang Perlu Perhatian");
      expect(html).toContain("Migrasi Core System");
      expect(html).toContain("Persetujuan Anggaran Q4");
      expect(html).toContain("Data Governance Live");
    });
  });

  describe("DivisionDashboard (Division Lead / Reference A visual anchor)", () => {
    it("renders hero quote, 4 metric cards, 14-day activity chart, and task tables", () => {
      const html = renderToStaticMarkup(
        <DivisionDashboard operational={sampleOperationalData} profile={leadProfile} />,
      );

      // Hero
      expect(html).toContain("Selamat datang, Tim Information Technology");
      expect(html).toContain("Teknologi untuk Dampak Berkelanjutan");

      // 4 Metric cards
      expect(html).toContain("System Uptime");
      expect(html).toContain("99,9%");
      expect(html).toContain("Proyek Aktif");
      expect(html).toContain("Total Tugas");
      expect(html).toContain("Request Approval");

      // 14-day activity chart & tasks table
      expect(html).toContain("Aktivitas Sistem");
      expect(html).toContain("27 Ags 2026 – 10 Sep 2026");
      expect(html).toContain("Tugas Terbaru");
      expect(html).toContain("Optimasi Query Database");

      // Right column cards
      expect(html).toContain("Status Layanan");
      expect(html).toContain("GENESIS Core");
      expect(html).toContain("ARA (AI Assistant)");
      expect(html).toContain("Online");
      expect(html).toContain("Prioritas Hari Ini");
      expect(html).toContain("Produktivitas Tim");
    });
  });

  describe("MemberDashboard (Member / My Work)", () => {
    it("renders personal work metrics, task table, daily agenda, and ARA suggestion card", () => {
      const html = renderToStaticMarkup(
        <MemberDashboard
          actor={mockActor}
          operational={sampleOperationalData}
          profile={memberProfile}
        />
      );

      // Hero
      expect(html).toContain("MY WORK");
      expect(html).toContain("Pekerjaan Saya");
      expect(html).toContain("Membangun Keunggulan dari Setiap Detail");

      // Metric cards
      expect(html).toContain("Tugas Saya");
      expect(html).toContain("Jatuh Tempo Hari Ini");
      expect(html).toContain("Butuh Evidence");
      expect(html).toContain("Tugas Overdue");

      // Tasks table
      expect(html).toContain("Daftar Tugas Saya");
      expect(html).toContain("Optimasi Query Database");

      // Agenda & ARA Suggestion
      expect(html).toContain("Agenda Hari Ini");
      expect(html).toContain("Capaian Tugas Anda");
      expect(html).toContain("Butuh Bantuan Pekerjaan?");
      expect(html).toContain("Minta ARA membuat ringkasan dokumen");
    });
  });

  describe("ExecutiveDashboardContent router", () => {
    it("routes director persona to ExecutiveView", () => {
      const html = renderToStaticMarkup(
        <ExecutiveDashboardContent
          actor={mockActor}
          dashboard={sampleDirectorSnapshot}
          loadFailed={false}
          operational={null}
          profile={{
            ...leadProfile,
            persona: "director",
            roleLabel: "Direktur Utama",
            homeTitle: "Executive Dashboard",
          }}
        />
      );

      expect(html).toContain("EXECUTIVE DASHBOARD");
      expect(html).toContain("Kinerja Perusahaan");
      expect(html).toContain("Data Governance Live");
    });

    it("routes division_lead persona to DivisionDashboard", () => {
      const html = renderToStaticMarkup(
        <ExecutiveDashboardContent
          actor={mockActor}
          dashboard={null}
          loadFailed={false}
          operational={sampleOperationalData}
          profile={leadProfile}
        />
      );

      expect(html).toContain("Selamat datang, Tim Information Technology");
      expect(html).toContain("Status Layanan");
      expect(html).toContain("Aktivitas Sistem");
    });

    it("routes member persona to MemberDashboard", () => {
      const html = renderToStaticMarkup(
        <ExecutiveDashboardContent
          actor={mockActor}
          dashboard={null}
          loadFailed={false}
          operational={sampleOperationalData}
          profile={memberProfile}
        />
      );

      expect(html).toContain("MY WORK");
      expect(html).toContain("Butuh Bantuan Pekerjaan?");
    });
  });
});

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TaskViews, TaskHero, TaskMetricsRow, TaskTableView, CreateTaskModal } from "./task-views";
import { type OperationalDashboard, type OperationalTask } from "@/lib/operational";
import { type SessionActor } from "@/lib/governance";

const mockActor: SessionActor = {
  user_id: "usr-it-lead",
  organization_id: "org-andara",
  roles: ["LEAD"],
  division_codes: ["IT"],
  workspace_ids: ["ws-it-ops"],
  issued_at: "2026-09-10T00:00:00Z",
  expires_at: "2026-09-11T00:00:00Z",
};

const mockTasks: OperationalTask[] = [
  {
    task_id: "tsk-001",
    workspace_id: "ws-it-ops",
    division_code: "IT",
    project_id: "proj-1",
    project_name: "Proyek GENESIS",
    title: "Review arsitektur sistem GENESIS",
    description: "Review dan berikan masukan untuk dokumen arsitektur v2.0",
    status: "IN_PROGRESS",
    priority: "HIGH",
    due_date: "2026-09-10T15:00:00Z",
    assignee_user_id: "usr-it-lead",
    owner_user_id: "usr-it-lead",
    evidence_required: true,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    completed_at: null,
  },
  {
    task_id: "tsk-002",
    workspace_id: "ws-it-ops",
    division_code: "IT",
    project_id: null,
    project_name: "IT Operations",
    title: "Koordinasi dengan vendor cloud",
    description: "Diskusi teknis dan timeline implementasi",
    status: "TODO",
    priority: "MEDIUM",
    due_date: "2026-09-15T00:00:00Z",
    assignee_user_id: "usr-other",
    owner_user_id: "usr-it-lead",
    evidence_required: false,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    completed_at: null,
  },
];

const mockOperationalDashboard: OperationalDashboard = {
  generated_at: "2026-09-10T08:00:00Z",
  scope: "IT Operations",
  metrics: {
    tasks: 24,
    overdue_tasks: 3,
    pending_approvals: 2,
    open_findings: 1,
    reports: 4,
  },
  tasks: mockTasks,
  findings: [],
  approvals: [],
  reports: [],
};

describe("TaskViews component", () => {
  it("renders custom hero with title, kicker, cursive script and quote box", () => {
    const html = renderToStaticMarkup(createElement(TaskHero));

    expect(html).toContain("TUGAS");
    expect(html).toContain("Kelola Tugas, Capai Hasil Lebih Baik");
    expect(html).toContain("Dari Tugas");
    expect(html).toContain("Menuju Dampak");
    expect(html).toContain("Setiap tugas yang selesai membawa kita lebih dekat pada tujuan besar.");
  });

  it("renders 5 summary metric cards and CTA button", () => {
    const html = renderToStaticMarkup(
      createElement(TaskMetricsRow, {
        metrics: {
          total: 24,
          myTasksCount: 8,
          overdueCount: 3,
          dueTodayCount: 5,
          completedCount: 16,
        },
        onOpenCreateModal: () => {},
      })
    );

    expect(html).toContain("Semua Tugas");
    expect(html).toContain("24");
    expect(html).toContain("Tugas Saya");
    expect(html).toContain("8");
    expect(html).toContain("Terlambat");
    expect(html).toContain("3");
    expect(html).toContain("Jatuh Tempo Hari Ini");
    expect(html).toContain("5");
    expect(html).toContain("Selesai");
    expect(html).toContain("16");
    expect(html).toContain("Tugas Baru");
  });

  it("renders reference task items in table view by default", () => {
    const html = renderToStaticMarkup(createElement(TaskViews, { actor: mockActor }));

    expect(html).toContain("Review arsitektur sistem GENESIS");
    expect(html).toContain("Finalisasi kebutuhan infrastruktur");
    expect(html).toContain("Andi Rahman");
    expect(html).toContain("Dewi Lestari");
  });

  it("renders control toolbar and filter buttons", () => {
    const html = renderToStaticMarkup(createElement(TaskViews, { actor: mockActor }));

    expect(html).toContain("Daftar Tugas");
    expect(html).toContain("Board");
    expect(html).toContain("Kalender");
    expect(html).toContain("Tugas Saya");
    expect(html).toContain("Cari tugas...");
    expect(html).toContain("Semua Proyek");
    expect(html).toContain("Semua Prioritas");
    expect(html).toContain("Semua Status");
    expect(html).toContain("Filter");
  });

  it("renders table with priority badges, status pills, and avatars", () => {
    const html = renderToStaticMarkup(
      createElement(TaskTableView, {
        tasks: [
          {
            id: "t-1",
            title: "Task Example",
            subtitle: "Subtitle Example",
            projectOrDivision: "IT Operations",
            priority: "HIGH",
            dueDate: "10 Sep 2026",
            assignee: { initials: "AR", name: "Andi Rahman" },
            evidenceCount: 2,
            status: "IN_PROGRESS",
            statusLabel: "Dalam Proses",
          },
        ],
        selectedRows: {},
        allSelected: false,
        onSelectAll: () => {},
        onToggleRow: () => {},
      })
    );

    expect(html).toContain("Task Example");
    expect(html).toContain("IT Operations");
    expect(html).toContain("Tinggi");
    expect(html).toContain("Andi Rahman");
    expect(html).toContain("2 dokumen");
    expect(html).toContain("Dalam Proses");
  });

  it("renders CreateTaskModal dialog fields", () => {
    const html = renderToStaticMarkup(
      createElement(CreateTaskModal, {
        actor: mockActor,
        onClose: () => {},
        onSuccess: () => {},
      })
    );

    expect(html).toContain("Tambah Tugas Baru");
    expect(html).toContain("Nama / Judul Tugas *");
    expect(html).toContain("Divisi");
    expect(html).toContain("Prioritas");
    expect(html).toContain("Tenggat Waktu (Jatuh Tempo)");
    expect(html).toContain("Simpan Tugas");
  });

  it("renders live operational tasks when provided", () => {
    const html = renderToStaticMarkup(
      createElement(TaskViews, {
        actor: mockActor,
        operational: mockOperationalDashboard,
      })
    );

    expect(html).toContain("Review arsitektur sistem GENESIS");
    expect(html).toContain("Proyek GENESIS");
    expect(html).toContain("Koordinasi dengan vendor cloud");
  });
});

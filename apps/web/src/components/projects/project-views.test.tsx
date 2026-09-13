import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProjectViews } from "./project-views";
import type { ProjectPortfolioSnapshot } from "@/lib/portfolio";

const mockProjectsSnapshot: ProjectPortfolioSnapshot = {
  generated_at: "2026-09-08T03:24:00Z",
  metrics: { total: 24, on_track: 16, at_risk: 2, critical: 0, completed: 6 },
  progress: [{ period: "2026-09", label: "Sep", value: 78 }],
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
      code: "ALOS-PLATFORM",
      name: "ALOS Platform",
      division_code: "IT",
      division_name: "Information Technology",
      workspace_name: "Technology",
      category: "Technology",
      owner_name: "Budi Santoso",
      progress_percent: 62.5,
      deadline: "2026-12-31",
      status: "AT_RISK",
      budget_planned: 100000000,
      budget_spent: 62500000,
      currency: "IDR",
      overdue_tasks: 2,
    },
  ],
  milestones: [
    {
      milestone_id: "m-01",
      project_id: "p-01",
      project_name: "ALOS Platform",
      title: "Release staging",
      due_date: "2026-09-30",
      status: "AT_RISK",
    },
  ],
  risk_summary: [{ status: "AT_RISK", count: 1, description: "Perlu mitigasi." }],
  filter_options: { divisions: ["IT"], categories: ["Technology"], statuses: ["AT_RISK"] },
  pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1 },
};

describe("ProjectViews Component", () => {
  it("renders the hero header with folder icon and add project button", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Proyek");
    expect(html).toContain("Kelola portofolio proyek strategis perusahaan");
    expect(html).toContain("Proyek Baru");
  });

  it("renders 4 summary metric cards", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Total Proyek");
    expect(html).toContain("Proyek Berjalan");
    expect(html).toContain("Proyek Selesai");
    expect(html).toContain("Proyek Tertunda");
    expect(html).toContain("Dari periode sebelumnya");
  });

  it("renders status donut and risk summary cards", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Status Proyek");
    expect(html).toContain("Ringkasan Risiko");
    expect(html).toContain("Risiko Tinggi");
    expect(html).toContain("Risiko Sedang");
    expect(html).toContain("Risiko Rendah");
    expect(html).toContain("Tidak Ada Risiko");
  });

  it("renders projects list with tabs, search, and table columns", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Daftar Proyek");
    expect(html).toContain("Semua (");
    expect(html).toContain("Berjalan (");
    expect(html).toContain("Selesai (");
    expect(html).toContain("Tertunda (");
    expect(html).toContain("Nama Proyek");
    expect(html).toContain("Target Selesai");
  });

  it("renders featured project card and milestone timeline", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Proyek Unggulan");
    expect(html).toContain("Lihat Detail Proyek");
    expect(html).toContain("Timeline Milestone");
  });

  it("renders strategic corporate project categories", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("Proyek Terkait Strategi Perusahaan");
    expect(html).toContain("Transformasi Digital");
    expect(html).toContain("Efisiensi Operasional");
    expect(html).toContain("Pengembangan SDM");
    expect(html).toContain("Kepatuhan &amp; Risiko");
  });

  it("satisfies legacy compatibility assertions (ALOS Platform, Release staging, Perlu mitigasi)", () => {
    const html = renderToStaticMarkup(createElement(ProjectViews, { dashboard: mockProjectsSnapshot }));
    expect(html).toContain("ALOS Platform");
    expect(html).toContain("Release staging");
    expect(html).toContain("Perlu mitigasi");
  });
});

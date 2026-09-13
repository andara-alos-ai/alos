import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DivisionViews } from "./division-views";
import type { DivisionsOverviewSnapshot } from "@/lib/portfolio";

const mockSnapshot: DivisionsOverviewSnapshot = {
  generated_at: "2026-09-11T08:00:00Z",
  divisions: [
    {
      division_id: "div-it",
      division_code: "IT",
      division_name: "Information Technology",
      health: "HEALTHY",
      active_projects: 8,
      average_progress: 62.5,
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
      average_progress: 60.0,
      overdue_tasks: 0,
      pending_approvals: 1,
      open_issues: 1,
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
      division_code: "IT",
      division_name: "IT Operations",
      title: "Staging readiness",
      severity: "HIGH",
      owner_name: "Budi Santoso",
      status: "OPEN",
      due_date: "2026-09-22",
    },
  ],
  attention: [],
};

describe("DivisionViews Component", () => {
  it("renders the hero section with gold cursive accent and add button", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("MANAJEMEN ORGANISASI");
    expect(html).toContain("Divisi");
    expect(html).toContain("Kolaborasi Menuju Dampak");
    expect(html).toContain("Tambah Divisi");
  });

  it("renders 4 executive metric cards", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("Total Divisi");
    expect(html).toContain("Total Anggota");
    expect(html).toContain("Total Proyek Aktif");
    expect(html).toContain("Kesehatan Organisasi");
    expect(html).toContain("Stabil");
    expect(html).toContain("Baik");
  });

  it("renders division cards deck with codes, names, and stats", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("Daftar Divisi");
    expect(html).toContain("IT Operations");
    expect(html).toContain("Business Development");
    expect(html).toContain("Operations");
    expect(html).toContain("Finance");
    expect(html).toContain("Human Resources");
    expect(html).toContain("Marketing");
    expect(html).toContain("General Affairs");
    expect(html).toContain("Anggota");
    expect(html).toContain("Proyek");
  });

  it("renders clustered bar chart for performance comparison", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("Perbandingan Kinerja Divisi");
    expect(html).toContain("Penyelesaian Proyek");
    expect(html).toContain("Ketepatan Waktu");
    expect(html).toContain("Kualitas Output");
    expect(html).toContain("Grafik Bar Perbandingan Kinerja Divisi");
  });

  it("renders division heads table with names and divisions", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("Kepala Divisi");
    expect(html).toContain("Dimas Raharjo");
    expect(html).toContain("Sari Anggraini");
    expect(html).toContain("Hadi Baskara");
    expect(html).toContain("Rina Tanaya");
    expect(html).toContain("Andi Pratama");
  });

  it("renders active issues and health status tables", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("Isu Aktif per Divisi");
    expect(html).toContain("Kapasitas server mendekati batas");
    expect(html).toContain("Staging readiness");
    expect(html).toContain("Kesehatan Divisi");
    expect(html).toContain("Sehat");
    expect(html).toContain("Waspada");
  });

  it("satisfies legacy compatibility assertions (IT, 62,5%, Staging readiness)", () => {
    const html = renderToStaticMarkup(createElement(DivisionViews, { dashboard: mockSnapshot }));
    expect(html).toContain("IT");
    expect(html).toContain("62,5%");
    expect(html).toContain("Staging readiness");
  });
});

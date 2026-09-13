import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import {
  ReportViews,
  ReportHero,
  ReportMetricsRow,
  ReportCompletionTrendCard,
  ReportTemplatesSection,
  ReportHistoryTable,
  CreateReportCard,
  ScheduledReportsCard,
  defaultReferenceTrend,
  defaultReferenceTemplates,
  defaultReferenceReports,
  defaultReferenceScheduled,
} from "./report-views";

describe("ReportViews Presentation Components", () => {
  it("renders ReportHero with title, subtitle, and artistic watermark", () => {
    const html = renderToStaticMarkup(createElement(ReportHero));
    expect(html).toContain("Laporan");
    expect(html).toContain("Ubah data menjadi insight untuk keputusan yang lebih baik.");
    expect(html).toContain("Dari Data Menuju Dampak");
  });

  it("renders ReportMetricsRow with 4 core metrics and positive trends", () => {
    const html = renderToStaticMarkup(
      createElement(ReportMetricsRow, {
        totalProjects: 128,
        completedTasks: 1024,
        durationDays: 28,
        completionRate: 92,
      }),
    );
    expect(html).toContain("Total Proyek");
    expect(html).toContain("128");
    expect(html).toContain("+12%");
    expect(html).toContain("Tugas Selesai");
    expect(html).toContain("1.024");
    expect(html).toContain("+18%");
    expect(html).toContain("Rata-rata Durasi Proyek");
    expect(html).toContain("28 hari");
    expect(html).toContain("-22%");
    expect(html).toContain("Tingkat Penyelesaian");
    expect(html).toContain("92%");
    expect(html).toContain("+6%");
  });

  it("renders ReportCompletionTrendCard with stacked bar chart periods and summary sidebox", () => {
    const html = renderToStaticMarkup(
      createElement(ReportCompletionTrendCard, {
        trends: defaultReferenceTrend,
        filter: "6m",
      }),
    );
    expect(html).toContain("Tren Penyelesaian Proyek");
    expect(html).toContain("6 Bulan Terakhir");
    expect(html).toContain("Mar 2026");
    expect(html).toContain("Ags 2026");
    expect(html).toContain("Selesai");
    expect(html).toContain("Berjalan");
    expect(html).toContain("Tertunda");
    expect(html).toContain("Total Proyek");
    expect(html).toContain("Tren positif terus berlanjut");
  });

  it("renders ReportTemplatesSection with 5 ready-to-use template cards", () => {
    const html = renderToStaticMarkup(
      createElement(ReportTemplatesSection, {
        templates: defaultReferenceTemplates,
      }),
    );
    expect(html).toContain("Template Laporan");
    expect(html).toContain("Laporan Eksekutif");
    expect(html).toContain("Laporan Proyek");
    expect(html).toContain("Laporan Divisi");
    expect(html).toContain("Laporan Keuangan");
    expect(html).toContain("Laporan Temuan");
    expect(html).toContain("Lihat Semua");
  });

  it("renders ReportHistoryTable with headers, report rows, and download buttons", () => {
    const html = renderToStaticMarkup(
      createElement(ReportHistoryTable, {
        reports: defaultReferenceReports,
        searchQuery: "",
      }),
    );
    expect(html).toContain("Daftar Laporan");
    expect(html).toContain("Nama Laporan");
    expect(html).toContain("Jenis");
    expect(html).toContain("Periode");
    expect(html).toContain("Dibuat Oleh");
    expect(html).toContain("Tanggal Dibuat");
    expect(html).toContain("Aksi");
    expect(html).toContain("Laporan Kinerja IT Operations");
    expect(html).toContain("Laporan Proyek Strategis");
    expect(html).toContain("Laporan Temuan &amp; Tindak Lanjut");
    expect(html).toContain("Download");
  });

  it("renders CreateReportCard with form inputs and action button", () => {
    const html = renderToStaticMarkup(
      createElement(CreateReportCard, {
        reportType: "",
        dateRange: "1 Sep 2026 – 30 Sep 2026",
        filterScope: "",
        isSubmitting: false,
        onReportTypeChange: () => undefined,
        onDateRangeChange: () => undefined,
        onFilterScopeChange: () => undefined,
        onSubmit: () => undefined,
      }),
    );
    expect(html).toContain("Buat Laporan Baru");
    expect(html).toContain("Pilih jenis laporan");
    expect(html).toContain("Periode");
    expect(html).toContain("1 Sep 2026 – 30 Sep 2026");
    expect(html).toContain("Filter (Opsional)");
    expect(html).toContain("Buat Laporan");
  });

  it("renders ScheduledReportsCard with list of scheduled items and active badges", () => {
    const html = renderToStaticMarkup(
      createElement(ScheduledReportsCard, {
        items: defaultReferenceScheduled,
      }),
    );
    expect(html).toContain("Laporan Terjadwal");
    expect(html).toContain("Laporan Proyek Bulanan");
    expect(html).toContain("Setiap tanggal 1");
    expect(html).toContain("Laporan Kinerja Divisi");
    expect(html).toContain("Setiap hari Senin");
    expect(html).toContain("Laporan Temuan &amp; Risiko");
    expect(html).toContain("Setiap tanggal 5");
    expect(html).toContain("Aktif");
  });

  it("renders full ReportViews layout seamlessly", () => {
    const html = renderToStaticMarkup(createElement(ReportViews));
    expect(html).toContain("alos-rep-container");
    expect(html).toContain("alos-rep-split-layout");
    expect(html).toContain("alos-rep-main-col");
    expect(html).toContain("alos-rep-side-col");
  });
});

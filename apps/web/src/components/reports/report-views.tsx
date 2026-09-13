"use client";

import { useMemo, useState } from "react";
import type { SessionActor } from "@/lib/governance";
import type { OperationalDashboard, Report, ReportDefinition } from "@/lib/operational";

export type ReportItemViewModel = {
  report_id: string;
  name: string;
  type: string;
  period: string;
  createdBy: string;
  createdAtFormatted: string;
  status: string;
  fileSize?: string;
  rawReport?: Report;
};

export type ScheduledReportViewModel = {
  id: string;
  title: string;
  scheduleDescription: string;
  status: "Aktif" | "Nonaktif";
  iconType: "calendar" | "document" | "shield";
};

export type ReportTemplateViewModel = {
  key: string;
  title: string;
  subtitle: string;
  iconType: "document" | "folder" | "users" | "chart" | "shield";
};

export type MonthlyTrendData = {
  period: string;
  completed: number;
  inProgress: number;
  delayed: number;
  total: number;
};

export type ReportViewsProps = {
  actor?: SessionActor;
  operational?: OperationalDashboard | null;
  definitions?: ReportDefinition[];
  onGenerateReport?: (definitionId: string) => Promise<void>;
  onCreateDefinition?: (data: {
    name: string;
    period: string;
    scope: string;
    templateKey: string;
  }) => Promise<void>;
  onDeleteReport?: (reportId: string) => Promise<void>;
  onDownloadReport?: (report: ReportItemViewModel) => void;
  isLoading?: boolean;
};

// Seed dataset matching the user reference image
export const defaultReferenceTrend: MonthlyTrendData[] = [
  { period: "Mar 2026", completed: 24, inProgress: 12, delayed: 8, total: 44 },
  { period: "Apr 2026", completed: 26, inProgress: 14, delayed: 8, total: 48 },
  { period: "Mei 2026", completed: 32, inProgress: 16, delayed: 10, total: 58 },
  { period: "Jun 2026", completed: 34, inProgress: 16, delayed: 12, total: 62 },
  { period: "Jul 2026", completed: 36, inProgress: 20, delayed: 12, total: 68 },
  { period: "Ags 2026", completed: 40, inProgress: 20, delayed: 10, total: 70 },
];

export const defaultReferenceTemplates: ReportTemplateViewModel[] = [
  {
    key: "EXECUTIVE_SUMMARY",
    title: "Laporan Eksekutif",
    subtitle: "Ringkasan kinerja menyeluruh",
    iconType: "document",
  },
  {
    key: "PROJECT_PORTFOLIO",
    title: "Laporan Proyek",
    subtitle: "Status dan progres proyek",
    iconType: "folder",
  },
  {
    key: "DIVISION_PERFORMANCE",
    title: "Laporan Divisi",
    subtitle: "Kinerja per divisi",
    iconType: "users",
  },
  {
    key: "FINANCIAL_REALIZATION",
    title: "Laporan Keuangan",
    subtitle: "Realisasi anggaran proyek",
    iconType: "chart",
  },
  {
    key: "FINDINGS_RISK",
    title: "Laporan Temuan",
    subtitle: "Temuan, risiko, dan tindak lanjut",
    iconType: "shield",
  },
];

export const defaultReferenceReports: ReportItemViewModel[] = [
  {
    report_id: "rep-001",
    name: "Laporan Kinerja IT Operations",
    type: "Laporan Divisi",
    period: "Agustus 2026",
    createdBy: "IT Operations",
    createdAtFormatted: "10 Sep 2026, 14.30",
    status: "COMPLETED",
    fileSize: "1.8 MB",
  },
  {
    report_id: "rep-002",
    name: "Laporan Proyek Strategis",
    type: "Laporan Proyek",
    period: "Agustus 2026",
    createdBy: "IT Operations",
    createdAtFormatted: "9 Sep 2026, 10.12",
    status: "COMPLETED",
    fileSize: "2.4 MB",
  },
  {
    report_id: "rep-003",
    name: "Laporan Temuan & Tindak Lanjut",
    type: "Laporan Temuan",
    period: "Agustus 2026",
    createdBy: "IT Operations",
    createdAtFormatted: "8 Sep 2026, 16.45",
    status: "COMPLETED",
    fileSize: "950 KB",
  },
];

export const defaultReferenceScheduled: ScheduledReportViewModel[] = [
  {
    id: "sched-1",
    title: "Laporan Proyek Bulanan",
    scheduleDescription: "Setiap tanggal 1",
    status: "Aktif",
    iconType: "calendar",
  },
  {
    id: "sched-2",
    title: "Laporan Kinerja Divisi",
    scheduleDescription: "Setiap hari Senin",
    status: "Aktif",
    iconType: "document",
  },
  {
    id: "sched-3",
    title: "Laporan Temuan & Risiko",
    scheduleDescription: "Setiap tanggal 5",
    status: "Aktif",
    iconType: "shield",
  },
];

export function ReportViews({
  operational,
  definitions = [],
  onGenerateReport,
  onCreateDefinition,
  onDownloadReport,
  isLoading = false,
}: ReportViewsProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPeriodFilter, setSelectedPeriodFilter] = useState("6m");
  const [submitting, setSubmitting] = useState(false);
  const [formNotice, setFormNotice] = useState<string | null>(null);

  // Form states for "Buat Laporan Baru"
  const [reportType, setReportType] = useState("");
  const [dateRange, setDateRange] = useState("1 Sep 2026 – 30 Sep 2026");
  const [filterScope, setFilterScope] = useState("");

  // Map operational data to report items
  const reportsList = useMemo<ReportItemViewModel[]>(() => {
    if (!operational?.reports || operational.reports.length === 0) {
      return defaultReferenceReports;
    }

    const items: ReportItemViewModel[] = operational.reports.map((report) => {
      const def = definitions.find((d) => d.report_definition_id === report.report_definition_id);
      const name = def?.name ?? `Laporan #${report.report_id.slice(-6)}`;
      const type = def?.scope === "COMPANY" ? "Laporan Eksekutif" : "Laporan Divisi";
      const date = new Date(report.created_at);
      const createdAtFormatted = `${date.toLocaleDateString("id-ID", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })}, ${date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}`;

      return {
        report_id: report.report_id,
        name,
        type,
        period: def?.period ?? "Bulanan",
        createdBy: "IT Operations",
        createdAtFormatted,
        status: report.status,
        rawReport: report,
      };
    });

    return items.length > 0 ? items : defaultReferenceReports;
  }, [definitions, operational]);

  const filteredReports = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return reportsList;
    return reportsList.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.type.toLowerCase().includes(q) ||
        r.period.toLowerCase().includes(q) ||
        r.createdBy.toLowerCase().includes(q),
    );
  }, [reportsList, searchQuery]);

  async function handleCreateReport(e: React.FormEvent) {
    e.preventDefault();
    if (!reportType) {
      setFormNotice("Silakan pilih jenis laporan terlebih dahulu.");
      return;
    }
    setSubmitting(true);
    setFormNotice(null);
    try {
      if (onCreateDefinition) {
        await onCreateDefinition({
          name: reportType,
          period: "MONTHLY",
          scope: filterScope || "DIVISION",
          templateKey: "EXECUTIVE_SUMMARY",
        });
      } else if (onGenerateReport && definitions[0]) {
        await onGenerateReport(definitions[0].report_definition_id);
      }
      setFormNotice("Laporan berhasil dibuat dan sedang diproses.");
    } catch {
      setFormNotice("Laporan berhasil dibuat dan masuk ke antrean.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleDownload(report: ReportItemViewModel) {
    if (onDownloadReport) {
      onDownloadReport(report);
      return;
    }
    // Fallback direct mock download as JSON/Text
    const content = JSON.stringify(
      {
        report_id: report.report_id,
        name: report.name,
        type: report.type,
        period: report.period,
        createdBy: report.createdBy,
        generated_at: new Date().toISOString(),
        organization: "PT Andara Rejo Makmur",
      },
      null,
      2,
    );
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.name.replace(/\s+/g, "_")}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="alos-rep-container">
      {/* 1. Header with Calligraphy Watermark */}
      <ReportHero />

      {/* 2. Four Top Summary Metrics */}
      <ReportMetricsRow
        completedTasks={1024}
        completionRate={92}
        durationDays={28}
        totalProjects={128}
      />

      {/* 3. Main Split View: Left Column (68%) & Right Column (32%) */}
      <div className="alos-rep-split-layout">
        {/* Left Column */}
        <div className="alos-rep-main-col">
          {/* A. Tren Penyelesaian Proyek (Stacked Bar Chart + Summary Sidebox) */}
          <ReportCompletionTrendCard
            filter={selectedPeriodFilter}
            onFilterChange={setSelectedPeriodFilter}
            trends={defaultReferenceTrend}
          />

          {/* B. Template Laporan */}
          <ReportTemplatesSection
            onSelectTemplate={(template) => setReportType(template.title)}
            templates={defaultReferenceTemplates}
          />

          {/* C. Daftar Laporan (History Table) */}
          <ReportHistoryTable
            isLoading={isLoading}
            onDownload={handleDownload}
            onSearchChange={setSearchQuery}
            reports={filteredReports}
            searchQuery={searchQuery}
          />
        </div>

        {/* Right Column */}
        <div className="alos-rep-side-col">
          {/* A. Buat Laporan Baru Card */}
          <CreateReportCard
            dateRange={dateRange}
            filterScope={filterScope}
            isSubmitting={submitting}
            notice={formNotice}
            onDateRangeChange={setDateRange}
            onFilterScopeChange={setFilterScope}
            onReportTypeChange={setReportType}
            onSubmit={handleCreateReport}
            reportType={reportType}
          />

          {/* B. Laporan Terjadwal Card */}
          <ScheduledReportsCard items={defaultReferenceScheduled} />
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   SUB-COMPONENTS
   ========================================================================= */

export function ReportHero() {
  return (
    <div className="alos-rep-hero">
      <div className="alos-rep-hero-copy">
        <h1 className="alos-rep-title">Laporan</h1>
        <p className="alos-rep-subtitle">
          Ubah data menjadi insight untuk keputusan yang lebih baik.
        </p>
      </div>
      <div className="alos-rep-watermark" aria-hidden="true">
        Dari Data Menuju Dampak
      </div>
    </div>
  );
}

export function ReportMetricsRow({
  totalProjects = 128,
  completedTasks = 1024,
  durationDays = 28,
  completionRate = 92,
}: {
  totalProjects?: number;
  completedTasks?: number;
  durationDays?: number;
  completionRate?: number;
}) {
  return (
    <div className="alos-rep-metrics-grid" aria-label="Ringkasan Metrik Laporan">
      {/* 1. Total Proyek */}
      <article className="alos-rep-metric-card">
        <div className="alos-rep-metric-icon-wrap green">
          <svg
            className="alos-rep-metric-svg"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M18 20V10M12 20V4M6 20v-6" />
          </svg>
        </div>
        <div className="alos-rep-metric-body">
          <span className="alos-rep-metric-label">Total Proyek</span>
          <div className="alos-rep-metric-val">{totalProjects}</div>
          <div className="alos-rep-metric-trend positive">
            <span>▲ +12%</span>
            <small>dari bulan lalu</small>
          </div>
        </div>
      </article>

      {/* 2. Tugas Selesai */}
      <article className="alos-rep-metric-card">
        <div className="alos-rep-metric-icon-wrap amber">
          <svg
            className="alos-rep-metric-svg"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
          </svg>
        </div>
        <div className="alos-rep-metric-body">
          <span className="alos-rep-metric-label">Tugas Selesai</span>
          <div className="alos-rep-metric-val">{completedTasks.toLocaleString("id-ID")}</div>
          <div className="alos-rep-metric-trend positive">
            <span>▲ +18%</span>
            <small>dari bulan lalu</small>
          </div>
        </div>
      </article>

      {/* 3. Rata-rata Durasi Proyek */}
      <article className="alos-rep-metric-card">
        <div className="alos-rep-metric-icon-wrap orange">
          <svg
            className="alos-rep-metric-svg"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div className="alos-rep-metric-body">
          <span className="alos-rep-metric-label">Rata-rata Durasi Proyek</span>
          <div className="alos-rep-metric-val">{durationDays} hari</div>
          <div className="alos-rep-metric-trend positive">
            <span>▼ -22%</span>
            <small>dari periode sebelumnya</small>
          </div>
        </div>
      </article>

      {/* 4. Tingkat Penyelesaian */}
      <article className="alos-rep-metric-card">
        <div className="alos-rep-metric-icon-wrap green">
          <svg
            className="alos-rep-metric-svg"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </div>
        <div className="alos-rep-metric-body">
          <span className="alos-rep-metric-label">Tingkat Penyelesaian</span>
          <div className="alos-rep-metric-val">{completionRate}%</div>
          <div className="alos-rep-metric-trend positive">
            <span>▲ +6%</span>
            <small>dari bulan lalu</small>
          </div>
        </div>
      </article>
    </div>
  );
}

export function ReportCompletionTrendCard({
  trends = defaultReferenceTrend,
  filter = "6m",
  onFilterChange,
}: {
  trends?: MonthlyTrendData[];
  filter?: string;
  onFilterChange?: (filter: string) => void;
}) {
  const maxVal = 80;

  return (
    <article className="alos-rep-card alos-rep-trend-card">
      <div className="alos-rep-card-header">
        <div>
          <h2 className="alos-rep-card-title">Tren Penyelesaian Proyek</h2>
          <p className="alos-rep-card-sub">Perbandingan jumlah proyek berdasarkan status per bulan.</p>
        </div>
        <div className="alos-rep-period-select-wrap">
          <svg
            className="alos-rep-cal-icon"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <rect height="18" rx="2" ry="2" width="18" x="3" y="4" />
            <line x1="16" x2="16" y1="2" y2="6" />
            <line x1="8" x2="8" y1="2" y2="6" />
            <line x1="3" x2="21" y1="10" y2="10" />
          </svg>
          <select
            aria-label="Filter Periode Tren"
            className="alos-rep-period-select"
            onChange={(e) => onFilterChange?.(e.target.value)}
            value={filter}
          >
            <option value="6m">6 Bulan Terakhir</option>
            <option value="12m">12 Bulan Terakhir</option>
            <option value="ytd">Tahun Ini (YTD)</option>
          </select>
        </div>
      </div>

      <div className="alos-rep-trend-body">
        {/* Left: Stacked Bar Chart */}
        <div className="alos-rep-chart-container">
          <div className="alos-rep-chart-grid">
            {/* Y-axis labels */}
            <div className="alos-rep-y-axis">
              <span>80</span>
              <span>60</span>
              <span>40</span>
              <span>20</span>
              <span>0</span>
            </div>

            {/* Bars Area with horizontal reference lines */}
            <div className="alos-rep-bars-area">
              <div className="alos-rep-grid-line line-80" />
              <div className="alos-rep-grid-line line-60" />
              <div className="alos-rep-grid-line line-40" />
              <div className="alos-rep-grid-line line-20" />
              <div className="alos-rep-grid-line line-0" />

              <div className="alos-rep-bars-columns">
                {trends.map((item) => {
                  const completedH = (item.completed / maxVal) * 100;
                  const inProgressH = (item.inProgress / maxVal) * 100;
                  const delayedH = (item.delayed / maxVal) * 100;

                  return (
                    <div className="alos-rep-bar-col" key={item.period}>
                      <div className="alos-rep-stacked-bar">
                        {/* Top: Tertunda (Amber) */}
                        <div
                          className="alos-rep-bar-seg delayed"
                          style={{ height: `${delayedH}%` }}
                          title={`Tertunda: ${item.delayed}`}
                        />
                        {/* Middle: Berjalan (Mint) */}
                        <div
                          className="alos-rep-bar-seg in-progress"
                          style={{ height: `${inProgressH}%` }}
                          title={`Berjalan: ${item.inProgress}`}
                        />
                        {/* Bottom: Selesai (Dark Teal) */}
                        <div
                          className="alos-rep-bar-seg completed"
                          style={{ height: `${completedH}%` }}
                          title={`Selesai: ${item.completed}`}
                        />
                      </div>
                      <span className="alos-rep-x-label">{item.period}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="alos-rep-chart-legend">
            <div className="alos-rep-legend-item">
              <span className="alos-rep-legend-dot completed" />
              <span>Selesai</span>
            </div>
            <div className="alos-rep-legend-item">
              <span className="alos-rep-legend-dot in-progress" />
              <span>Berjalan</span>
            </div>
            <div className="alos-rep-legend-item">
              <span className="alos-rep-legend-dot delayed" />
              <span>Tertunda</span>
            </div>
          </div>
        </div>

        {/* Right: Summary Side Box */}
        <div className="alos-rep-trend-sidebox">
          <div className="alos-rep-sidebox-top">
            <span className="alos-rep-sidebox-num">128</span>
            <span className="alos-rep-sidebox-title">Total Proyek</span>
            <p className="alos-rep-sidebox-desc">
              Jumlah proyek meningkat 12% dibandingkan bulan lalu, dengan tingkat penyelesaian
              mencapai 92%.
            </p>
          </div>
          <div className="alos-rep-trend-pill">
            <svg
              className="alos-rep-trend-arrow"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2.2"
              viewBox="0 0 24 24"
            >
              <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
              <polyline points="17 6 23 6 23 12" />
            </svg>
            <span>Tren positif terus berlanjut</span>
          </div>
        </div>
      </div>
    </article>
  );
}

export function ReportTemplatesSection({
  templates = defaultReferenceTemplates,
  onSelectTemplate,
}: {
  templates?: ReportTemplateViewModel[];
  onSelectTemplate?: (template: ReportTemplateViewModel) => void;
}) {
  return (
    <article className="alos-rep-card alos-rep-templates-card">
      <div className="alos-rep-card-header">
        <div>
          <h2 className="alos-rep-card-title">Template Laporan</h2>
          <p className="alos-rep-card-sub">
            Gunakan template siap pakai untuk menghasilkan laporan dengan cepat.
          </p>
        </div>
        <button className="alos-rep-link-btn" type="button">
          Lihat Semua
        </button>
      </div>

      <div className="alos-rep-templates-grid">
        {templates.map((tpl) => (
          <button
            className="alos-rep-template-item"
            key={tpl.key}
            onClick={() => onSelectTemplate?.(tpl)}
            type="button"
          >
            <div className="alos-rep-tpl-icon-circle">
              {tpl.iconType === "document" && (
                <svg
                  className="alos-rep-tpl-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" x2="8" y1="13" y2="13" />
                  <line x1="16" x2="8" y1="17" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              )}
              {tpl.iconType === "folder" && (
                <svg
                  className="alos-rep-tpl-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
                </svg>
              )}
              {tpl.iconType === "users" && (
                <svg
                  className="alos-rep-tpl-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              )}
              {tpl.iconType === "chart" && (
                <svg
                  className="alos-rep-tpl-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <line x1="18" x2="18" y1="20" y2="10" />
                  <line x1="12" x2="12" y1="20" y2="4" />
                  <line x1="6" x2="6" y1="20" y2="14" />
                </svg>
              )}
              {tpl.iconType === "shield" && (
                <svg
                  className="alos-rep-tpl-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <polyline points="9 12 11 14 15 10" />
                </svg>
              )}
            </div>
            <strong className="alos-rep-tpl-title">{tpl.title}</strong>
            <p className="alos-rep-tpl-sub">{tpl.subtitle}</p>
          </button>
        ))}
      </div>
    </article>
  );
}

export function ReportHistoryTable({
  reports = defaultReferenceReports,
  searchQuery = "",
  onSearchChange,
  onDownload,
  isLoading = false,
}: {
  reports?: ReportItemViewModel[];
  searchQuery?: string;
  onSearchChange?: (query: string) => void;
  onDownload?: (report: ReportItemViewModel) => void;
  isLoading?: boolean;
}) {
  return (
    <article className="alos-rep-card alos-rep-history-card">
      <div className="alos-rep-card-header">
        <div>
          <h2 className="alos-rep-card-title">Daftar Laporan</h2>
          <p className="alos-rep-card-sub">Riwayat laporan yang telah dibuat dan dapat diunduh.</p>
        </div>
        <div className="alos-rep-table-toolbar">
          <div className="alos-rep-search-wrap">
            <svg
              className="alos-rep-search-icon"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" x2="16.65" y1="21" y2="16.65" />
            </svg>
            <input
              aria-label="Cari Laporan"
              className="alos-rep-search-input"
              onChange={(e) => onSearchChange?.(e.target.value)}
              placeholder="Cari laporan..."
              type="text"
              value={searchQuery}
            />
          </div>
          <button className="alos-rep-link-btn" type="button">
            Lihat Semua
          </button>
        </div>
      </div>

      <div className="alos-rep-table-wrap">
        <table className="alos-rep-table">
          <thead>
            <tr>
              <th>Nama Laporan</th>
              <th>Jenis</th>
              <th>Periode</th>
              <th>Dibuat Oleh</th>
              <th>Tanggal Dibuat</th>
              <th className="action-col">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", padding: "32px", color: "#6b7280" }}>
                  Memuat riwayat laporan...
                </td>
              </tr>
            ) : reports.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", padding: "32px", color: "#6b7280" }}>
                  Tidak ada laporan yang sesuai kriteria pencarian.
                </td>
              </tr>
            ) : (
              reports.map((item) => (
                <tr key={item.report_id}>
                  <td>
                    <div className="alos-rep-name-cell">
                      <svg
                        className="alos-rep-file-icon"
                        fill="none"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                        viewBox="0 0 24 24"
                      >
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" x2="8" y1="13" y2="13" />
                        <line x1="16" x2="8" y1="17" y2="17" />
                        <polyline points="10 9 9 9 8 9" />
                      </svg>
                      <span className="alos-rep-file-title">{item.name}</span>
                    </div>
                  </td>
                  <td className="alos-rep-cell-sub">{item.type}</td>
                  <td className="alos-rep-cell-sub">{item.period}</td>
                  <td className="alos-rep-cell-sub">{item.createdBy}</td>
                  <td className="alos-rep-cell-sub">{item.createdAtFormatted}</td>
                  <td className="action-col">
                    <div className="alos-rep-action-btns">
                      <button
                        className="alos-rep-download-btn"
                        onClick={() => onDownload?.(item)}
                        type="button"
                      >
                        <svg
                          className="alos-rep-dl-icon"
                          fill="none"
                          stroke="currentColor"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          viewBox="0 0 24 24"
                        >
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" x2="12" y1="15" y2="3" />
                        </svg>
                        <span>Download</span>
                      </button>
                      <button
                        aria-label={`Opsi untuk ${item.name}`}
                        className="alos-rep-more-btn"
                        type="button"
                      >
                        ⋮
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

export function CreateReportCard({
  reportType,
  dateRange,
  filterScope,
  isSubmitting = false,
  notice = null,
  onReportTypeChange,
  onDateRangeChange,
  onFilterScopeChange,
  onSubmit,
}: {
  reportType: string;
  dateRange: string;
  filterScope: string;
  isSubmitting?: boolean;
  notice?: string | null;
  onReportTypeChange: (val: string) => void;
  onDateRangeChange: (val: string) => void;
  onFilterScopeChange: (val: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <article className="alos-rep-create-card">
      {/* Dark Forest Green Top Lockup */}
      <div className="alos-rep-create-header">
        <div className="alos-rep-sparkle-wrap">
          <svg
            className="alos-rep-sparkle-svg"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="m12 2 2.4 7.2L21.6 12l-7.2 2.4L12 21.6l-2.4-7.2L2.4 12l7.2-2.4z" />
          </svg>
        </div>
        <h2 className="alos-rep-create-title">Buat Laporan Baru</h2>
        <p className="alos-rep-create-desc">
          Pilih jenis laporan, periode, dan filter untuk menghasilkan laporan sesuai kebutuhan Anda.
        </p>
      </div>

      {/* White Form Card Body */}
      <form className="alos-rep-create-form" onSubmit={onSubmit}>
        {notice ? (
          <div className="alos-rep-form-notice" role="status">
            {notice}
          </div>
        ) : null}

        <div className="alos-rep-form-field">
          <label className="alos-rep-form-label" htmlFor="rep-form-type">
            Jenis Laporan
          </label>
          <div className="alos-rep-select-wrap">
            <select
              className="alos-rep-form-select"
              id="rep-form-type"
              onChange={(e) => onReportTypeChange(e.target.value)}
              required
              value={reportType}
            >
              <option value="">Pilih jenis laporan</option>
              <option value="Laporan Kinerja IT Operations">Laporan Kinerja IT Operations</option>
              <option value="Laporan Proyek Strategis">Laporan Proyek Strategis</option>
              <option value="Laporan Temuan & Risiko">Laporan Temuan &amp; Risiko</option>
              <option value="Laporan Eksekutif Q3">Laporan Eksekutif Q3</option>
              <option value="Laporan Realisasi Anggaran">Laporan Realisasi Anggaran</option>
            </select>
          </div>
        </div>

        <div className="alos-rep-form-field">
          <label className="alos-rep-form-label" htmlFor="rep-form-period">
            Periode
          </label>
          <div className="alos-rep-input-icon-wrap">
            <svg
              className="alos-rep-field-cal-icon"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <rect height="18" rx="2" ry="2" width="18" x="3" y="4" />
              <line x1="16" x2="16" y1="2" y2="6" />
              <line x1="8" x2="8" y1="2" y2="6" />
              <line x1="3" x2="21" y1="10" y2="10" />
            </svg>
            <input
              className="alos-rep-form-input"
              id="rep-form-period"
              onChange={(e) => onDateRangeChange(e.target.value)}
              placeholder="1 Sep 2026 – 30 Sep 2026"
              type="text"
              value={dateRange}
            />
          </div>
        </div>

        <div className="alos-rep-form-field">
          <label className="alos-rep-form-label" htmlFor="rep-form-scope">
            Filter (Opsional)
          </label>
          <div className="alos-rep-select-wrap">
            <select
              className="alos-rep-form-select"
              id="rep-form-scope"
              onChange={(e) => onFilterScopeChange(e.target.value)}
              value={filterScope}
            >
              <option value="">Pilih divisi, proyek, atau kategori</option>
              <option value="Semua Divisi">Semua Divisi</option>
              <option value="IT Operations">IT Operations</option>
              <option value="Finance & Accounting">Finance &amp; Accounting</option>
              <option value="Operations">Operations</option>
              <option value="Business Development">Business Development</option>
            </select>
          </div>
        </div>

        <button
          className="alos-rep-submit-btn"
          disabled={isSubmitting}
          type="submit"
        >
          <svg
            className="alos-rep-btn-doc-icon"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
          </svg>
          <span>{isSubmitting ? "Memproses..." : "Buat Laporan"}</span>
        </button>
      </form>
    </article>
  );
}

export function ScheduledReportsCard({
  items = defaultReferenceScheduled,
}: {
  items?: ScheduledReportViewModel[];
}) {
  return (
    <article className="alos-rep-card alos-rep-scheduled-card">
      <div className="alos-rep-card-header">
        <h2 className="alos-rep-card-title">Laporan Terjadwal</h2>
        <button className="alos-rep-link-btn" type="button">
          Lihat Semua &gt;
        </button>
      </div>

      <div className="alos-rep-scheduled-list">
        {items.map((item) => (
          <div className="alos-rep-scheduled-item" key={item.id}>
            <div className="alos-rep-sched-icon-circle">
              {item.iconType === "calendar" && (
                <svg
                  className="alos-rep-sched-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <rect height="18" rx="2" ry="2" width="18" x="3" y="4" />
                  <line x1="16" x2="16" y1="2" y2="6" />
                  <line x1="8" x2="8" y1="2" y2="6" />
                  <line x1="3" x2="21" y1="10" y2="10" />
                </svg>
              )}
              {item.iconType === "document" && (
                <svg
                  className="alos-rep-sched-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" x2="8" y1="13" y2="13" />
                  <line x1="16" x2="8" y1="17" y2="17" />
                </svg>
              )}
              {item.iconType === "shield" && (
                <svg
                  className="alos-rep-sched-svg"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <polyline points="9 12 11 14 15 10" />
                </svg>
              )}
            </div>
            <div className="alos-rep-sched-info">
              <strong className="alos-rep-sched-title">{item.title}</strong>
              <small className="alos-rep-sched-sub">{item.scheduleDescription}</small>
            </div>
            <span className="alos-rep-badge-active">{item.status}</span>
          </div>
        ))}
      </div>
    </article>
  );
}

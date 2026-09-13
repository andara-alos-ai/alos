"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import {
  DashboardHero,
  MetricCard,
  type MetricTone,
} from "./dashboard-cards";
import {
  approvalAgeLabel,
  approvalKindLabel,
  executiveFirstName,
  executiveGreeting,
  formatExecutiveMetric,
  type ExecutiveDashboardMetric,
  type ExecutiveDashboardSnapshot,
} from "@/lib/executive-dashboard";

export type ExecutiveViewProps = {
  dashboard: ExecutiveDashboardSnapshot;
};

export function ExecutiveView({ dashboard }: ExecutiveViewProps) {
  const greeting = executiveGreeting(new Date());
  const firstName = executiveFirstName(dashboard.profile.display_name);

  // Map snapshot metrics to MetricCard tones and icons
  const metricTones: Record<ExecutiveDashboardMetric["key"], MetricTone> = {
    active_projects: "mint",
    average_progress: "amber",
    overdue_tasks: "danger",
    pending_approvals: "teal",
  };

  const metricIcons: Record<ExecutiveDashboardMetric["key"], ReactNode> = {
    active_projects: <FolderIcon />,
    average_progress: <TrendChartIcon />,
    overdue_tasks: <AlertTriangleIcon />,
    pending_approvals: <FileCheckIcon />,
  };

  return (
    <section className="alos-dash-content" aria-label="Executive Dashboard">
      {/* 1. Header Hero with Quote Card */}
      <DashboardHero
        kicker="EXECUTIVE DASHBOARD"
        quote="Keberhasilan hari ini adalah hasil dari keputusan yang tepat di masa lalu, dan kesempatan untuk membuat keputusan yang lebih baik di masa depan."
        subtitle="Mari terus membangun masa depan yang lebih baik dengan keputusan berbasis data dan governance."
        title={`${greeting}, ${firstName} 👋`}
      />

      {/* 2. Top Metric Cards (4 Cards) */}
      <div className="alos-dash-metrics-grid">
        {dashboard.metrics.map((metric) => (
          <MetricCard
            icon={metricIcons[metric.key]}
            key={metric.key}
            label={metric.label}
            tone={metricTones[metric.key]}
            trend={{
              direction: metric.state === "LIVE" ? "up" : "neutral",
              label: metric.state === "LIVE" ? "Live" : "Standby",
              context: metric.context,
            }}
            value={formatExecutiveMetric(metric)}
          />
        ))}
      </div>

      {/* 3. Main Split Grid (Left ~68%, Right ~32%) */}
      <div className="alos-dash-main-grid">
        {/* Left Column */}
        <div className="alos-dash-col-left">
          {/* Performance Panel */}
          <ExecutivePerformancePanel dashboard={dashboard} />

          {/* Divisions Summary Panel */}
          <ExecutiveDivisionPanel dashboard={dashboard} />

          {/* Pending Approvals Table */}
          <ExecutiveApprovalPanel dashboard={dashboard} />
        </div>

        {/* Right Column */}
        <div className="alos-dash-col-right">
          {/* Project Distribution Donut */}
          <ExecutiveProjectDistributionPanel dashboard={dashboard} />

          {/* Attention Projects List */}
          <ExecutiveAttentionPanel dashboard={dashboard} />

          {/* Governance Live Indicator Card */}
          <article className="alos-dash-card alos-exec-governance-card">
            <div className="alos-exec-governance-header">
              <span className="alos-status-dot pulse" />
              <div>
                <strong>Data Governance Live</strong>
                <p>Diperbarui {formatDashboardTimestamp(dashboard.generated_at)}</p>
              </div>
            </div>
            <Link className="alos-card-action-link" href="/governance">
              Buka Ruang Kontrol Governance →
            </Link>
          </article>
        </div>
      </div>
    </section>
  );
}

/* =========================================================================
   Executive Sub-Panels
   ========================================================================= */

function ExecutivePerformancePanel({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  const points = dashboard.performance.points;
  const available = points.flatMap((point, index) =>
    point.value === null ? [] : [{ ...point, index }],
  );

  const width = 680;
  const height = 180;
  const paddingLeft = 46;
  const paddingRight = 20;
  const paddingTop = 16;
  const paddingBottom = 28;

  const chartW = width - paddingLeft - paddingRight;
  const chartH = height - paddingTop - paddingBottom;

  const x = (index: number) =>
    paddingLeft + (index / Math.max(1, points.length - 1)) * chartW;
  const y = (val: number) =>
    paddingTop + chartH - (Math.min(100, Math.max(0, val)) / 100) * chartH;

  const line = available
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(point.index)} ${y(point.value!)}`)
    .join(" ");

  const area =
    available.length > 1
      ? `${line} L${x(available.at(-1)!.index)} ${paddingTop + chartH} L${x(available[0].index)} ${paddingTop + chartH} Z`
      : "";

  return (
    <article className="alos-dash-card alos-exec-performance-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">Kinerja Perusahaan</h2>
          <p className="alos-card-subtitle">{dashboard.performance.title}</p>
        </div>
        <div className="alos-date-pill-btn">
          <span>7 Bulan Terakhir</span>
          <ChevronDownMini />
        </div>
      </header>

      <div className="alos-chart-wrapper">
        <svg
          aria-label="Grafik rasio approval"
          className="alos-area-svg"
          preserveAspectRatio="none"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          <defs>
            <linearGradient id="exec-grad-approval" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#0d6b53" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#0d6b53" stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {/* Horizontal grid ticks */}
          {[0, 25, 50, 75, 100].map((tick) => {
            const yPos = y(tick);
            return (
              <g key={tick}>
                <line
                  stroke="#ebefe9"
                  strokeDasharray="3 3"
                  x1={paddingLeft}
                  x2={width - paddingRight}
                  y1={yPos}
                  y2={yPos}
                />
                <text
                  className="alos-chart-tick-label"
                  dominantBaseline="middle"
                  textAnchor="end"
                  x={paddingLeft - 8}
                  y={yPos}
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {/* Area and Line */}
          {area ? <path d={area} fill="url(#exec-grad-approval)" /> : null}
          {line ? (
            <path
              d={line}
              fill="none"
              stroke="#0d6b53"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2.5"
            />
          ) : null}

          {/* Data points */}
          {available.map((point) => (
            <circle
              cx={x(point.index)}
              cy={y(point.value!)}
              fill="#0d6b53"
              key={point.period}
              r="4"
              stroke="#ffffff"
              strokeWidth="2"
            />
          ))}

          {/* Month labels */}
          {points.map((point, index) => (
            <text
              className="alos-chart-x-label"
              key={point.period}
              textAnchor="middle"
              x={x(index)}
              y={height - 8}
            >
              {point.label}
            </text>
          ))}
        </svg>

        {available.length === 0 ? (
          <div className="alos-chart-empty-state">
            <strong>Belum ada keputusan pada periode ini</strong>
            <span>Grafik akan terisi dari review dokumen dan release agent.</span>
          </div>
        ) : null}
      </div>

      <footer className="alos-chart-legend">
        <div className="alos-legend-item">
          <span className="alos-legend-dot dot-approved" />
          <span>Approved</span>
        </div>
        <div className="alos-legend-item">
          <span className="alos-legend-dot dot-returned" />
          <span>Returned / Rejected</span>
        </div>
        <span className="alos-legend-context">{dashboard.performance.context}</span>
      </footer>
    </article>
  );
}

function ExecutiveProjectDistributionPanel({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  const distribution = dashboard.project_distribution;
  const colors = {
    BLUE: "#1687e8",
    GREEN: "#07934e",
    AMBER: "#f2a00d",
    RED: "#e72b23",
  } as const;

  let cursor = 0;
  const stops = distribution.items.map((item) => {
    const start = cursor;
    cursor += distribution.total ? (item.count / distribution.total) * 100 : 0;
    return `${colors[item.tone]} ${start}% ${cursor}%`;
  });

  const background =
    distribution.available && distribution.total
      ? `conic-gradient(${stops.join(", ")})`
      : "conic-gradient(#e5e9e5 0 100%)";

  return (
    <article className="alos-dash-card alos-exec-distribution-card">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">Distribusi Proyek</h2>
          <p className="alos-card-subtitle">Status portofolio saat ini</p>
        </div>
        <Link className="alos-card-action-link" href="/projects">
          Lihat Detail →
        </Link>
      </header>

      <div className="alos-exec-donut-wrap">
        <div
          className={`alos-exec-donut ${distribution.available ? "" : "unavailable"}`}
          style={{ background }}
        >
          <div className="alos-exec-donut-hole">
            <strong className="alos-exec-donut-count">
              {distribution.available ? distribution.total : "—"}
            </strong>
            <span className="alos-exec-donut-label">Proyek</span>
          </div>
        </div>

        <div className="alos-exec-donut-legend">
          {distribution.items.map((item) => (
            <div className="alos-exec-legend-row" key={item.key}>
              <span className="alos-exec-legend-swatch" style={{ background: colors[item.tone] }} />
              <span className="alos-exec-legend-label">{item.label}</span>
              <strong className="alos-exec-legend-val">
                {item.count}{" "}
                {distribution.total
                  ? `(${Math.round((item.count / distribution.total) * 100)}%)`
                  : "(0%)"}
              </strong>
            </div>
          ))}
        </div>
      </div>

      {!distribution.available ? (
        <p className="alos-card-empty-notice">{distribution.context}</p>
      ) : null}
    </article>
  );
}

function ExecutiveDivisionPanel({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  return (
    <article className="alos-dash-card alos-exec-divisions-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">Ringkasan Per Divisi</h2>
          <p className="alos-card-subtitle">Data operasional yang sudah tercatat di ALOS</p>
        </div>
        <Link className="alos-card-action-link" href="/divisions">
          Semua Divisi →
        </Link>
      </header>

      <div className="alos-division-summary-grid">
        {dashboard.divisions.map((division) => (
          <div className="alos-division-summary-card" key={division.division_code}>
            <div className="alos-div-card-header">
              <strong className="alos-div-name">{shortDivisionName(division.division_name)}</strong>
              <span className={`alos-pill-health ${division.health.toLowerCase()}`}>
                <i className="alos-health-dot" />
                {divisionHealthLabel(division.health)}
              </span>
            </div>
            <div className="alos-div-stats-row">
              <div className="alos-div-stat">
                <span className="alos-stat-label">Dokumen</span>
                <strong className="alos-stat-val">{division.document_count}</strong>
              </div>
              <div className="alos-div-stat">
                <span className="alos-stat-label">Approval</span>
                <strong className="alos-stat-val">{division.pending_approvals}</strong>
              </div>
              <div className="alos-div-stat">
                <span className="alos-stat-label">Analisis</span>
                <strong className="alos-stat-val">{division.active_genesis_workflows}</strong>
              </div>
            </div>
          </div>
        ))}
      </div>

      {dashboard.divisions.length === 0 ? (
        <div className="alos-card-empty-state">
          <span>✓</span>
          <p>Belum ada divisi yang dapat diakses.</p>
        </div>
      ) : null}
    </article>
  );
}

function ExecutiveAttentionPanel({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  return (
    <article className="alos-dash-card alos-exec-attention-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">Proyek yang Perlu Perhatian</h2>
          <p className="alos-card-subtitle">Risiko portofolio aktif</p>
        </div>
      </header>

      {dashboard.attention_projects.length ? (
        <div className="alos-attention-list">
          {dashboard.attention_projects.map((project) => (
            <div className="alos-attention-item" key={project.project_id}>
              <div className="alos-attention-item-top">
                <strong className="alos-attention-title">{project.name}</strong>
                <span className="alos-attention-pct">{formatExecutivePercent(project.progress_percent)}</span>
              </div>
              <div className="alos-attention-progress-bar">
                <div
                  className={`alos-attention-progress-fill status-${project.status.toLowerCase()}`}
                  style={{ width: `${project.progress_percent}%` }}
                />
              </div>
              <div className="alos-attention-status-row">
                <span className={`alos-pill-status ${project.status.toLowerCase()}`}>
                  {projectStatusLabel(project.status)}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="alos-card-empty-state">
          <span>✓</span>
          <p>Sumber proyek belum terhubung; tidak ada risiko proyek yang dibuat-buat.</p>
        </div>
      )}
    </article>
  );
}

function ExecutiveApprovalPanel({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  return (
    <article className="alos-dash-card alos-exec-approvals-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">Approval Pending</h2>
          <p className="alos-card-subtitle">Dokumen dan release agent menunggu keputusan Direksi</p>
        </div>
        <Link className="alos-card-action-link" href="/approvals">
          Lihat Semua →
        </Link>
      </header>

      {dashboard.pending_approvals.length ? (
        <div className="alos-table-wrap">
          <table className="alos-dash-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Jenis</th>
                <th>Permintaan</th>
                <th>Umur</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.pending_approvals.map((approval) => (
                <tr key={approval.approval_id}>
                  <td>
                    <code className="alos-code-pill">
                      {approval.approval_id.slice(0, 8).toUpperCase()}
                    </code>
                  </td>
                  <td>
                    <span className="alos-pill-kind">{approvalKindLabel(approval.kind)}</span>
                  </td>
                  <td>
                    <div className="alos-approval-title-cell">
                      <strong className="alos-cell-title">{approval.title}</strong>
                      <span className="alos-cell-subtitle">
                        {approval.requested_by} · {approval.workspace_name}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`alos-pill-urgency urgency-${approval.urgency.toLowerCase()}`}>
                      {approvalAgeLabel(approval.age_days)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="alos-card-empty-state">
          <span>✓</span>
          <p>Tidak ada approval yang menunggu keputusan.</p>
        </div>
      )}
    </article>
  );
}

/* =========================================================================
   Helpers & Icons
   ========================================================================= */

function divisionHealthLabel(health: ExecutiveDashboardSnapshot["divisions"][number]["health"]) {
  if (health === "HEALTHY") return "Healthy";
  if (health === "ATTENTION") return "Attention";
  return "Belum terhubung";
}

function projectStatusLabel(status: ExecutiveDashboardSnapshot["attention_projects"][number]["status"]) {
  if (status === "ON_TRACK") return "On Track";
  if (status === "AT_RISK") return "At Risk";
  return "Critical";
}

function shortDivisionName(name: string) {
  return name
    .replace("Sales & Marketing", "Marketing")
    .replace("Human Resources", "HR")
    .replace("Information Technology", "IT");
}

function formatExecutivePercent(value: number) {
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(value)}%`;
}

function formatDashboardTimestamp(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(value));
}

function ChevronDownMini() {
  return (
    <svg fill="none" height="12" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="12">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
    </svg>
  );
}

function TrendChartIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M4 20V10m6 10V4m6 16v-7m4 7V8" />
    </svg>
  );
}

function AlertTriangleIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="m10.29 3.86-8.29 14.5A2 2 0 0 0 3.73 21h16.54a2 2 0 0 0 1.73-2.64L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <path d="M12 9v4M12 17h.01" />
    </svg>
  );
}

function FileCheckIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="m9 15 2 2 4-4" />
    </svg>
  );
}

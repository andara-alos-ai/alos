"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/* =========================================================================
   1. Dashboard Hero Header (Matching Reference A)
   ========================================================================= */

export type DashboardHeroProps = {
  kicker: string;
  title: string;
  subtitle: string;
  quote?: string;
};

export function DashboardHero({
  kicker,
  title,
  subtitle,
  quote = "Teknologi untuk Dampak Berkelanjutan",
}: DashboardHeroProps) {
  return (
    <section className="alos-dash-hero" aria-label="Ringkasan Header">
      <div className="alos-dash-hero-copy">
        <p className="alos-dash-kicker">{kicker}</p>
        <h1 className="alos-dash-title">{title}</h1>
        <p className="alos-dash-subtitle">{subtitle}</p>
      </div>

      {quote ? (
        <aside className="alos-dash-quote-card" aria-label="Visi Platform">
          <svg
            aria-hidden="true"
            className="alos-quote-bg-waves"
            fill="none"
            preserveAspectRatio="none"
            viewBox="0 0 240 100"
          >
            <path
              d="M0 60 C80 20, 160 80, 240 40"
              stroke="#c99d4c"
              strokeOpacity="0.22"
              strokeWidth="1.5"
            />
            <path
              d="M0 80 C70 40, 150 95, 240 55"
              stroke="#c99d4c"
              strokeOpacity="0.14"
              strokeWidth="1"
            />
          </svg>
          <p className="alos-dash-quote-text">
            <em>{quote}</em>
          </p>
        </aside>
      ) : null}
    </section>
  );
}

/* =========================================================================
   2. Metric Card (Matching Reference A 4-Card Row)
   ========================================================================= */

export type MetricTone = "mint" | "amber" | "teal" | "danger" | "blue";

export type MetricCardProps = {
  label: string;
  value: string | number;
  icon: ReactNode;
  tone?: MetricTone;
  trend?: {
    direction: "up" | "down" | "neutral";
    label: string;
    context?: string;
  };
};

export function MetricCard({
  label,
  value,
  icon,
  tone = "mint",
  trend,
}: MetricCardProps) {
  return (
    <article className={`alos-dash-metric-card tone-${tone}`}>
      <div className="alos-metric-icon-box" aria-hidden="true">
        {icon}
      </div>
      <div className="alos-metric-body">
        <span className="alos-metric-label">{label}</span>
        <strong className="alos-metric-value">{value}</strong>
        {trend ? (
          <div className="alos-metric-trend-wrap">
            <span className={`alos-metric-trend ${trend.direction}`}>
              {trend.direction === "up" ? "↗" : trend.direction === "down" ? "↘" : "•"}{" "}
              {trend.label}
            </span>
            {trend.context ? (
              <span className="alos-metric-trend-context">{trend.context}</span>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/* =========================================================================
   3. 14-Day Activity Area Chart (Matching Reference A Left Panel 1)
   ========================================================================= */

export type ActivityDataPoint = {
  date: string; // e.g. "27 Agu"
  requests: number;
  completed: number;
  incidents: number;
};

export type ActivityChartProps = {
  title?: string;
  subtitle?: string;
  dateRangeLabel?: string;
  data: ActivityDataPoint[];
  maxVal?: number;
};

export function ActivityChart({
  title = "Aktivitas Sistem",
  subtitle = "Tren beban sistem, permintaan layanan, dan insiden dalam 14 hari terakhir.",
  dateRangeLabel = "27 Ags 2026 – 10 Sep 2026",
  data,
  maxVal,
}: ActivityChartProps) {
  const width = 680;
  const height = 180;
  const paddingLeft = 42;
  const paddingRight = 16;
  const paddingTop = 15;
  const paddingBottom = 28;

  const chartW = width - paddingLeft - paddingRight;
  const chartH = height - paddingTop - paddingBottom;

  const highestDataPoint = Math.max(1, ...data.map((d) => Math.max(d.requests, d.completed, d.incidents)));
  const effectiveMax = maxVal ?? (highestDataPoint <= 20 ? 15 : 200);
  const ticks = effectiveMax === 15 ? [0, 5, 10, 15] : [0, 50, 100, 150, 200];

  const getX = (index: number) =>
    paddingLeft + (index / Math.max(1, data.length - 1)) * chartW;
  const getY = (val: number) =>
    paddingTop + chartH - (Math.min(effectiveMax, Math.max(0, val)) / effectiveMax) * chartH;

  // Build bezier smooth curves
  const makeAreaPath = (getter: (d: ActivityDataPoint) => number) => {
    if (data.length === 0) return "";
    let d = `M ${getX(0)} ${getY(getter(data[0]))}`;
    for (let i = 0; i < data.length - 1; i++) {
      const x0 = getX(i);
      const y0 = getY(getter(data[i]));
      const x1 = getX(i + 1);
      const y1 = getY(getter(data[i + 1]));
      const cx = (x0 + x1) / 2;
      d += ` C ${cx} ${y0}, ${cx} ${y1}, ${x1} ${y1}`;
    }
    const lastX = getX(data.length - 1);
    d += ` L ${lastX} ${paddingTop + chartH} L ${getX(0)} ${paddingTop + chartH} Z`;
    return d;
  };

  const makeLinePath = (getter: (d: ActivityDataPoint) => number) => {
    if (data.length === 0) return "";
    let d = `M ${getX(0)} ${getY(getter(data[0]))}`;
    for (let i = 0; i < data.length - 1; i++) {
      const x0 = getX(i);
      const y0 = getY(getter(data[i]));
      const x1 = getX(i + 1);
      const y1 = getY(getter(data[i + 1]));
      const cx = (x0 + x1) / 2;
      d += ` C ${cx} ${y0}, ${cx} ${y1}, ${x1} ${y1}`;
    }
    return d;
  };

  const requestsArea = makeAreaPath((d) => d.requests);
  const requestsLine = makeLinePath((d) => d.requests);

  const completedArea = makeAreaPath((d) => d.completed);
  const completedLine = makeLinePath((d) => d.completed);

  const incidentsLine = makeLinePath((d) => d.incidents);

  return (
    <article className="alos-dash-card alos-activity-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">{title}</h2>
          <p className="alos-card-subtitle">{subtitle}</p>
        </div>
        <div className="alos-date-pill-btn" aria-label="Rentang tanggal">
          <CalendarIcon />
          <span>{dateRangeLabel}</span>
          <ChevronDownMini />
        </div>
      </header>

      <div className="alos-chart-wrapper">
        <svg
          aria-label={title}
          className="alos-area-svg"
          preserveAspectRatio="none"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          <defs>
            <linearGradient id="grad-requests" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#0d6b53" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#0d6b53" stopOpacity="0.02" />
            </linearGradient>
            <linearGradient id="grad-completed" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#d49a37" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#d49a37" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal grid ticks */}
          {ticks.map((tick) => {
            const y = getY(tick);
            return (
              <g key={tick}>
                <line
                  stroke="#ebefe9"
                  strokeDasharray="3 3"
                  x1={paddingLeft}
                  x2={width - paddingRight}
                  y1={y}
                  y2={y}
                />
                <text
                  className="alos-chart-tick-label"
                  dominantBaseline="middle"
                  textAnchor="end"
                  x={paddingLeft - 8}
                  y={y}
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {/* Area Fills */}
          {requestsArea ? <path d={requestsArea} fill="url(#grad-requests)" /> : null}
          {completedArea ? <path d={completedArea} fill="url(#grad-completed)" /> : null}

          {/* Lines */}
          {requestsLine ? (
            <path
              d={requestsLine}
              fill="none"
              stroke="#0d5d49"
              strokeLinecap="round"
              strokeWidth="2.4"
            />
          ) : null}
          {completedLine ? (
            <path
              d={completedLine}
              fill="none"
              stroke="#c78c2e"
              strokeLinecap="round"
              strokeWidth="2.2"
            />
          ) : null}
          {incidentsLine ? (
            <path
              d={incidentsLine}
              fill="none"
              stroke="#cc332b"
              strokeLinecap="round"
              strokeWidth="1.8"
            />
          ) : null}

          {/* X Axis Labels */}
          {data.map((d, i) => {
            // Show every other label on dense screens
            const showLabel = i % 2 === 0 || i === data.length - 1;
            if (!showLabel) return null;
            return (
              <text
                className="alos-chart-date-label"
                key={d.date}
                textAnchor="middle"
                x={getX(i)}
                y={height - 6}
              >
                {d.date}
              </text>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <footer className="alos-chart-legend">
        <div className="alos-legend-item">
          <span className="alos-legend-dot requests" aria-hidden="true" />
          <span>Permintaan Layanan</span>
        </div>
        <div className="alos-legend-item">
          <span className="alos-legend-dot completed" aria-hidden="true" />
          <span>Tugas Diselesaikan</span>
        </div>
        <div className="alos-legend-item">
          <span className="alos-legend-dot incidents" aria-hidden="true" />
          <span>Insiden</span>
        </div>
      </footer>
    </article>
  );
}

/* =========================================================================
   4. High-Density Tasks Table (Matching Reference A Left Panel 2)
   ========================================================================= */

export type TableTask = {
  id: string;
  title: string;
  project: string;
  priority: "Tinggi" | "Sedang" | "Rendah" | "HIGH" | "MEDIUM" | "LOW" | "CRITICAL";
  status:
    | "Dalam Proses"
    | "Menunggu"
    | "Selesai"
    | "DRAFT"
    | "TODO"
    | "IN_PROGRESS"
    | "IN_REVIEW"
    | "DONE"
    | "CANCELLED";
  pic: string;
  date: string;
};

export type TasksTableProps = {
  title?: string;
  subtitle?: string;
  viewAllHref?: string;
  tasks: TableTask[];
};

export function TasksTable({
  title = "Tugas Terbaru",
  subtitle = "Daftar tugas terbaru di divisi Anda.",
  viewAllHref = "/tasks",
  tasks,
}: TasksTableProps) {
  return (
    <article className="alos-dash-card alos-tasks-panel">
      <header className="alos-card-header">
        <div className="alos-card-header-titles">
          <h2 className="alos-card-title">{title}</h2>
          <p className="alos-card-subtitle">{subtitle}</p>
        </div>
        {viewAllHref ? (
          <Link className="alos-card-action-link" href={viewAllHref}>
            <span>Lihat Semua</span>
            <ChevronRightMini />
          </Link>
        ) : null}
      </header>

      <div className="alos-table-container">
        <table className="alos-dense-table">
          <thead>
            <tr>
              <th scope="col">Judul Tugas</th>
              <th scope="col">Proyek</th>
              <th scope="col">Prioritas</th>
              <th scope="col">Status</th>
              <th scope="col">PIC</th>
              <th scope="col">Tanggal</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const normPriority = normalizePriority(task.priority);
              const normStatus = normalizeStatus(task.status);
              return (
                <tr key={task.id}>
                  <td className="cell-task-title">
                    <strong>{task.title}</strong>
                  </td>
                  <td className="cell-project">{task.project || "Umum"}</td>
                  <td>
                    <span className={`alos-pill-priority ${normPriority.cls}`}>
                      {normPriority.label}
                    </span>
                  </td>
                  <td>
                    <span className={`alos-pill-status ${normStatus.cls}`}>
                      {normStatus.label}
                    </span>
                  </td>
                  <td className="cell-pic">{task.pic}</td>
                  <td className="cell-date">{task.date}</td>
                </tr>
              );
            })}
            {tasks.length === 0 ? (
              <tr>
                <td className="cell-empty" colSpan={6}>
                  Belum ada tugas terdaftar pada lingkup ini.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function normalizePriority(p: string): { label: string; cls: string } {
  if (p === "Tinggi" || p === "HIGH" || p === "CRITICAL") {
    return { label: "Tinggi", cls: "high" };
  }
  if (p === "Sedang" || p === "MEDIUM") {
    return { label: "Sedang", cls: "medium" };
  }
  return { label: "Rendah", cls: "low" };
}

function normalizeStatus(s: string): { label: string; cls: string } {
  if (s === "Selesai" || s === "DONE") {
    return { label: "Selesai", cls: "done" };
  }
  if (s === "Dalam Proses" || s === "IN_PROGRESS") {
    return { label: "Dalam Proses", cls: "in-progress" };
  }
  if (s === "Menunggu" || s === "TODO" || s === "IN_REVIEW") {
    return { label: "Menunggu", cls: "pending" };
  }
  return { label: s, cls: "neutral" };
}

/* =========================================================================
   5. Service Status List Card (Matching Reference A Right Panel 1)
   ========================================================================= */

export type ServiceStatusItem = {
  id: string;
  name: string;
  description: string;
  status: "Online" | "Degraded" | "Offline";
};

export type ServiceStatusCardProps = {
  title?: string;
  viewAllHref?: string;
  services: ServiceStatusItem[];
};

export function ServiceStatusCard({
  title = "Status Layanan",
  viewAllHref = "/governance?view=runtime",
  services,
}: ServiceStatusCardProps) {
  return (
    <article className="alos-dash-card alos-service-card">
      <header className="alos-card-header">
        <h2 className="alos-card-title">{title}</h2>
        {viewAllHref ? (
          <Link className="alos-card-action-link" href={viewAllHref}>
            <span>Lihat Semua</span>
            <ChevronRightMini />
          </Link>
        ) : null}
      </header>

      <ul className="alos-service-list" role="list">
        {services.map((service) => (
          <li className="alos-service-row" key={service.id}>
            <span className="alos-service-dot" aria-hidden="true" />
            <div className="alos-service-info">
              <strong className="alos-service-name">{service.name}</strong>
              <small className="alos-service-desc">{service.description}</small>
            </div>
            <span className={`alos-service-badge ${service.status.toLowerCase()}`}>
              {service.status}
            </span>
          </li>
        ))}
      </ul>
    </article>
  );
}

/* =========================================================================
   6. Daily Priorities Card (Matching Reference A Right Panel 2)
   ========================================================================= */

export type DailyPriorityItem = {
  id: string;
  title: string;
  time: string;
  severity: "critical" | "warning" | "normal";
};

export type DailyPrioritiesCardProps = {
  title?: string;
  viewAllHref?: string;
  items: DailyPriorityItem[];
};

export function DailyPrioritiesCard({
  title = "Prioritas Hari Ini",
  viewAllHref = "/tasks",
  items,
}: DailyPrioritiesCardProps) {
  return (
    <article className="alos-dash-card alos-priority-card">
      <header className="alos-card-header">
        <h2 className="alos-card-title">{title}</h2>
        {viewAllHref ? (
          <Link className="alos-card-action-link" href={viewAllHref}>
            <span>Lihat Semua</span>
            <ChevronRightMini />
          </Link>
        ) : null}
      </header>

      <ul className="alos-priority-list" role="list">
        {items.map((item) => (
          <li className="alos-priority-row" key={item.id}>
            <span className={`alos-priority-dot ${item.severity}`} aria-hidden="true" />
            <span className="alos-priority-title">{item.title}</span>
            <time className="alos-priority-time">{item.time}</time>
          </li>
        ))}
      </ul>
    </article>
  );
}

/* =========================================================================
   7. Team Productivity Donut Card (Matching Reference A Right Panel 3)
   ========================================================================= */

export type ProductivityDonutCardProps = {
  title?: string;
  percentage: number;
  completedTasks: number;
  totalTasks: number;
  trendLabel?: string;
};

export function ProductivityDonutCard({
  title = "Produktivitas Tim",
  percentage = 78,
  completedTasks = 37,
  totalTasks = 48,
  trendLabel = "12% dibanding minggu lalu",
}: ProductivityDonutCardProps) {
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(100, Math.max(0, percentage)) / 100) * circumference;

  return (
    <article className="alos-dash-card alos-productivity-card">
      <header className="alos-card-header">
        <h2 className="alos-card-title">{title}</h2>
        <div className="alos-filter-chip">Minggu Ini ⌄</div>
      </header>

      <div className="alos-productivity-body">
        <div className="alos-donut-container">
          <svg className="alos-donut-svg" height="96" width="96" viewBox="0 0 96 96">
            <circle
              className="alos-donut-track"
              cx="48"
              cy="48"
              fill="none"
              r={radius}
              stroke="#e4ebe6"
              strokeWidth="9"
            />
            <circle
              className="alos-donut-indicator"
              cx="48"
              cy="48"
              fill="none"
              r={radius}
              stroke="#0d6e55"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              strokeWidth="9"
              transform="rotate(-90 48 48)"
            />
          </svg>
          <span className="alos-donut-label">{percentage}%</span>
        </div>

        <div className="alos-productivity-details">
          <strong className="alos-productivity-stat-title">Tugas selesai tepat waktu</strong>
          <span className="alos-productivity-stat-count">
            {completedTasks} dari {totalTasks} tugas
          </span>
          {trendLabel ? (
            <div className="alos-productivity-trend">
              <span className="alos-trend-pill up">↑ {trendLabel}</span>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/* =========================================================================
   Micro SVG Icons
   ========================================================================= */

function CalendarIcon() {
  return (
    <svg fill="none" height="15" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="15">
      <rect height="18" rx="2" width="18" x="3" y="4" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

function ChevronDownMini() {
  return (
    <svg fill="none" height="13" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="13">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function ChevronRightMini() {
  return (
    <svg fill="none" height="14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="14">
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

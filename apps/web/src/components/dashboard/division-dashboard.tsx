"use client";

import { useMemo } from "react";

import {
  ActivityChart,
  DailyPrioritiesCard,
  DashboardHero,
  MetricCard,
  ProductivityDonutCard,
  ServiceStatusCard,
  TasksTable,
  type ActivityDataPoint,
  type DailyPriorityItem,
  type ServiceStatusItem,
  type TableTask,
} from "./dashboard-cards";
import { type DashboardProfile } from "@/lib/dashboard-access";
import { type OperationalDashboard } from "@/lib/operational";

export type DivisionDashboardProps = {
  profile: DashboardProfile;
  operational: OperationalDashboard | null;
};

// Default 14-day activity dataset (matching Reference A)
const defaultActivityData: ActivityDataPoint[] = [
  { date: "27 Agu", requests: 100, completed: 35, incidents: 0 },
  { date: "28 Agu", requests: 110, completed: 38, incidents: 1 },
  { date: "29 Agu", requests: 125, completed: 42, incidents: 0 },
  { date: "30 Agu", requests: 95, completed: 30, incidents: 0 },
  { date: "31 Agu", requests: 115, completed: 40, incidents: 0 },
  { date: "1 Sep", requests: 110, completed: 36, incidents: 1 },
  { date: "2 Sep", requests: 135, completed: 45, incidents: 0 },
  { date: "3 Sep", requests: 130, completed: 48, incidents: 0 },
  { date: "4 Sep", requests: 175, completed: 68, incidents: 2 },
  { date: "5 Sep", requests: 130, completed: 58, incidents: 0 },
  { date: "6 Sep", requests: 105, completed: 45, incidents: 0 },
  { date: "7 Sep", requests: 125, completed: 55, incidents: 1 },
  { date: "8 Sep", requests: 145, completed: 72, incidents: 0 },
  { date: "9 Sep", requests: 120, completed: 60, incidents: 0 },
  { date: "10 Sep", requests: 140, completed: 78, incidents: 0 },
];

const defaultServices: ServiceStatusItem[] = [
  { id: "s1", name: "GENESIS Core", description: "Aplikasi utama", status: "Online" },
  { id: "s2", name: "ARA (AI Assistant)", description: "Layanan AI & data", status: "Online" },
  { id: "s3", name: "File Storage", description: "Penyimpanan dokumen", status: "Online" },
  { id: "s4", name: "Email & Collaboration", description: "Komunikasi internal", status: "Online" },
  { id: "s5", name: "Network & Infrastructure", description: "Infrastruktur jaringan", status: "Online" },
];

const defaultPriorities: DailyPriorityItem[] = [
  { id: "p1", title: "Tindak lanjut insiden performa GENESIS", time: "10.00", severity: "critical" },
  { id: "p2", title: "Review request akses dari Divisi Keuangan", time: "11.30", severity: "warning" },
  { id: "p3", title: "Koordinasi deployment fitur terbaru", time: "14.00", severity: "normal" },
  { id: "p4", title: "Cek status backup harian", time: "15.30", severity: "normal" },
  { id: "p5", title: "Meeting evaluasi infrastruktur Q3", time: "16.00", severity: "normal" },
];

const fallbackTasks: TableTask[] = [
  {
    id: "t1",
    title: "Investigasi performa GENESIS lambat",
    project: "IT Operations",
    priority: "Tinggi",
    status: "Dalam Proses",
    pic: "Budi Santoso",
    date: "10 Sep 2026",
  },
  {
    id: "t2",
    title: "Review akses pengguna baru",
    project: "Governance",
    priority: "Sedang",
    status: "Menunggu",
    pic: "Siti Nurhaliza",
    date: "10 Sep 2026",
  },
  {
    id: "t3",
    title: "Update security patch server",
    project: "Infrastructure",
    priority: "Tinggi",
    status: "Dalam Proses",
    pic: "Ahmad Rizky",
    date: "9 Sep 2026",
  },
  {
    id: "t4",
    title: "Backup data mingguan",
    project: "IT Operations",
    priority: "Sedang",
    status: "Selesai",
    pic: "Dewi Lestari",
    date: "9 Sep 2026",
  },
  {
    id: "t5",
    title: "Analisis log insiden 4582",
    project: "IT Operations",
    priority: "Tinggi",
    status: "Dalam Proses",
    pic: "Budi Santoso",
    date: "8 Sep 2026",
  },
];

export function DivisionDashboard({ profile, operational }: DivisionDashboardProps) {
  const divisionTitle = profile.divisionLabel ?? profile.homeLabel;

  // Map real operational tasks to table format if available
  const tableTasks = useMemo<TableTask[]>(() => {
    if (!operational || operational.tasks.length === 0) {
      return fallbackTasks;
    }
    return operational.tasks.slice(0, 8).map((task) => ({
      id: task.task_id,
      title: task.title,
      project: task.project_name || task.division_code || "Operasional",
      priority: task.priority,
      status: task.status,
      pic: task.assignee_user_id || "Tim Divisi",
      date: new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" }).format(
        new Date(task.updated_at || task.created_at),
      ),
    }));
  }, [operational]);

  // Dynamic metric calculations based on operational data
  const totalTasks = operational?.tasks.length ?? 48;
  const pendingApprovals = operational?.approvals.filter((a) => a.status === "PENDING").length ?? 8;
  const completedTasks = operational?.tasks.filter((t) => t.status === "DONE").length ?? 37;
  const productivityPercent = Math.round(
    totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 78,
  );

  return (
    <section className="alos-dash-content" aria-label={`Dashboard Divisi ${divisionTitle}`}>
      {/* 1. Header Hero */}
      <DashboardHero
        kicker={profile.homeEyebrow.replace("ALOS / ", "")}
        quote="Teknologi untuk Dampak Berkelanjutan"
        subtitle={profile.homeDescription}
        title={`Selamat datang, Tim ${divisionTitle}`}
      />

      {/* 2. Top Metric Cards (4 Cards) */}
      <div className="alos-dash-metrics-grid">
        <MetricCard
          icon={<UptimeIcon />}
          label="System Uptime"
          tone="mint"
          trend={{ direction: "up", label: "+0,1%", context: "dari bulan lalu" }}
          value="99,9%"
        />
        <MetricCard
          icon={<ProjectsIcon />}
          label="Proyek Aktif"
          tone="mint"
          trend={{ direction: "up", label: "+2", context: "dari bulan lalu" }}
          value="12"
        />
        <MetricCard
          icon={<TasksIcon />}
          label="Total Tugas"
          tone="amber"
          trend={{ direction: "up", label: "+6", context: "dibanding minggu lalu" }}
          value={totalTasks}
        />
        <MetricCard
          icon={<ApprovalsIcon />}
          label="Request Approval"
          tone="teal"
          trend={{ direction: "neutral", label: "0", context: "menunggu persetujuan" }}
          value={pendingApprovals}
        />
      </div>

      {/* 3. Main Split Grid (Left ~68%, Right ~32%) */}
      <div className="alos-dash-main-grid">
        {/* Left Column */}
        <div className="alos-dash-col-left">
          <ActivityChart
            data={defaultActivityData}
            dateRangeLabel="27 Ags 2026 – 10 Sep 2026"
            subtitle="Tren beban sistem, permintaan layanan, dan insiden dalam 14 hari terakhir."
            title="Aktivitas Sistem"
          />
          <TasksTable
            subtitle={`Daftar tugas terbaru di divisi ${divisionTitle}.`}
            tasks={tableTasks}
            title="Tugas Terbaru"
            viewAllHref="/tasks"
          />
        </div>

        {/* Right Column */}
        <div className="alos-dash-col-right">
          <ServiceStatusCard
            services={defaultServices}
            title="Status Layanan"
            viewAllHref="/governance?view=runtime"
          />
          <DailyPrioritiesCard
            items={defaultPriorities}
            title="Prioritas Hari Ini"
            viewAllHref="/tasks"
          />
          <ProductivityDonutCard
            completedTasks={completedTasks}
            percentage={productivityPercent}
            title="Produktivitas Tim"
            totalTasks={totalTasks}
            trendLabel="12% dibanding minggu lalu"
          />
        </div>
      </div>
    </section>
  );
}

function UptimeIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <rect height="8" rx="2" width="20" x="2" y="3" />
      <rect height="8" rx="2" width="20" x="2" y="13" />
      <path d="M6 7h.01M6 17h.01" />
    </svg>
  );
}

function ProjectsIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
    </svg>
  );
}

function TasksIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <rect height="18" rx="3" width="18" x="3" y="3" />
      <path d="m8.5 12.5 2.5 2.5 5-5" />
    </svg>
  );
}

function ApprovalsIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

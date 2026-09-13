"use client";

import { useMemo } from "react";

import {
  ActivityChart,
  DailyPrioritiesCard,
  DashboardHero,
  MetricCard,
  ProductivityDonutCard,
  TasksTable,
  type ActivityDataPoint,
  type DailyPriorityItem,
  type TableTask,
} from "./dashboard-cards";
import { type DashboardProfile } from "@/lib/dashboard-access";
import { type OperationalDashboard } from "@/lib/operational";
import { type SessionActor } from "@/lib/governance";

export type MemberDashboardProps = {
  actor: SessionActor;
  profile: DashboardProfile;
  operational: OperationalDashboard | null;
};

const defaultMemberActivity: ActivityDataPoint[] = [
  { date: "27 Agu", requests: 4, completed: 3, incidents: 0 },
  { date: "28 Agu", requests: 6, completed: 5, incidents: 0 },
  { date: "29 Agu", requests: 8, completed: 7, incidents: 0 },
  { date: "30 Agu", requests: 3, completed: 3, incidents: 0 },
  { date: "31 Agu", requests: 5, completed: 4, incidents: 0 },
  { date: "1 Sep", requests: 7, completed: 6, incidents: 0 },
  { date: "2 Sep", requests: 9, completed: 8, incidents: 0 },
  { date: "3 Sep", requests: 6, completed: 5, incidents: 0 },
  { date: "4 Sep", requests: 11, completed: 9, incidents: 0 },
  { date: "5 Sep", requests: 8, completed: 8, incidents: 0 },
  { date: "6 Sep", requests: 5, completed: 5, incidents: 0 },
  { date: "7 Sep", requests: 7, completed: 6, incidents: 0 },
  { date: "8 Sep", requests: 10, completed: 9, incidents: 0 },
  { date: "9 Sep", requests: 8, completed: 7, incidents: 0 },
  { date: "10 Sep", requests: 9, completed: 8, incidents: 0 },
];

const defaultMemberPriorities: DailyPriorityItem[] = [
  { id: "mp1", title: "Lengkapi lampiran evidence laporan mingguan", time: "10.00", severity: "critical" },
  { id: "mp2", title: "Perbarui status milestone proyek digitalisasi", time: "11.30", severity: "warning" },
  { id: "mp3", title: "Review catatan approval vendor cloud", time: "14.00", severity: "normal" },
  { id: "mp4", title: "Diskusi kebutuhan automasi dengan ARA", time: "15.30", severity: "normal" },
];

const fallbackMemberTasks: TableTask[] = [
  {
    id: "mt1",
    title: "Verifikasi kelengkapan dokumen proyek",
    project: "Operasional",
    priority: "Tinggi",
    status: "Dalam Proses",
    pic: "Saya",
    date: "10 Sep 2026",
  },
  {
    id: "mt2",
    title: "Review draft SOP kepatuhan data",
    project: "Governance",
    priority: "Sedang",
    status: "Menunggu",
    pic: "Saya",
    date: "10 Sep 2026",
  },
  {
    id: "mt3",
    title: "Input rekap evidence bulanan",
    project: "Audit",
    priority: "Tinggi",
    status: "Dalam Proses",
    pic: "Saya",
    date: "9 Sep 2026",
  },
  {
    id: "mt4",
    title: "Pemeriksaan checklist keamanan akun",
    project: "Security",
    priority: "Sedang",
    status: "Selesai",
    pic: "Saya",
    date: "8 Sep 2026",
  },
];

export function MemberDashboard({
  actor,
  profile,
  operational,
}: MemberDashboardProps) {
  const userGreeting = profile.homeTitle || "Selamat datang, Ruang Kerja Anda";
  const userSubtitle =
    profile.homeDescription ||
    "Kelola tugas personal, penuhi kebutuhan evidence, dan selesaikan pekerjaan prioritas Anda hari ini.";
  const kicker =
    actor.division_codes.length > 0 ? `MY WORK / ${actor.division_codes[0]}` : "MY WORK";

  const tableTasks = useMemo<TableTask[]>(() => {
    if (!operational || operational.tasks.length === 0) {
      return fallbackMemberTasks;
    }
    return operational.tasks.slice(0, 6).map((task) => ({
      id: task.task_id,
      title: task.title,
      project: task.project_name || task.division_code || "Pekerjaan Saya",
      priority: task.priority,
      status: task.status,
      pic: "Saya",
      date: new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" }).format(
        new Date(task.updated_at || task.created_at),
      ),
    }));
  }, [operational]);

  const totalMyTasks = operational?.tasks.length ?? 8;
  const completedTasks = operational?.tasks.filter((t) => t.status === "DONE").length ?? 6;
  const evidenceNeeded = operational?.tasks.filter((t) => t.evidence_required).length ?? 3;
  const overdueTasks = operational?.tasks.filter((t) => t.status !== "DONE" && t.due_date && new Date(t.due_date) < new Date()).length ?? 0;
  const rate = totalMyTasks > 0 ? Math.round((completedTasks / totalMyTasks) * 100) : 85;

  return (
    <section className="alos-dash-content" aria-label="Ruang Kerja Personal">
      {/* 1. Header Hero */}
      <DashboardHero
        kicker={kicker}
        quote="Membangun Keunggulan dari Setiap Detail"
        subtitle={userSubtitle}
        title={userGreeting}
      />

      {/* 2. Top Metric Cards */}
      <div className="alos-dash-metrics-grid">
        <MetricCard
          icon={<MyTaskIcon />}
          label="Tugas Saya"
          tone="mint"
          trend={{ direction: "up", label: "+2", context: "minggu ini" }}
          value={totalMyTasks}
        />
        <MetricCard
          icon={<DueTodayIcon />}
          label="Jatuh Tempo Hari Ini"
          tone="amber"
          trend={{ direction: "neutral", label: "2", context: "prioritas tinggi" }}
          value={2}
        />
        <MetricCard
          icon={<EvidenceIcon />}
          label="Butuh Evidence"
          tone="teal"
          trend={{ direction: "neutral", label: String(evidenceNeeded), context: "dokumen pendukung" }}
          value={evidenceNeeded}
        />
        <MetricCard
          icon={<OverdueIcon />}
          label="Tugas Overdue"
          tone={overdueTasks > 0 ? "danger" : "mint"}
          trend={{ direction: overdueTasks > 0 ? "down" : "up", label: String(overdueTasks), context: "perlu tindak lanjut" }}
          value={overdueTasks}
        />
      </div>

      {/* 3. Main Split Grid */}
      <div className="alos-dash-main-grid">
        {/* Left Column */}
        <div className="alos-dash-col-left">
          <ActivityChart
            data={defaultMemberActivity}
            dateRangeLabel="14 Hari Terakhir"
            subtitle="Penyelesaian tugas harian dan pemenuhan dokumen kerja Anda."
            title="Aktivitas Kerja Personal"
          />
          <TasksTable
            subtitle="Daftar tugas yang sedang ditugaskan kepada Anda."
            tasks={tableTasks}
            title="Daftar Tugas Saya"
            viewAllHref="/tasks"
          />
        </div>

        {/* Right Column */}
        <div className="alos-dash-col-right">
          <DailyPrioritiesCard
            items={defaultMemberPriorities}
            title="Agenda Hari Ini"
            viewAllHref="/tasks"
          />
          <ProductivityDonutCard
            completedTasks={completedTasks}
            percentage={rate}
            title="Capaian Tugas Anda"
            totalTasks={totalMyTasks}
            trendLabel="Sesuai target target mingguan"
          />
          {/* ARA Suggestion Card */}
          <article className="alos-dash-card alos-ara-help-card">
            <div className="alos-ara-help-icon">✦</div>
            <div className="alos-ara-help-copy">
              <strong>Butuh Bantuan Pekerjaan?</strong>
              <p>Minta ARA membuat ringkasan dokumen, analisis data, atau draft laporan tugas Anda.</p>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}

function MyTaskIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <rect height="18" rx="2" width="18" x="3" y="3" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function DueTodayIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}

function EvidenceIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  );
}

function OverdueIcon() {
  return (
    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
      <path d="m10.29 3.86-8.29 14.5A2 2 0 0 0 3.73 21h16.54a2 2 0 0 0 1.73-2.64L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <path d="M12 9v4M12 17h.01" />
    </svg>
  );
}

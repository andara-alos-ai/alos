"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, getOperationsHealth, getReminders, getWorkQueue } from "@/lib/api";
import { accessibleWorkspacesFor } from "@/lib/catalog";
import { formatDateTime, humanizeCode, relativeDeadline } from "@/lib/format";
import { roleLabels } from "@/lib/navigation";
import type { OperationsHealth, Reminder, WorkItem } from "@/lib/types";

type DashboardData = {
  mine: WorkItem[];
  overdue: WorkItem[];
  reminders: Reminder[];
  health: OperationsHealth | null;
};

const healthRoles = ["DIRECTOR", "AI_EXECUTIVE", "IT_ADMIN", "AUDITOR"];

function safeError(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Ringkasan operasional belum dapat dimuat.";
}

export default function DashboardPage() {
  const { activeProjectId, principal, projects, status, token } = useSession();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!token || !principal) return;
    setLoading(true);
    setError(null);
    try {
      const canViewHealth = principal.roles.some((role) => healthRoles.includes(role));
      const [mine, overdue, reminders, healthResult] = await Promise.all([
        getWorkQueue(token, "mine", activeProjectId),
        getWorkQueue(token, "overdue", activeProjectId),
        getReminders(token, 20),
        canViewHealth
          ? getOperationsHealth(token).then((health) => ({ health })).catch(() => ({ health: null }))
          : Promise.resolve({ health: null }),
      ]);
      setData({ mine, overdue, reminders, health: healthResult.health });
    } catch (dashboardError) {
      setError(safeError(dashboardError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, principal, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadDashboard(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadDashboard, status]);

  if (loading || status !== "authenticated") return <LoadingState label="Menyiapkan ringkasan operasional…" />;
  if (error) return <ErrorState message={error} retry={() => void loadDashboard()} />;
  if (!data || !principal) return null;

  const activeReminders = data.reminders.filter((reminder) => reminder.status !== "DISMISSED");
  const criticalItems = data.mine.filter((item) => item.priority === "CRITICAL").length;
  const pendingEvents = data.health ? data.health.pending_events + data.health.retry_events : null;
  const primaryRole = principal.roles[0];
  const roleLabel = primaryRole ? roleLabels[primaryRole] : "Pengguna ALOS";
  const activeProject = projects.find((project) => project.project_id === activeProjectId);
  const accessibleWorkspaces = accessibleWorkspacesFor(principal.roles, principal.division_codes);
  const canViewGovernance = principal.roles.some((role) => (
    ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "IT_ADMIN", "AUDITOR"].includes(role)
  ));

  return (
    <>
      <header className="dashboardHero">
        <div className="dashboardHeroCopy">
          <p className="heroKicker"><Icon name="agent" /> ALOS · Enterprise Operations</p>
          <h1>Pusat kendali kerja yang terhubung, terukur, dan dapat diaudit.</h1>
          <p>Pantau pekerjaan lintas divisi, approval, evidence, risiko, serta aktivitas digital workforce dalam satu konteks operasional.</p>
          <div className="heroContext">
            <span>{roleLabel}</span>
            <span>{activeProject ? `${activeProject.code} · ${activeProject.name}` : "Semua proyek yang dapat diakses"}</span>
            <span>Working Baseline</span>
          </div>
          <div className="heroActions"><Link className="button heroPrimary" href="/work-queue">Buka antrean kerja</Link><button className="button heroSecondary" onClick={() => void loadDashboard()} type="button">Perbarui data</button></div>
        </div>
        <div className="operatingLayers" aria-label="Empat layer operasi ALOS">
          <p className="eyebrow">Operating model</p>
          <ol>
            <li><span>01</span><div><strong>Direktur Utama</strong><small>Keputusan & arah perusahaan</small></div></li>
            <li><span>02</span><div><strong>AI Executive Layer</strong><small>Brief, KPI, risk & escalation</small></div></li>
            <li><span>03</span><div><strong>Workspace Divisi</strong><small>Enam area operasi perusahaan</small></div></li>
            <li><span>04</span><div><strong>Shared Agent Runtime</strong><small>18 Core Agent & Genesis</small></div></li>
          </ol>
        </div>
      </header>

      <section className="metricGrid" aria-label="Metrik operasional">
        <article className="metricCard"><span className="metricIcon green"><Icon name="work" /></span><div><small>Pekerjaan saya</small><strong>{data.mine.length}</strong><p>{criticalItems} prioritas kritis</p></div></article>
        <article className="metricCard"><span className="metricIcon red"><Icon name="clock" /></span><div><small>Terlambat</small><strong>{data.overdue.length}</strong><p>Perlu perhatian segera</p></div></article>
        <article className="metricCard"><span className="metricIcon amber"><Icon name="bell" /></span><div><small>Pengingat aktif</small><strong>{activeReminders.length}</strong><p>Untuk pengguna atau divisi Anda</p></div></article>
        <article className="metricCard"><span className="metricIcon blue"><Icon name="workflow" /></span><div><small>{pendingEvents === null ? "Core Agent" : "Event integrasi"}</small><strong>{pendingEvents === null ? 18 : pendingEvents}</strong><p>{pendingEvents === null ? "Satu shared runtime" : "Menunggu atau mencoba ulang"}</p></div></article>
      </section>

      <section className="workspaceLauncher">
        <div className="sectionHeading"><div><p className="eyebrow">Workspace sesuai kewenangan</p><h2>Area kerja Anda</h2><p>Business owner tetap pada divisi; IT bertindak sebagai technical custodian platform.</p></div>{canViewGovernance ? <Link className="textLink" href="/governance">Lihat blueprint & keputusan →</Link> : null}</div>
        <div className="workspaceLaunchGrid">
          {accessibleWorkspaces.map((workspace) => (
            <Link className="workspaceLaunchCard" href={`/workspace/${workspace.id}`} key={workspace.id}>
              <span className="workspaceLaunchIcon"><Icon name="briefcase" /></span>
              <div><small>{workspace.code}</small><h3>{workspace.name}</h3><p>{workspace.focus}</p></div>
              <footer><span>{workspace.agents.length ? `${workspace.agents.length} Core Agent` : "Technical custodian"}</span><b>Masuk →</b></footer>
            </Link>
          ))}
        </div>
      </section>

      <div className="dashboardGrid">
        <section className="panel">
          <div className="panelHeader">
            <div><p className="eyebrow">Prioritas pribadi</p><h2>Pekerjaan berikutnya</h2></div>
            <Link className="textLink" href="/work-queue">Buka antrean <span>→</span></Link>
          </div>
          {data.mine.length ? (
            <div className="compactList">
              {data.mine.slice(0, 6).map((item) => (
                <Link className="compactItem" href="/work-queue" key={item.work_item_id}>
                  <span className={`priorityDot ${item.priority.toLowerCase()}`} />
                  <span className="compactCopy"><strong>{item.title}</strong><small>{humanizeCode(item.division_code)} · {humanizeCode(item.work_type)}</small></span>
                  <span className={item.overdue ? "deadline overdue" : "deadline"}>{relativeDeadline(item.due_at)}</span>
                </Link>
              ))}
            </div>
          ) : <EmptyState title="Antrean pribadi bersih" description="Belum ada work item yang ditugaskan kepada Anda pada konteks proyek ini." />}
        </section>

        <aside className="panel sidePanel">
          <div className="panelHeader"><div><p className="eyebrow">Pengingat</p><h2>Deadline & eskalasi</h2></div></div>
          {activeReminders.length ? (
            <div className="reminderList">
              {activeReminders.slice(0, 5).map((reminder) => (
                <article key={reminder.reminder_id}>
                  <span className={`reminderIcon ${reminder.reminder_type.toLowerCase()}`}><Icon name="bell" /></span>
                  <div><strong>{humanizeCode(reminder.reminder_type)}</strong><p>{reminder.division_code ? humanizeCode(reminder.division_code) : "Penugasan personal"}</p><small>{formatDateTime(reminder.scheduled_for)}</small></div>
                </article>
              ))}
            </div>
          ) : <EmptyState title="Tidak ada pengingat aktif" description="Sistem belum menemukan deadline atau eskalasi yang perlu ditampilkan." />}
        </aside>
      </div>

      {data.health ? (
        <section className="systemStrip" aria-label="Kesehatan integrasi">
          <div><span className={data.health.last_worker_status === "COMPLETED" ? "healthDot healthy" : "healthDot"} /><p><strong>Operational worker</strong><small>Terakhir: {formatDateTime(data.health.last_worker_completed_at)}</small></p></div>
          <dl><div><dt>Pending</dt><dd>{data.health.pending_events}</dd></div><div><dt>Retry</dt><dd>{data.health.retry_events}</dd></div><div><dt>Dead letter</dt><dd>{data.health.dead_letter_events}</dd></div></dl>
          <Link className="textLink lightLink" href="/system-health">Detail sistem →</Link>
        </section>
      ) : null}
    </>
  );
}

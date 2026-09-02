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

  if (loading || status !== "authenticated") {
    return <LoadingState label="Menyiapkan ringkasan operasional eksekutif…" />;
  }
  if (error) {
    return <ErrorState message={error} retry={() => void loadDashboard()} />;
  }
  if (!data || !principal) return null;

  const activeReminders = data.reminders.filter((r) => r.status !== "DISMISSED");
  const criticalItems = data.mine.filter((item) => item.priority === "CRITICAL").length;
  const primaryRole = principal.roles[0];
  const roleLabel = primaryRole ? roleLabels[primaryRole] : "Pengguna ALOS";
  const activeProject = projects.find((p) => p.project_id === activeProjectId);
  const accessibleWorkspaces = accessibleWorkspacesFor(principal.roles, principal.division_codes);
  const isDirectorOrExec = principal.roles.some((r) => ["DIRECTOR", "AI_EXECUTIVE"].includes(r));

  return (
    <>
      {/* Top Banner / Executive Hero */}
      <section className="dashboardHero" aria-label="Ringkasan eksekutif">
        <div className="dashboardHeroCopy">
          <p className="heroKicker">
            <Icon name="governance" />
            <span>Sistem Operasi Perusahaan · PT Andara Rejo Makmur</span>
          </p>
          <h1>Pusat Kendali Eksekutif & Operasional Lintas Divisi</h1>
          <p>
            Platform internal terpadu yang menghubungkan pekerjaan harian manusia, approval, evidence,
            audit ledger kriptografis, dan 18 Core Agent dalam satu kendali governance.
          </p>
          <div className="heroContext">
            <span>Peran: {roleLabel}</span>
            <span>
              Proyek: {activeProject ? `${activeProject.code} — ${activeProject.name}` : "Semua Proyek Aktif"}
            </span>
            <span>Audit Chain: Immutable</span>
          </div>
          <div className="heroActions">
            <Link className="button heroPrimary" href="/work-queue">
              Antrean Kerja Saya ({data.mine.length})
            </Link>
            {isDirectorOrExec && (
              <Link className="button heroSecondary" href="/executive">
                AI Executive Brief
              </Link>
            )}
            <button className="button heroSecondary" onClick={() => void loadDashboard()} type="button">
              Perbarui Data
            </button>
          </div>
        </div>

        <div className="operatingLayers">
          <p className="eyebrow light">Prinsip & Arsitektur Operasi</p>
          <ol>
            <li>
              <span>01</span>
              <div>
                <strong>Satu Sistem Internal</strong>
                <small>6 divisi beroperasi dalam satu platform terintegrasi.</small>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Kontrol Governance</strong>
                <small>Setiap mutasi tervalidasi, bertanda tangan kriptografis, dan diaudit.</small>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>AI Executive & Genesis</strong>
                <small>Sintesis eksekutif multi-divisi dan perluasan kapabilitas terkelola.</small>
              </div>
            </li>
          </ol>
        </div>
      </section>

      {/* 4 Metric Stats Cards */}
      <section className="metricGrid" aria-label="Metrik kunci">
        <article className="metricCard">
          <span className={`metricIcon ${criticalItems > 0 ? "red" : "green"}`}>
            <Icon name="work" />
          </span>
          <div>
            <small>Tugas Saya</small>
            <strong>{data.mine.length}</strong>
            <p>{criticalItems > 0 ? `${criticalItems} perlu perhatian kritis` : "Tugas & verifikasi aktif"}</p>
          </div>
        </article>

        <article className="metricCard">
          <span className={`metricIcon ${data.overdue.length ? "red" : "green"}`}>
            <Icon name="clock" />
          </span>
          <div>
            <small>Terlambat (Overdue)</small>
            <strong>{data.overdue.length}</strong>
            <p>{data.overdue.length ? "Melewati batas waktu SLA" : "Tidak ada item terlambat"}</p>
          </div>
        </article>

        <article className="metricCard">
          <span className="metricIcon amber">
            <Icon name="bell" />
          </span>
          <div>
            <small>Pengingat Aktif</small>
            <strong>{activeReminders.length}</strong>
            <p>Jadwal checklist, SLA & eskalasi</p>
          </div>
        </article>

        <article className="metricCard">
          <span className="metricIcon blue">
            <Icon name="workflow" />
          </span>
          <div>
            <small>Event Integrasi & Runtime</small>
            <strong>
              {data.health
                ? data.health.pending_events + data.health.retry_events
                : 18}
            </strong>
            <p>
              {data.health
                ? `${data.health.pending_events} pending · ${data.health.retry_events} retry`
                : "18 Core Agent siap operasi"}
            </p>
          </div>
        </article>
      </section>

      {/* Workspace Quick Launchers */}
      <section className="workspaceLauncher">
        <div className="sectionHeading">
          <div>
            <p className="eyebrow">Akses Cepat Divisi</p>
            <h2>Workspace Operasional</h2>
            <p>Akses langsung ke alur kerja, verifikasi evidence, dan transaksi harian per divisi.</p>
          </div>
          <Link className="textLink" href="/projects">
            Daftar Seluruh Proyek →
          </Link>
        </div>

        <div className="workspaceLaunchGrid">
          {accessibleWorkspaces.map((ws) => (
            <Link className="workspaceLaunchCard" href={ws.operationalHref} key={ws.id}>
              <span className="workspaceLaunchIcon">
                <Icon name="briefcase" />
              </span>
              <div>
                <small>{ws.code}</small>
                <h3>{ws.name}</h3>
                <p>{ws.focus}</p>
              </div>
              <footer>
                <span>{ws.agents.join(", ")}</span>
                <b>Buka <span>→</span></b>
              </footer>
            </Link>
          ))}
        </div>
      </section>

      {/* Bottom Grid: My Priority Tasks & Reminders */}
      <div className="dashboardGrid">
        {/* Left: Priority Tasks */}
        <section className="panel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Prioritas Pribadi</p>
              <h2>Antrean Kerja Berikutnya</h2>
            </div>
            <Link className="textLink" href="/work-queue">
              Buka antrean ({data.mine.length}) <span>→</span>
            </Link>
          </div>

          {data.mine.length === 0 ? (
            <EmptyState
              description="Belum ada work item yang ditugaskan kepada Anda pada konteks proyek ini."
              title="Antrean Tugas Bersih"
            />
          ) : (
            <div className="compactList">
              {data.mine.slice(0, 6).map((item) => (
                <Link className="compactItem" href="/work-queue" key={item.work_item_id}>
                  <span className={`priorityDot ${item.priority.toLowerCase()}`} />
                  <span className="compactCopy">
                    <strong>{item.title}</strong>
                    <small>
                      {humanizeCode(item.division_code)} · {humanizeCode(item.work_type)}
                    </small>
                  </span>
                  <span className={item.overdue ? "deadline overdue" : "deadline"}>
                    <Icon name="clock" />
                    {relativeDeadline(item.due_at)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* Right: Reminders */}
        <aside className="panel sidePanel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Pengingat Operasional</p>
              <h2>Deadline & Eskalasi</h2>
            </div>
          </div>

          {activeReminders.length === 0 ? (
            <EmptyState
              description="Sistem belum menemukan jadwal deadline atau eskalasi yang perlu ditampilkan."
              title="Tidak Ada Pengingat Aktif"
            />
          ) : (
            <div className="reminderList">
              {activeReminders.slice(0, 5).map((reminder) => (
                <article key={reminder.reminder_id}>
                  <span className={`reminderIcon ${reminder.reminder_type.toLowerCase()}`}>
                    <Icon name="bell" />
                  </span>
                  <div>
                    <strong>{humanizeCode(reminder.reminder_type)}</strong>
                    <p>
                      {reminder.division_code
                        ? `Divisi ${humanizeCode(reminder.division_code)}`
                        : "Penugasan Personal"}
                    </p>
                    <small>{formatDateTime(reminder.scheduled_for)}</small>
                  </div>
                </article>
              ))}
            </div>
          )}
        </aside>
      </div>

      {/* Health Indicator Strip */}
      {data.health && (
        <section className="systemStrip" aria-label="Kesehatan integrasi">
          <div>
            <span
              className={
                data.health.last_worker_status === "COMPLETED"
                  ? "healthDot healthy"
                  : "healthDot"
              }
            />
            <p>
              <strong>Operational Worker Aktif</strong>
              <small>Terakhir: {formatDateTime(data.health.last_worker_completed_at)}</small>
            </p>
          </div>
          <dl>
            <div>
              <dt>Pending</dt>
              <dd>{data.health.pending_events}</dd>
            </div>
            <div>
              <dt>Retry</dt>
              <dd>{data.health.retry_events}</dd>
            </div>
            <div>
              <dt>Dead Letter</dt>
              <dd>{data.health.dead_letter_events}</dd>
            </div>
          </dl>
          <Link className="textLink lightLink" href="/system-health">
            Detail Observability →
          </Link>
        </section>
      )}
    </>
  );
}

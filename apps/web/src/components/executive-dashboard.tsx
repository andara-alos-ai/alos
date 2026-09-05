"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  dashboardModules,
  type DashboardMetric,
  type DashboardModuleKey,
} from "@/lib/dashboard-modules";
import {
  getDashboardProfile,
  type DashboardPersona,
  type DashboardProfile,
} from "@/lib/dashboard-access";
import { DocumentCenter } from "@/components/document-center";
import { type SessionActor } from "@/lib/governance";

type ExecutiveDashboardProps = {
  module?: DashboardModuleKey;
};

type IconName = "home" | "divisions" | "projects" | "tasks" | "approvals" | "documents" | "reports" | "findings" | "genesis" | "settings" | "governance" | "logout" | "search" | "bell" | "chevron" | DashboardMetric["icon"];

const navItems: Array<{ href: string; key: DashboardModuleKey; label: string; icon: IconName }> = [
  { href: "/divisions", key: "divisions", label: "Divisi", icon: "divisions" },
  { href: "/projects", key: "projects", label: "Proyek", icon: "projects" },
  { href: "/tasks", key: "tasks", label: "Tugas", icon: "tasks" },
  { href: "/approvals", key: "approvals", label: "Approval", icon: "approvals" },
  { href: "/documents", key: "documents", label: "Dokumen", icon: "documents" },
  { href: "/reports", key: "reports", label: "Laporan", icon: "reports" },
  { href: "/findings", key: "findings", label: "Temuan", icon: "findings" },
];

export function ExecutiveDashboard({ module }: ExecutiveDashboardProps) {
  const router = useRouter();
  const [actor, setActor] = useState<SessionActor | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    async function loadActor() {
      const response = await fetch("/api/v1/whoami", { cache: "no-store", credentials: "same-origin" });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setLoadFailed(true);
        return;
      }
      setActor((await response.json()) as SessionActor);
    }
    void loadActor();
  }, [router]);

  async function logout() {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin", cache: "no-store" });
    router.replace("/login");
    router.refresh();
  }

  const roleLabel = useMemo(() => actor?.roles.join(" · ") || "Sesi ALOS", [actor]);
  const profile = useMemo(
    () => (actor ? getDashboardProfile(actor.roles, actor.division_codes) : null),
    [actor],
  );
  const page = module ? dashboardModules[module] : null;
  const displayRoleLabel = profile?.roleLabel ?? roleLabel;
  const pageTitle = page?.title ?? profile?.homeTitle ?? "Selamat datang di ALOS";
  const pageDescription = page?.description ?? profile?.homeDescription ?? "Satu ruang kerja untuk melihat kondisi perusahaan, keputusan, dan aksi yang telah terdaftar.";
  const searchPlaceholder = page?.searchPlaceholder ?? "Cari proyek, dokumen, divisi, atau tanya GENESIS…";
  const navigation = profile
    ? [{ href: "/", key: "executive" as const, label: profile.homeLabel, icon: "home" as const }, ...navItems]
    : navItems;

  if (!actor && !loadFailed) {
    return <main className="alos-loading-shell">Memuat ALOS…</main>;
  }

  if (loadFailed) {
    return <main className="alos-loading-shell">Sesi ALOS tidak dapat dimuat. Silakan muat ulang halaman.</main>;
  }

  return (
    <main className="alos-app-shell">
      <aside className="alos-sidebar" aria-label="Navigasi utama ALOS">
        <Link className="alos-brand" href="/">
          <Image alt="ALOS" height={64} priority src="/alos-logo-mark.png" width={64} />
          <span><strong>ALOS</strong><small>Andara Leverage Operating System</small><small>PT Andara Rejo Makmur</small></span>
        </Link>

        <nav className="alos-nav">
          {navigation.map((item) => (
            <Link className={item.key === (module ?? "executive") ? "active" : ""} href={item.href} key={item.key}>
              <AppIcon name={item.icon} />{item.label}
            </Link>
          ))}
        </nav>

        <div className="alos-genesis-nav">
          <Link className={module === "genesis" ? "active" : ""} href="/genesis">
            <AppIcon name="genesis" />
            <span className="alos-genesis-label"><strong>GENESIS</strong><small>AI Executive</small></span>
            <AppIcon name="chevron" />
          </Link>
        </div>

        <div className="alos-sidebar-footer">
          <Link className={module === "settings" ? "active" : ""} href="/settings"><AppIcon name="settings" />Pengaturan</Link>
          {profile?.governanceVisible ? <Link href="/governance"><AppIcon name="governance" />Governance &amp; Agent Control</Link> : null}
          <button onClick={() => void logout()} type="button"><AppIcon name="logout" />Keluar</button>
          <p>Building Better Living<br /><em>for a Brighter Tomorrow</em></p>
        </div>
      </aside>

      <section className="alos-main">
        <header className="alos-topbar">
          <label className="alos-search" aria-label="Pencarian ALOS">
            <AppIcon name="search" />
            <input disabled placeholder={searchPlaceholder} />
            <kbd>⌘ K</kbd>
          </label>
          <div className="alos-profile">
            <div className="alos-date"><strong>{formatCurrentDate()}</strong><span>{formatCurrentTime()}</span></div>
            <button aria-label="Notifikasi belum tersedia" className="alos-notifications" disabled type="button"><AppIcon name="bell" /><i /></button>
            <div className="alos-avatar" aria-hidden="true">{roleInitial(displayRoleLabel)}</div>
            <div className="alos-profile-copy"><strong>{profile?.homeLabel ?? "ALOS User"}</strong><span>{displayRoleLabel}</span></div>
            <AppIcon name="chevron" />
          </div>
        </header>

        <section className="alos-hero" aria-label="ALOS The Park Town Sukoharjo">
          <div className="alos-hero-copy">
            <p className="alos-kicker">{module ? `ALOS / ${module.toUpperCase()}` : profile?.homeEyebrow}</p>
            <h1>{pageTitle}</h1>
            <p>{pageDescription}</p>
            {!module && <><span className="alos-hero-rule" /><em>“Keputusan terbaik dimulai dari informasi yang terstruktur dan dapat dipercaya.”</em></>}
          </div>
        </section>

        {module ? <ModuleDashboard actor={actor!} module={module} /> : <ExecutiveDashboardContent profile={profile!} />}
      </section>
    </main>
  );
}

function ExecutiveDashboardContent({ profile }: { profile: DashboardProfile }) {
  const content = homeDashboardContent(profile.persona);
  return (
    <section className="alos-content" aria-label={profile.homeLabel}>
      <DashboardScope profile={profile} />
      <MetricGrid metrics={content.metrics} />
      <div className="alos-dashboard-grid">
        <DataPanel eyebrow={content.primaryEyebrow} title={content.primaryTitle} type="chart" />
        <DataPanel eyebrow={content.secondaryEyebrow} title={content.secondaryTitle} type="donut" />
      </div>
      <div className="alos-dashboard-grid alos-lower-grid">
        <DataPanel eyebrow={content.lowerPrimaryEyebrow} title={content.lowerPrimaryTitle} type="division-grid" />
        <DataPanel eyebrow={content.lowerSecondaryEyebrow} title={content.lowerSecondaryTitle} type="list" />
      </div>
    </section>
  );
}

function DashboardScope({ profile }: { profile: DashboardProfile }) {
  return (
    <article className="alos-role-scope">
      <div>
        <p className="alos-kicker">RUANG KERJA AKTIF</p>
        <h2>{profile.scopeTitle}</h2>
        <p>{profile.scopeDescription}</p>
      </div>
      <dl>
        <div><dt>Peran</dt><dd>{profile.roleLabel}</dd></div>
        <div><dt>Lingkup divisi</dt><dd>{profile.divisionLabel ?? "Lintas fungsi"}</dd></div>
      </dl>
    </article>
  );
}

function homeDashboardContent(persona: DashboardPersona) {
  const shared: Record<DashboardPersona, {
    lowerPrimaryEyebrow: string;
    lowerPrimaryTitle: string;
    lowerSecondaryEyebrow: string;
    lowerSecondaryTitle: string;
    metrics: DashboardMetric[];
    primaryEyebrow: string;
    primaryTitle: string;
    secondaryEyebrow: string;
    secondaryTitle: string;
  }> = {
    director: {
      metrics: [
        { label: "Proyek aktif", hint: "Belum ada proyek terhubung", icon: "folder", tone: "success" },
        { label: "Rata-rata progres", hint: "Menunggu pembaruan proyek", icon: "chart", tone: "warning" },
        { label: "Tugas overdue", hint: "Belum ada tugas terdaftar", icon: "alert", tone: "danger" },
        { label: "Approval pending", hint: "Belum ada permintaan", icon: "file", tone: "info" },
      ],
      primaryEyebrow: "KINERJA PERUSAHAAN",
      primaryTitle: "Tren kinerja",
      secondaryEyebrow: "DISTRIBUSI PROYEK",
      secondaryTitle: "Kesehatan proyek",
      lowerPrimaryEyebrow: "RINGKASAN PER DIVISI",
      lowerPrimaryTitle: "Kesehatan organisasi",
      lowerSecondaryEyebrow: "MEMERLUKAN PERHATIAN",
      lowerSecondaryTitle: "Proyek, isu, dan approval",
    },
    division_lead: {
      metrics: [
        { label: "Prioritas divisi", hint: "Belum ada prioritas terdaftar", icon: "folder", tone: "success" },
        { label: "Progres kerja", hint: "Menunggu pembaruan tim", icon: "chart", tone: "warning" },
        { label: "Tenggat perhatian", hint: "Belum ada tenggat terdaftar", icon: "alert", tone: "danger" },
        { label: "Menunggu keputusan", hint: "Belum ada approval", icon: "file", tone: "info" },
      ],
      primaryEyebrow: "KINERJA DIVISI",
      primaryTitle: "Tren prioritas dan progres",
      secondaryEyebrow: "KESEHATAN KERJA",
      secondaryTitle: "Status pekerjaan divisi",
      lowerPrimaryEyebrow: "TIM & EVIDENCE",
      lowerPrimaryTitle: "Kesiapan proses divisi",
      lowerSecondaryEyebrow: "PERLU TINDAK LANJUT",
      lowerSecondaryTitle: "Tugas, risiko, dan approval",
    },
    member: {
      metrics: [
        { label: "Tugas saya", hint: "Belum ada tugas ditugaskan", icon: "check", tone: "success" },
        { label: "Jatuh tempo", hint: "Belum ada tenggat", icon: "calendar", tone: "warning" },
        { label: "Perlu perhatian", hint: "Belum ada isu", icon: "alert", tone: "danger" },
        { label: "Menunggu review", hint: "Belum ada item", icon: "file", tone: "info" },
      ],
      primaryEyebrow: "PEKERJAAN SAYA",
      primaryTitle: "Prioritas dan penyelesaian",
      secondaryEyebrow: "STATUS TUGAS",
      secondaryTitle: "Kesehatan pekerjaan saya",
      lowerPrimaryEyebrow: "DOKUMEN & EVIDENCE",
      lowerPrimaryTitle: "Sumber yang dapat diakses",
      lowerSecondaryEyebrow: "BUTUH PERHATIAN",
      lowerSecondaryTitle: "Tugas dan approval terkait",
    },
    it_lead: {
      metrics: [
        { label: "Agent terdaftar", hint: "Menunggu release yang disetujui", icon: "folder", tone: "success" },
        { label: "Sumber terverifikasi", hint: "Belum ada sumber baru", icon: "check", tone: "info" },
        { label: "Kontrol menunggu", hint: "Belum ada kontrol baru", icon: "alert", tone: "warning" },
        { label: "UAT & release", hint: "Belum ada aktivitas baru", icon: "file", tone: "violet" },
      ],
      primaryEyebrow: "OPERASI SISTEM",
      primaryTitle: "Kesiapan runtime dan sumber",
      secondaryEyebrow: "GENESIS & AGENT",
      secondaryTitle: "Status kontrak dan release",
      lowerPrimaryEyebrow: "KONTROL TEKNIS",
      lowerPrimaryTitle: "Guardrail dan evidence",
      lowerSecondaryEyebrow: "TINDAK LANJUT",
      lowerSecondaryTitle: "UAT, review, dan release",
    },
    deputy_it: {
      metrics: [
        { label: "Kontrol untuk review", hint: "Belum ada kontrol menunggu", icon: "shield", tone: "warning" },
        { label: "Evidence terverifikasi", hint: "Belum ada evidence baru", icon: "check", tone: "success" },
        { label: "Temuan guardrail", hint: "Belum ada temuan", icon: "alert", tone: "danger" },
        { label: "Audit tersedia", hint: "Menunggu aktivitas", icon: "file", tone: "info" },
      ],
      primaryEyebrow: "KONTROL & EVIDENCE",
      primaryTitle: "Kesiapan kontrol operasi",
      secondaryEyebrow: "HASIL UJI",
      secondaryTitle: "Ringkasan UAT dan guardrail",
      lowerPrimaryEyebrow: "AUDIT LINTAS FUNGSI",
      lowerPrimaryTitle: "Status pemeriksaan",
      lowerSecondaryEyebrow: "MEMERLUKAN REVIEW",
      lowerSecondaryTitle: "Approval dan pengecualian",
    },
  };
  return shared[persona];
}

function ModuleDashboard({ actor, module }: { actor: SessionActor; module: DashboardModuleKey }) {
  if (module === "genesis") return <GenesisDashboard actor={actor} />;
  if (module === "settings") return <SettingsDashboard actor={actor} />;
  if (module === "documents") return <DocumentCenter actor={actor} mode="documents" />;

  const page = dashboardModules[module];
  return (
    <section className="alos-content" aria-label={`${page.title} ALOS`}>
      <div className="alos-section-heading"><div><p className="alos-kicker">ALOS / {module.toUpperCase()}</p><h2>{page.title}</h2></div><span>Menunggu sumber data terverifikasi</span></div>
      <MetricGrid metrics={page.metrics} />
      {module === "tasks" ? <TaskBoard emptyMessage={page.emptyMessage} /> : <OperationalDashboard module={module} />}
    </section>
  );
}

function OperationalDashboard({ module }: { module: Exclude<DashboardModuleKey, "genesis" | "settings" | "tasks"> }) {
  const page = dashboardModules[module];
  const detailTitle = module === "documents" ? "Daftar Dokumen" : module === "reports" ? "Semua Laporan" : module === "approvals" ? "Daftar Approval" : module === "findings" ? "Daftar Temuan" : module === "projects" ? "Daftar Proyek" : "Isu Divisi";
  const primaryType = module === "documents" ? "donut" : module === "findings" ? "severity" : "chart";
  return (
    <>
      <div className="alos-dashboard-grid">
        <DataPanel eyebrow="RINGKASAN" title={page.primaryPanel} type={primaryType} />
        <DataPanel eyebrow="PRIORITAS" title={page.secondaryPanel} type="list" />
      </div>
      <article className="alos-panel alos-table-panel">
        <div className="alos-panel-heading-row"><PanelTitle eyebrow="DATA TERDAFTAR" title={detailTitle} /><button className="alos-outline-button" disabled type="button">Filter</button></div>
        <EmptyMessage text={page.emptyMessage} compact />
      </article>
    </>
  );
}

function TaskBoard({ emptyMessage }: { emptyMessage: string }) {
  const columns = ["To Do", "In Progress", "In Review", "Completed"];
  return (
    <>
      <article className="alos-panel alos-task-board"><PanelTitle eyebrow="TUGAS TERDAFTAR" title="Task Board" /><div className="alos-kanban">{columns.map((column) => <div key={column}><strong>{column}</strong><EmptyMessage compact text="Belum ada tugas" /></div>)}</div></article>
      <div className="alos-dashboard-grid alos-lower-grid"><DataPanel eyebrow="STATUS" title="Task Status Overview" type="donut" /><DataPanel eyebrow="PRIORITAS" title="Tugas Prioritas Tinggi" type="list" /></div>
      <article className="alos-panel alos-table-panel"><PanelTitle eyebrow="DATA TERDAFTAR" title="Daftar Tugas" /><EmptyMessage compact text={emptyMessage} /></article>
    </>
  );
}

function GenesisDashboard({ actor }: { actor: SessionActor }) {
  return <DocumentCenter actor={actor} mode="genesis" />;
}

function SettingsDashboard({ actor }: { actor: SessionActor }) {
  const roleLabel = getDashboardProfile(actor.roles, actor.division_codes).roleLabel;
  return (
    <section className="alos-content" aria-label="Pengaturan ALOS">
      <div className="alos-section-heading"><div><p className="alos-kicker">ALOS / ADMINISTRATION</p><h2>Settings &amp; Administration</h2></div><span>Hak akses aktif</span></div>
      <div className="alos-settings-top"><article className="alos-panel"><PanelTitle eyebrow="AKUN" title="Profile Settings" /><EmptyMessage compact text="Profil personal belum dihubungkan ke direktori pengguna." /></article><article className="alos-panel"><PanelTitle eyebrow="ORGANISASI" title="Company Settings" /><EmptyMessage compact text="Informasi organisasi yang dapat diubah akan muncul sesuai peran Anda." /></article><article className="alos-panel"><PanelTitle eyebrow="AKSES" title="Your Role & Access" /><div className="alos-role-card"><AppIcon name="shield" /><div><strong>{roleLabel}</strong><span>Peran aktif dari sesi staging</span></div></div></article></div>
      <div className="alos-settings-grid"><SettingsCard icon="divisions" title="User & Access Management" text="Daftar pengguna, peran, dan akses akan muncul setelah directory pengguna terintegrasi." /><SettingsCard icon="bell" title="Notification Settings" text="Preferensi notifikasi belum dikonfigurasi untuk akun ini." /><SettingsCard icon="shield" title="Security Settings" text="Kebijakan keamanan dikelola melalui Governance & Agent Control." /><SettingsCard icon="settings" title="System Preferences" text="Preferensi tampilan akan tersedia setelah profil pengguna terdaftar." /></div>
    </section>
  );
}

function SettingsCard({ icon, text, title }: { icon: IconName; text: string; title: string }) {
  return <article className="alos-panel alos-setting-card"><AppIcon name={icon} /><div><h3>{title}</h3><p>{text}</p></div><AppIcon name="chevron" /></article>;
}

function MetricGrid({ metrics }: { metrics: readonly DashboardMetric[] }) {
  return <div className="alos-metric-grid">{metrics.map((metric) => <MetricCard key={metric.label} metric={metric} />)}</div>;
}

function MetricCard({ metric }: { metric: DashboardMetric }) {
  return <article className={`alos-metric alos-metric-${metric.tone}`}><span className="alos-metric-icon"><AppIcon name={metric.icon} /></span><div><strong>—</strong><p>{metric.label}</p><small>{metric.hint}</small></div></article>;
}

function DataPanel({ eyebrow, title, type }: { eyebrow: string; title: string; type: "chart" | "donut" | "division-grid" | "list" | "severity" }) {
  return <article className={`alos-panel alos-panel-${type}`}><PanelTitle eyebrow={eyebrow} title={title} />{type === "chart" && <EmptyChart />}{type === "donut" && <EmptyDonut />}{type === "division-grid" && <EmptyDivisionGrid />}{type === "severity" && <EmptySeverity />}{type === "list" && <EmptyList />}</article>;
}

function PanelTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div className="alos-panel-title"><p className="alos-kicker">{eyebrow}</p><h3>{title}</h3></div>;
}

function EmptyChart() {
  return <div className="alos-empty-chart"><span>Belum ada data tren</span><i /><i /><i /><i /><i /><i /></div>;
}

function EmptyDonut() {
  return <div className="alos-donut-empty"><div><strong>—</strong><span>Data</span></div><p>Status akan tersedia setelah data terhubung.</p></div>;
}

function EmptyDivisionGrid() {
  return <div className="alos-division-empty"><div>Divisi <span>—</span></div><div>Kesehatan <span>—</span></div><div>Progres <span>—</span></div><div>Isu <span>—</span></div><p>Struktur divisi belum terdaftar.</p></div>;
}

function EmptySeverity() {
  return <div className="alos-severity-empty"><i /><i /><i /><i /><p>Belum ada temuan audit.</p></div>;
}

function EmptyList() {
  return <div className="alos-empty-list"><div /><div /><div /><p>Belum ada item untuk ditampilkan.</p></div>;
}

function EmptyMessage({ compact = false, text }: { compact?: boolean; text: string }) {
  return <div className={`alos-empty-message${compact ? " compact" : ""}`}><span aria-hidden="true">○</span><p>{text}</p></div>;
}

function AppIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1Z" /></>,
    divisions: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    projects: <><path d="M4 7h16v13H4zM8 7V4h8v3M8 12h8" /></>,
    tasks: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="m8 9 1.5 1.5L13 7m-5 8 1.5 1.5L13 13m3-4h.01M16 15h.01" /></>,
    approvals: <><path d="m5 12 4 4L19 6" /><path d="M21 12a9 9 0 1 1-3-6.7" /></>,
    documents: <><path d="M6 3h9l3 3v15H6zM9 11h6M9 15h6M9 7h3" /></>,
    reports: <><path d="M4 20V10m5 10V4m6 16v-7m5 7V7" /></>,
    findings: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4m-5-8v4m0 4h.01" /></>,
    genesis: <><path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7Z" /><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7Z" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.06.06-2.1 2.1-.06-.06a1.8 1.8 0 0 0-2-.36 1.8 1.8 0 0 0-1.1 1.65V20.5h-3v-.11A1.8 1.8 0 0 0 10.45 18.7a1.8 1.8 0 0 0-2 .36l-.06.06-2.1-2.1.06-.06a1.8 1.8 0 0 0 .36-2 1.8 1.8 0 0 0-1.65-1.1H5v-3h.11A1.8 1.8 0 0 0 6.8 9.75a1.8 1.8 0 0 0-.36-2l-.06-.06 2.1-2.1.06.06a1.8 1.8 0 0 0 2 .36 1.8 1.8 0 0 0 1.1-1.65V4.25h3v.11a1.8 1.8 0 0 0 1.1 1.65 1.8 1.8 0 0 0 2-.36l.06-.06 2.1 2.1-.06.06a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.65 1.1h.11v3h-.11A1.8 1.8 0 0 0 19.4 15Z" /></>,
    governance: <><path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6Z" /><path d="m8.5 12 2.2 2.2 4.8-4.8" /></>,
    logout: <><path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 22h4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    folder: <><path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></>,
    chart: <><path d="M4 20V10m6 10V4m6 16v-7m4 7V8" /></>,
    alert: <><path d="M12 3 2.5 20h19Z" /><path d="M12 9v4m0 3h.01" /></>,
    file: <><path d="M6 3h9l3 3v15H6zM9 12h6M9 16h6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 10h18" /></>,
    check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    shield: <><path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6Z" /><path d="M12 8v5m0 3h.01" /></>,
    document: <><path d="M6 3h9l3 3v15H6zM9 11h6M9 15h6M9 7h3" /></>,
    report: <><path d="M5 20V4h14v16Z" /><path d="M8 16v-3m4 3V8m4 8v-5" /></>,
  };
  return <svg aria-hidden="true" className="alos-icon" fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="20">{paths[name]}</svg>;
}

function formatCurrentDate() {
  return new Intl.DateTimeFormat("id-ID", { dateStyle: "full" }).format(new Date());
}

function formatCurrentTime() {
  return new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(new Date());
}

function roleInitial(roleLabel: string) {
  return roleLabel.replace(/[^A-Z]/g, "").slice(0, 2) || "A";
}

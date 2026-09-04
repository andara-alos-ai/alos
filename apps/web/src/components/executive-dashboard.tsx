"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { dashboardModules, type DashboardModuleKey } from "@/lib/dashboard-modules";
import { type SessionActor } from "@/lib/governance";

type ExecutiveDashboardProps = {
  module?: DashboardModuleKey;
};

const navItems: Array<{ href: string; key: DashboardModuleKey | "executive"; label: string; symbol: string }> = [
  { href: "/", key: "executive", label: "Executive Dashboard", symbol: "⌂" },
  { href: "/divisions", key: "divisions", label: "Divisi", symbol: "▦" },
  { href: "/projects", key: "projects", label: "Proyek", symbol: "▣" },
  { href: "/tasks", key: "tasks", label: "Tugas", symbol: "☑" },
  { href: "/approvals", key: "approvals", label: "Approval", symbol: "✓" },
  { href: "/documents", key: "documents", label: "Dokumen", symbol: "▤" },
  { href: "/reports", key: "reports", label: "Laporan", symbol: "▥" },
  { href: "/findings", key: "findings", label: "Temuan", symbol: "◉" },
  { href: "/genesis", key: "genesis", label: "Genesis", symbol: "✦" },
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
  const pageTitle = module ? dashboardModules[module].title : "Executive Dashboard";
  const pageDescription = module
    ? dashboardModules[module].description
    : "Ringkasan kondisi perusahaan akan terisi otomatis setelah sumber data operasional terdaftar.";

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
          <Image alt="ALOS" height={48} priority src="/alos-logo-mark.png" width={48} />
          <span><strong>ALOS</strong><small>Andara Leverage Operating System</small><small>PT Andara Rejo Makmur</small></span>
        </Link>

        <nav className="alos-nav">
          {navItems.map((item) => (
            <Link className={item.key === (module ?? "executive") ? "active" : ""} href={item.href} key={item.key}>
              <span aria-hidden="true">{item.symbol}</span>{item.label}
            </Link>
          ))}
        </nav>

        <div className="alos-sidebar-footer">
          <Link href="/governance">Governance &amp; Agent Control</Link>
          <button onClick={() => void logout()} type="button">Keluar</button>
          <p>Building Better Living<br /><em>for a Brighter Tomorrow</em></p>
        </div>
      </aside>

      <section className="alos-main">
        <header className="alos-topbar">
          <label className="alos-search" aria-label="Pencarian ALOS">
            <span aria-hidden="true">⌕</span>
            <input disabled placeholder="Pencarian akan aktif saat data perusahaan terhubung" />
            <kbd>Ctrl K</kbd>
          </label>
          <div className="alos-session"><span>{new Intl.DateTimeFormat("id-ID", { dateStyle: "full" }).format(new Date())}</span><strong>{roleLabel}</strong></div>
        </header>

        <section className="alos-hero" aria-label="Hero ALOS The Park Town Sukoharjo">
          <div className="alos-hero-copy">
            <p className="alos-kicker">ALOS / ANDARA REJO MAKMUR</p>
            <h1>{module ? pageTitle : "Selamat datang di ALOS"}</h1>
            <p>{pageDescription}</p>
          </div>
        </section>

        {module ? <ModuleEmptyState module={module} /> : <ExecutiveEmptyState />}
      </section>
    </main>
  );
}

function ExecutiveEmptyState() {
  return (
    <section className="alos-content" aria-label="Executive Dashboard">
      <div className="alos-section-heading"><div><p className="alos-kicker">RINGKASAN PERUSAHAAN</p><h2>Belum ada data operasional</h2></div><span>Data aman · belum terhubung</span></div>
      <div className="alos-metric-grid">
        <EmptyMetric label="Proyek aktif" />
        <EmptyMetric label="Rata-rata progres" />
        <EmptyMetric label="Tugas overdue" alert />
        <EmptyMetric label="Approval tertunda" />
      </div>
      <div className="alos-dashboard-grid">
        <article className="alos-panel alos-chart-panel"><PanelTitle eyebrow="KINERJA PERUSAHAAN" title="Tren kinerja" /><EmptyChart /></article>
        <article className="alos-panel"><PanelTitle eyebrow="DISTRIBUSI" title="Kesehatan proyek" /><EmptyMessage text="Status proyek akan tampil setelah modul Proyek dan sumber data pertama terdaftar." /></article>
      </div>
      <div className="alos-dashboard-grid alos-lower-grid">
        <article className="alos-panel"><PanelTitle eyebrow="DIVISI" title="Ringkasan per divisi" /><EmptyMessage text="Belum ada divisi operasional yang terhubung ke ALOS." /></article>
        <article className="alos-panel"><PanelTitle eyebrow="PRIORITAS" title="Proyek dan isu yang perlu perhatian" /><EmptyMessage text="Tidak ada proyek, temuan, atau approval yang ditampilkan saat ini." /></article>
      </div>
    </section>
  );
}

function ModuleEmptyState({ module }: { module: DashboardModuleKey }) {
  const title = dashboardModules[module].title;
  return (
    <section className="alos-content" aria-label={`${title} ALOS`}>
      <div className="alos-section-heading"><div><p className="alos-kicker">MODUL {title.toUpperCase()}</p><h2>Siap untuk data terdaftar</h2></div><span>Empty state</span></div>
      <div className="alos-metric-grid">
        <EmptyMetric label={`${title} aktif`} />
        <EmptyMetric label="Perlu perhatian" alert />
        <EmptyMetric label="Menunggu review" />
        <EmptyMetric label="Selesai" />
      </div>
      <article className="alos-panel alos-module-empty">
        <PanelTitle eyebrow="BELUM ADA DATA" title={`${title} belum terhubung`} />
        <EmptyMessage text="Halaman ini sengaja belum menampilkan angka contoh. Data hanya akan muncul setelah struktur, sumber, hak akses, dan audit modul ini disiapkan." />
      </article>
    </section>
  );
}

function EmptyMetric({ label, alert = false }: { label: string; alert?: boolean }) {
  return <article className={`alos-metric${alert ? " alos-metric-alert" : ""}`}><span>{label}</span><strong>—</strong><small>Belum ada data</small></article>;
}

function PanelTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div className="alos-panel-title"><p className="alos-kicker">{eyebrow}</p><h3>{title}</h3></div>;
}

function EmptyChart() {
  return <div className="alos-empty-chart"><span>Data tren akan muncul di sini</span><i /><i /><i /><i /><i /></div>;
}

function EmptyMessage({ text }: { text: string }) {
  return <div className="alos-empty-message"><span aria-hidden="true">○</span><p>{text}</p></div>;
}

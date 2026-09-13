"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ApiError, apiMessage, apiRequest } from "@/lib/api-client";
import { AppShell } from "@/components/layout/app-shell";

import {
  dashboardModules,
  type DashboardMetric,
  type DashboardModuleKey,
} from "@/lib/dashboard-modules";
import {
  getDashboardProfile,
  type DashboardProfile,
} from "@/lib/dashboard-access";
import { DocumentCenter } from "@/components/document-center";
import { AraViews } from "@/components/ara/ara-views";
import { OperationalModuleDashboard } from "@/components/operational-modules";
import {
  DivisionsOverviewDashboard,
  ProjectPortfolioDashboard,
} from "@/components/portfolio-dashboards";
import {
  type ExecutiveDashboardSnapshot,
} from "@/lib/executive-dashboard";
import { type SessionActor } from "@/lib/governance";
import { type OperationalDashboard } from "@/lib/operational";

import { DivisionDashboard } from "@/components/dashboard/division-dashboard";
import { ExecutiveView } from "@/components/dashboard/executive-view";
import { MemberDashboard } from "@/components/dashboard/member-dashboard";

type ExecutiveDashboardProps = {
  module?: DashboardModuleKey;
};

type IconName =
  | "home"
  | "divisions"
  | "projects"
  | "tasks"
  | "approvals"
  | "documents"
  | "reports"
  | "findings"
  | "genesis"
  | "settings"
  | "governance"
  | "logout"
  | "bell"
  | "chevron"
  | DashboardMetric["icon"];

export function ExecutiveDashboard({ module }: ExecutiveDashboardProps) {
  const router = useRouter();
  const [actor, setActor] = useState<SessionActor | null>(null);
  const [executiveData, setExecutiveData] = useState<ExecutiveDashboardSnapshot | null>(null);
  const [executiveLoadFailed, setExecutiveLoadFailed] = useState(false);
  const [operationalData, setOperationalData] = useState<OperationalDashboard | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    async function loadActor() {
      try {
        const currentActor = await apiRequest<SessionActor>("/api/v1/whoami");
        setActor(currentActor);
        if (currentActor.roles.includes("DIRECTOR")) {
          try {
            setExecutiveData(
              await apiRequest<ExecutiveDashboardSnapshot>("/api/v1/executive-dashboard"),
            );
          } catch {
            setExecutiveLoadFailed(true);
          }
        } else {
          try {
            setOperationalData(
              await apiRequest<OperationalDashboard>("/api/v1/dashboard/operational"),
            );
          } catch {
            // Built-in graceful fallbacks exist inside DivisionDashboard & MemberDashboard
          }
        }
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 401) {
          router.replace("/login");
          return;
        }
        setLoadFailed(true);
      }
    }
    void loadActor();
  }, [router]);

  async function logout() {
    await apiRequest<void>("/api/v1/auth/logout", { method: "POST" });
    window.location.assign(new URL("/login", window.location.origin).href);
  }

  const profile = useMemo(
    () => (actor ? getDashboardProfile(actor.roles, actor.division_codes) : null),
    [actor],
  );
  const page = module ? dashboardModules[module] : null;
  const pageTitle = page?.title ?? profile?.homeTitle ?? "Selamat datang di ALOS";
  const pageDescription =
    page?.description ??
    profile?.homeDescription ??
    "Satu ruang kerja untuk melihat kondisi perusahaan, keputusan, dan aksi yang telah terdaftar.";
  const isFocusedWorkspace = module === "documents" || module === "genesis";
  const isCustomHeroModule =
    isFocusedWorkspace ||
    module === "divisions" ||
    module === "projects" ||
    module === "tasks" ||
    module === "approvals" ||
    module === "reports";
  const pendingApprovalCount =
    executiveData?.metrics.find((metric) => metric.key === "pending_approvals")?.value ??
    operationalData?.approvals.filter((a) => a.status === "PENDING").length ??
    0;

  if (!actor && !loadFailed) {
    return (
      <AppShell actor={null} profile={null}>
        <div className="alos-loading-shell">Memuat ALOS…</div>
      </AppShell>
    );
  }

  if (loadFailed && !actor) {
    return (
      <AppShell actor={null} profile={null}>
        <section className="alos-dash-content" style={{ padding: "40px 0" }}>
          <article className="alos-executive-error">
            <strong>Sesi ALOS tidak dapat terhubung ke server</strong>
            <span>
              Pastikan backend ALOS aktif pada port 8000. Anda dapat memuat ulang halaman untuk
              mencoba kembali.
            </span>
          </article>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell
      actor={actor}
      onLogout={() => void logout()}
      pendingApprovalCount={pendingApprovalCount}
      profile={profile}
    >
      {/* Outer Hero for specific non-home module sub-pages */}
      {!isCustomHeroModule && module ? (
        <section className="alos-dash-hero" aria-label={`ALOS ${module.toUpperCase()}`}>
          <div className="alos-dash-hero-copy">
            <p className="alos-dash-kicker">{`ALOS / ${module.toUpperCase()}`}</p>
            <h1 className="alos-dash-title">{pageTitle}</h1>
            <p className="alos-dash-subtitle">{pageDescription}</p>
          </div>
        </section>
      ) : null}

      {module ? (
        <ModuleDashboard actor={actor!} module={module} />
      ) : (
        <ExecutiveDashboardContent
          actor={actor!}
          dashboard={executiveData}
          loadFailed={executiveLoadFailed}
          operational={operationalData}
          profile={profile!}
        />
      )}
    </AppShell>
  );
}

export function ExecutiveDashboardContent({
  actor,
  dashboard,
  loadFailed,
  operational = null,
  profile,
}: {
  actor?: SessionActor;
  dashboard: ExecutiveDashboardSnapshot | null;
  loadFailed: boolean;
  operational?: OperationalDashboard | null;
  profile: DashboardProfile;
}) {
  if (profile.persona === "director") {
    if (loadFailed) {
      return (
        <section className="alos-dash-content">
          <article className="alos-executive-error">
            <strong>Ringkasan eksekutif belum dapat dimuat</strong>
            <span>Data operasional tetap aman. Muat ulang halaman untuk mencoba kembali.</span>
          </article>
        </section>
      );
    }
    if (!dashboard) return <ExecutiveDashboardLoading />;
    return <ExecutiveHomeDashboard dashboard={dashboard} />;
  }

  if (
    profile.persona === "division_lead" ||
    profile.persona === "it_lead" ||
    profile.persona === "deputy_it"
  ) {
    return <DivisionDashboard operational={operational} profile={profile} />;
  }

  return (
    <MemberDashboard
      actor={
        actor ?? {
          user_id: "anonymous",
          organization_id: "",
          roles: ["MEMBER"],
          division_codes: [],
          workspace_ids: [],
          issued_at: new Date().toISOString(),
          expires_at: "",
        }
      }
      operational={operational}
      profile={profile}
    />
  );
}

export function ExecutiveHomeDashboard({ dashboard }: { dashboard: ExecutiveDashboardSnapshot }) {
  return <ExecutiveView dashboard={dashboard} />;
}

function ExecutiveDashboardLoading() {
  return (
    <section className="alos-dash-content" aria-label="Memuat Executive Dashboard">
      <div className="alos-dash-metrics-grid">
        {[0, 1, 2, 3].map((item) => (
          <div
            className="alos-executive-skeleton metric"
            key={item}
            style={{
              height: "100px",
              borderRadius: "14px",
              background: "#eef2eb",
              animation: "pulse 1.5s infinite ease-in-out",
            }}
          />
        ))}
      </div>
      <div className="alos-dash-main-grid">
        <div
          style={{
            height: "360px",
            borderRadius: "14px",
            background: "#eef2eb",
            animation: "pulse 1.5s infinite ease-in-out",
          }}
        />
        <div
          style={{
            height: "360px",
            borderRadius: "14px",
            background: "#eef2eb",
            animation: "pulse 1.5s infinite ease-in-out",
          }}
        />
      </div>
    </section>
  );
}

function ModuleDashboard({ actor, module }: { actor: SessionActor; module: DashboardModuleKey }) {
  if (module === "genesis") return <GenesisDashboard actor={actor} />;
  if (module === "settings") return <SettingsDashboard actor={actor} />;
  if (module === "documents") return <DocumentCenter actor={actor} mode="documents" />;
  if (module === "divisions") return <DivisionsOverviewDashboard />;
  if (module === "projects") return <ProjectPortfolioDashboard actor={actor} />;
  if (
    module === "tasks" ||
    module === "approvals" ||
    module === "findings" ||
    module === "reports"
  ) {
    return <OperationalModuleDashboard actor={actor} module={module} />;
  }
  return null;
}

function GenesisDashboard({ actor }: { actor: SessionActor }) {
  return <AraViews actor={actor} />;
}

function SettingsDashboard({ actor }: { actor: SessionActor }) {
  const roleLabel = getDashboardProfile(actor.roles, actor.division_codes).roleLabel;
  return (
    <section className="alos-dash-content" aria-label="Pengaturan ALOS">
      <div className="alos-card-header">
        <div className="alos-card-header-titles">
          <p className="alos-dash-kicker">ALOS / ADMINISTRATION</p>
          <h2 className="alos-card-title">Settings &amp; Administration</h2>
        </div>
        <span className="alos-trust-badge checked">Hak akses aktif</span>
      </div>

      <div className="alos-settings-top">
        <article className="alos-dash-card">
          <PanelTitle eyebrow="AKUN" title="Sesi aktif" />
          <dl className="review-list">
            <div>
              <dt>User ID</dt>
              <dd className="digest-value">{actor.user_id}</dd>
            </div>
            <div>
              <dt>Berlaku hingga</dt>
              <dd>
                {new Intl.DateTimeFormat("id-ID", {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(actor.expires_at))}
              </dd>
            </div>
          </dl>
        </article>
        <article className="alos-dash-card">
          <PanelTitle eyebrow="ORGANISASI" title="Scope organisasi" />
          <dl className="review-list">
            <div>
              <dt>Organization ID</dt>
              <dd className="digest-value">{actor.organization_id}</dd>
            </div>
            <div>
              <dt>Workspace terakses</dt>
              <dd>{actor.workspace_ids.length}</dd>
            </div>
            <div>
              <dt>Divisi terakses</dt>
              <dd>{actor.division_codes.join(", ") || "Lintas organisasi sesuai policy"}</dd>
            </div>
          </dl>
        </article>
        <article className="alos-dash-card">
          <PanelTitle eyebrow="AKSES" title="Role &amp; control" />
          <div className="alos-role-card">
            <AppIcon name="shield" />
            <div>
              <strong>{roleLabel}</strong>
              <span>{actor.roles.join(" · ") || "Role terdaftar"}</span>
            </div>
          </div>
          <Link className="alos-card-action-link" href="/governance">
            Buka Governance &amp; Agent Control →
          </Link>
        </article>
      </div>

      <div className="alos-settings-grid">
        <article className="alos-dash-card alos-setting-card">
          <AppIcon name="bell" />
          <div>
            <h3>Notifikasi</h3>
            <p>Gunakan ikon notifikasi di bar atas untuk melihat dan menandai inbox Anda.</p>
          </div>
        </article>
        <IntegrationStatusPanel actor={actor} />
      </div>
    </section>
  );
}

type IntegrationStatus = {
  integration_key: string;
  provider: string;
  status: string;
  allowed_hosts: string[];
  updated_at: string;
};

function IntegrationStatusPanel({ actor }: { actor: SessionActor }) {
  const canView = actor.roles.some((role) =>
    ["DIRECTOR", "IT_ADMIN", "AI_ADMIN", "IT_LEAD"].includes(role),
  );
  const [items, setItems] = useState<IntegrationStatus[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canView) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      apiRequest<IntegrationStatus[]>("/api/v1/integrations/status", {
        signal: controller.signal,
      })
        .then(setItems)
        .catch((failure) => {
          if (!controller.signal.aborted) setError(apiMessage(failure));
        });
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [canView]);

  if (!canView) {
    return (
      <article className="alos-dash-card alos-setting-card">
        <AppIcon name="shield" />
        <div>
          <h3>Status integrasi</h3>
          <p>Status konektor hanya tersedia untuk peran observability.</p>
        </div>
      </article>
    );
  }

  return (
    <article className="alos-dash-card alos-setting-card">
      <AppIcon name="settings" />
      <div>
        <h3>Status integrasi</h3>
        {error ? (
          <p>{error}</p>
        ) : items.length ? (
          <ul>
            {items.map((item) => (
              <li key={item.integration_key}>
                {item.integration_key}: <strong>{item.status}</strong> · {item.provider}
              </li>
            ))}
          </ul>
        ) : (
          <p>Belum ada integrasi yang terdaftar untuk organisasi ini.</p>
        )}
      </div>
      <Link aria-label="Buka governance" href="/governance">
        <AppIcon name="chevron" />
      </Link>
    </article>
  );
}

function PanelTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="alos-panel-title">
      <p className="alos-dash-kicker">{eyebrow}</p>
      <h3 className="alos-card-title">{title}</h3>
    </div>
  );
}

function AppIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1Z" />
      </>
    ),
    divisions: (
      <>
        <rect height="16" rx="2" width="16" x="4" y="4" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
    projects: (
      <>
        <path d="M4 7h16v13H4zM8 7V4h8v3M8 12h8" />
      </>
    ),
    tasks: (
      <>
        <rect height="18" rx="2" width="16" x="4" y="3" />
        <path d="m8 9 1.5 1.5L13 7m-5 8 1.5 1.5L13 13m3-4h.01M16 15h.01" />
      </>
    ),
    approvals: (
      <>
        <path d="m5 12 4 4L19 6" />
        <path d="M21 12a9 9 0 1 1-3-6.7" />
      </>
    ),
    documents: (
      <>
        <path d="M6 3h9l3 3v15H6zM9 11h6M9 15h6M9 7h3" />
      </>
    ),
    reports: (
      <>
        <path d="M4 20V10m5 10V4m6 16v-7m5 7V7" />
      </>
    ),
    findings: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4m-5-8v4m0 4h.01" />
      </>
    ),
    genesis: (
      <>
        <path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7Z" />
        <path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7Z" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.06.06-2.1 2.1-.06-.06a1.8 1.8 0 0 0-2-.36 1.8 1.8 0 0 0-1.1 1.65V20.5h-3v-.11A1.8 1.8 0 0 0 10.45 18.7a1.8 1.8 0 0 0-2 .36l-.06.06-2.1-2.1.06-.06a1.8 1.8 0 0 0 .36-2 1.8 1.8 0 0 0-1.65-1.1H5v-3h.11A1.8 1.8 0 0 0 6.8 9.75a1.8 1.8 0 0 0-.36-2l-.06-.06 2.1-2.1.06.06a1.8 1.8 0 0 0 2 .36 1.8 1.8 0 0 0 1.1-1.65V4.25h3v.11a1.8 1.8 0 0 0 1.1 1.65 1.8 1.8 0 0 0 2-.36l.06-.06 2.1 2.1-.06.06a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.65 1.1h.11v3h-.11A1.8 1.8 0 0 0 19.4 15Z" />
      </>
    ),
    governance: (
      <>
        <path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6Z" />
        <path d="m8.5 12 2.2 2.2 4.8-4.8" />
      </>
    ),
    logout: (
      <>
        <path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" />
      </>
    ),
    bell: (
      <>
        <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 22h4" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    folder: (
      <>
        <path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      </>
    ),
    chart: (
      <>
        <path d="M4 20V10m6 10V4m6 16v-7m4 7V8" />
      </>
    ),
    alert: (
      <>
        <path d="M12 3 2.5 20h19Z" />
        <path d="M12 9v4m0 3h.01" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h9l3 3v15H6zM9 12h6M9 16h6" />
      </>
    ),
    calendar: (
      <>
        <rect height="16" rx="2" width="18" x="3" y="5" />
        <path d="M7 3v4m10-4v4M3 10h18" />
      </>
    ),
    check: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12 2.5 2.5L16 9" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    shield: (
      <>
        <path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6Z" />
        <path d="M12 8v5m0 3h.01" />
      </>
    ),
    document: (
      <>
        <path d="M6 3h9l3 3v15H6zM9 11h6M9 15h6M9 7h3" />
      </>
    ),
    report: (
      <>
        <path d="M5 20V4h14v16Z" />
        <path d="M8 16v-3m4 3V8m4 8v-5" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      className="alos-icon"
      fill="none"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width="20"
    >
      {paths[name]}
    </svg>
  );
}

export function formatJakartaDate(value: Date) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "long",
    timeZone: "Asia/Jakarta",
    weekday: "long",
    year: "numeric",
  }).format(value);
}

export function formatJakartaTime(value: Date) {
  const clock = new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    timeZone: "Asia/Jakarta",
  }).format(value);
  return `${clock.replace(":", ".")} WIB`;
}

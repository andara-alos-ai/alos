"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { type DashboardProfile } from "@/lib/dashboard-access";
import { type SessionActor } from "@/lib/governance";

export type SidebarProps = {
  actor: SessionActor | null;
  profile: DashboardProfile | null;
  pendingApprovalCount?: number;
  onLogout?: () => void | Promise<void>;
  activeNavHref?: string;
};

type NavItem = {
  href: string;
  label: string;
  icon: (active: boolean) => ReactNode;
  badge?: number;
  matchPattern: (pathname: string) => boolean;
};

export function Sidebar({
  actor,
  profile,
  pendingApprovalCount = 0,
  onLogout,
  activeNavHref,
}: SidebarProps) {
  const rawPathname = usePathname();
  const pathname = rawPathname ?? "/";

  const homeLabel = profile?.homeLabel ?? "Dashboard";

  const primaryItems: NavItem[] = [
    {
      href: "/",
      label: homeLabel,
      icon: (active) => <HomeIcon active={active} />,
      matchPattern: (path) => path === "/",
    },
    {
      href: "/divisions",
      label: "Divisi",
      icon: (active) => <DivisionsIcon active={active} />,
      matchPattern: (path) => path.startsWith("/divisions"),
    },
    {
      href: "/projects",
      label: "Proyek",
      icon: (active) => <ProjectsIcon active={active} />,
      matchPattern: (path) => path.startsWith("/projects"),
    },
    {
      href: "/tasks",
      label: "Tugas",
      icon: (active) => <TasksIcon active={active} />,
      matchPattern: (path) => path.startsWith("/tasks"),
    },
    {
      href: "/approvals",
      label: "Approval",
      icon: (active) => <ApprovalsIcon active={active} />,
      badge: pendingApprovalCount > 0 ? Math.round(pendingApprovalCount) : undefined,
      matchPattern: (path) => path.startsWith("/approvals"),
    },
    {
      href: "/documents",
      label: "Dokumen",
      icon: (active) => <DocumentsIcon active={active} />,
      matchPattern: (path) => path.startsWith("/documents"),
    },
    {
      href: "/reports",
      label: "Laporan",
      icon: (active) => <ReportsIcon active={active} />,
      matchPattern: (path) => path.startsWith("/reports"),
    },
    {
      href: "/findings",
      label: "Temuan",
      icon: (active) => <FindingsIcon active={active} />,
      matchPattern: (path) => path.startsWith("/findings"),
    },
  ];

  const isAraActive = activeNavHref ? activeNavHref === "/genesis" : pathname.startsWith("/genesis");
  const isGovernanceActive = activeNavHref
    ? activeNavHref === "/governance"
    : pathname.startsWith("/governance") ||
      pathname.startsWith("/agents") ||
      pathname.startsWith("/factory") ||
      pathname.startsWith("/releases") ||
      pathname.startsWith("/validation");
  const isSettingsActive = activeNavHref ? activeNavHref === "/settings" : pathname.startsWith("/settings");

  return (
    <aside className="alos-sidebar-panel" aria-label="Navigasi utama ALOS">
      {/* Brand Header */}
      <Link className="alos-sidebar-brand" href="/" aria-label="ALOS Beranda">
        <div className="alos-brand-logo-wrap">
          <Image
            alt="Logo ALOS"
            className="alos-brand-logo"
            height={44}
            priority
            src="/alos-logo-mark.png"
            width={44}
          />
        </div>
        <div className="alos-brand-meta">
          <span className="alos-brand-title">ALOS</span>
          <span className="alos-brand-sub">Integrated Business Platform</span>
          <span className="alos-brand-org">PT Andara Rejo Makmur</span>
        </div>
      </Link>

      {/* Main Navigation */}
      <nav className="alos-sidebar-nav" aria-label="Menu Utama">
        <ul className="alos-nav-list" role="list">
          {primaryItems.map((item) => {
            const isActive = activeNavHref ? activeNavHref === item.href : item.matchPattern(pathname);
            return (
              <li key={item.href}>
                <Link
                  aria-current={isActive ? "page" : undefined}
                  className={`alos-nav-item ${isActive ? "active" : ""}`}
                  href={item.href}
                >
                  <span className="alos-nav-icon-wrap" aria-hidden="true">
                    {item.icon(isActive)}
                  </span>
                  <span className="alos-nav-label">{item.label}</span>
                  {item.badge ? (
                    <span className="alos-nav-badge" aria-label={`${item.badge} pending`}>
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="alos-sidebar-separator" role="separator" />

        {/* ARA Workspace */}
        <div className="alos-sidebar-section">
          <Link
            aria-current={isAraActive ? "page" : undefined}
            className={`alos-nav-item alos-nav-item-ara ${isAraActive ? "active" : ""}`}
            href="/genesis"
          >
            <span className="alos-nav-icon-wrap alos-ara-icon" aria-hidden="true">
              <AraStarIcon active={isAraActive} />
            </span>
            <span className="alos-nav-label">ARA Workspace</span>
          </Link>
        </div>

        {/* Governance & Agent Control (Restricted to Authorized Roles) */}
        {profile?.governanceVisible ? (
          <>
            <div className="alos-sidebar-separator" role="separator" />
            <div className="alos-sidebar-section">
              <Link
                aria-current={isGovernanceActive ? "page" : undefined}
                className={`alos-nav-item alos-nav-item-gov ${isGovernanceActive ? "active" : ""}`}
                href="/governance"
              >
                <span className="alos-nav-icon-wrap" aria-hidden="true">
                  <GovernanceShieldIcon active={isGovernanceActive} />
                </span>
                <span className="alos-nav-label">Governance &amp; Agent Control</span>
              </Link>
            </div>
          </>
        ) : null}

        <div className="alos-sidebar-separator" role="separator" />

        {/* Settings */}
        <div className="alos-sidebar-section">
          <Link
            aria-current={isSettingsActive ? "page" : undefined}
            className={`alos-nav-item ${isSettingsActive ? "active" : ""}`}
            href="/settings"
          >
            <span className="alos-nav-icon-wrap" aria-hidden="true">
              <SettingsIcon active={isSettingsActive} />
            </span>
            <span className="alos-nav-label">Pengaturan</span>
          </Link>
        </div>
      </nav>

      {/* Sidebar Footer */}
      <footer className="alos-sidebar-footer-area">
        {actor ? (
          <div className="alos-sidebar-user-card">
            <div className="alos-sidebar-user-avatar" aria-hidden="true">
              {roleInitials(profile?.roleLabel ?? "ALOS")}
            </div>
            <div className="alos-sidebar-user-info">
              <strong className="alos-sidebar-user-name">
                {profile?.roleLabel ?? "Pengguna ALOS"}
              </strong>
              <small className="alos-sidebar-user-role">
                {profile?.divisionLabel ?? actor.roles[0] ?? "PT Andara"}
              </small>
            </div>
            {onLogout ? (
              <button
                aria-label="Keluar dari akun ALOS"
                className="alos-sidebar-logout-btn"
                onClick={() => void onLogout()}
                title="Keluar"
                type="button"
              >
                <LogoutIcon />
              </button>
            ) : null}
          </div>
        ) : null}

        {/* Brand Inspiration Tagline */}
        <div className="alos-sidebar-tagline-wrap">
          <svg
            aria-hidden="true"
            className="alos-sidebar-wave-art"
            fill="none"
            preserveAspectRatio="none"
            viewBox="0 0 200 40"
          >
            <path
              d="M0 35 C50 15, 120 45, 200 20"
              stroke="#c99d4c"
              strokeOpacity="0.32"
              strokeWidth="1.2"
            />
            <path
              d="M0 25 C60 5, 140 38, 200 12"
              stroke="#c99d4c"
              strokeOpacity="0.18"
              strokeWidth="0.8"
            />
          </svg>
          <p className="alos-sidebar-tagline">
            <em>Bersama AI,</em>
            <span>Mendorong Dampak Nyata</span>
          </p>
        </div>
      </footer>
    </aside>
  );
}

function roleInitials(roleLabel: string): string {
  const parts = roleLabel.replace(/[^A-Za-z0-9\s]/g, "").trim().split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return roleLabel.slice(0, 2).toUpperCase() || "AL";
}

/* =========================================================================
   Semantic SVG Icons (Calm, crisp enterprise strokes matching visual anchor)
   ========================================================================= */

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <path d="M3 10.5 12 3l9 7.5v9.5a1 1 0 0 1-1 1h-4.5a1 1 0 0 1-1-1v-5h-5v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function DivisionsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <rect height="18" rx="2" width="18" x="3" y="3" />
      <path d="M3 9h18M9 21V9M15 21V9" />
    </svg>
  );
}

function ProjectsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <rect height="14" rx="2" width="20" x="2" y="7" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2M2 12h20" />
    </svg>
  );
}

function TasksIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <rect height="18" rx="2" width="18" x="3" y="3" />
      <path d="m8.5 12 2.5 2.5 5-5" />
    </svg>
  );
}

function ApprovalsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 5-5" />
    </svg>
  );
}

function DocumentsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  );
}

function ReportsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <path d="M18 20V10M12 20V4M6 20v-6" />
    </svg>
  );
}

function FindingsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4.35-4.35" />
      <circle cx="11" cy="11" fill="currentColor" r="1.5" stroke="none" />
    </svg>
  );
}

function AraStarIcon({ active }: { active: boolean }) {
  return (
    <svg
      fill="currentColor"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={active ? "1" : "0.5"}
      viewBox="0 0 24 24"
      width="20"
    >
      {/* 4-point golden star */}
      <path d="M12 2c.8 4.2 3.8 7.2 8 8-4.2.8-7.2 3.8-8 8-.8-4.2-3.8-7.2-8-8 4.2-.8 7.2-3.8 8-8z" />
      <path d="M19 16c.3 1.5 1.5 2.7 3 3-1.5.3-2.7 1.5-3 3-.3-1.5-1.5-2.7-3-3 1.5-.3 2.7-1.5 3-3z" opacity="0.75" />
    </svg>
  );
}

function GovernanceShieldIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function SettingsIcon({ active }: { active: boolean }) {
  return (
    <svg fill="none" height="19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={active ? "2.2" : "1.8"} viewBox="0 0 24 24" width="19">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.06.06-2.1 2.1-.06-.06a1.8 1.8 0 0 0-2-.36 1.8 1.8 0 0 0-1.1 1.65V20.5h-3v-.11A1.8 1.8 0 0 0 10.45 18.7a1.8 1.8 0 0 0-2 .36l-.06.06-2.1-2.1.06-.06a1.8 1.8 0 0 0 .36-2 1.8 1.8 0 0 0-1.65-1.1H5v-3h.11A1.8 1.8 0 0 0 6.8 9.75a1.8 1.8 0 0 0-.36-2l-.06-.06 2.1-2.1.06.06a1.8 1.8 0 0 0 2 .36 1.8 1.8 0 0 0 1.1-1.65V4.25h3v.11a1.8 1.8 0 0 0 1.1 1.65 1.8 1.8 0 0 0 2-.36l.06-.06 2.1 2.1-.06.06a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.65 1.1h.11v3h-.11A1.8 1.8 0 0 0 19.4 15z" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg fill="none" height="16" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="16">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

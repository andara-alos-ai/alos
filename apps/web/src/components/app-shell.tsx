"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { workspaces } from "@/lib/catalog";
import { humanizeCode } from "@/lib/format";
import {
  primaryNavigation,
  roleLabels,
  systemNavigation,
  type NavigationItem,
  visibleNavigation,
} from "@/lib/navigation";
import { sessionInitials } from "@/lib/session";
import type { Role } from "@/lib/types";

import { Icon } from "./icons";
import { useSession } from "./session-provider";

const roleWorkspace: Partial<Record<Role, string>> = {
  SALES: "sales-marketing",
  FINANCE: "finance",
  PROPERTY: "property",
  HR: "hr",
  LEGAL: "legal",
  IT_ADMIN: "it",
};

const divisionWorkspace: Record<string, string> = {
  FINANCE: "finance",
  SALES_MARKETING: "sales-marketing",
  PROPERTY: "property",
  HR: "hr",
  LEGAL: "legal",
  IT: "it",
};

function NavigationGroup({
  items,
  pathname,
  onNavigate,
}: {
  items: NavigationItem[];
  pathname: string;
  onNavigate: () => void;
}) {
  return (
    <nav className="navGroup" aria-label="Navigasi aplikasi">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={active ? "navLink active" : "navLink"}
            href={item.href}
            key={item.href}
            onClick={onNavigate}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useSession();
  const [mobileOpen, setMobileOpen] = useState(false);
  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (session.status === "anonymous" && !isLoginPage) router.replace("/login");
    if (session.status === "authenticated" && isLoginPage) router.replace("/");
  }, [isLoginPage, router, session.status]);

  const accessibleWorkspaces = useMemo(() => {
    const principal = session.principal;
    if (!principal) return [];
    if (principal.roles.some((role) => ["DIRECTOR", "AI_EXECUTIVE", "AUDITOR"].includes(role))) {
      return workspaces;
    }
    const workspaceIds = new Set<string>();
    principal.roles.forEach((role) => {
      const workspace = roleWorkspace[role];
      if (workspace) workspaceIds.add(workspace);
    });
    principal.division_codes.forEach((division) => {
      const workspace = divisionWorkspace[division];
      if (workspace) workspaceIds.add(workspace);
    });
    return workspaces.filter((workspace) => workspaceIds.has(workspace.id));
  }, [session.principal]);

  if (isLoginPage) return <>{children}</>;

  if (session.status !== "authenticated" || !session.principal) {
    return (
      <div className="sessionGate" aria-live="polite">
        <span className="spinner" />
        <strong>Memverifikasi akses ALOS…</strong>
      </div>
    );
  }

  const principal = session.principal;
  const primaryRole = principal.roles[0];
  const mainItems = visibleNavigation(primaryNavigation, principal.roles);
  const systemItems = visibleNavigation(systemNavigation, principal.roles);
  const roleLabel = primaryRole ? roleLabels[primaryRole] : "Pengguna ALOS";
  const divisionLabel = principal.division_codes.length
    ? principal.division_codes.map(humanizeCode).join(", ")
    : "Lintas divisi";

  return (
    <div className="appFrame">
      <button
        aria-label="Tutup navigasi"
        className={mobileOpen ? "mobileBackdrop visible" : "mobileBackdrop"}
        onClick={() => setMobileOpen(false)}
        type="button"
      />
      <aside className={mobileOpen ? "sidebar open" : "sidebar"}>
        <div className="brandRow">
          <Link className="brand" href="/" onClick={() => setMobileOpen(false)}>
            <span className="brandMark">A</span>
            <span className="brandText"><strong>ALOS</strong><small>Internal v1</small></span>
          </Link>
          <button
            aria-label="Tutup menu"
            className="iconButton sidebarClose"
            onClick={() => setMobileOpen(false)}
            type="button"
          >
            <Icon name="close" />
          </button>
        </div>

        <div className="sidebarScroll">
          <p className="navLabel">Operasional</p>
          <NavigationGroup items={mainItems} pathname={pathname} onNavigate={() => setMobileOpen(false)} />

          {accessibleWorkspaces.length ? (
            <>
              <p className="navLabel">Workspace divisi</p>
              <nav className="navGroup" aria-label="Workspace divisi">
                {accessibleWorkspaces.map((workspace) => {
                  const href = `/workspace/${workspace.id}`;
                  const active = pathname.startsWith(href);
                  return (
                    <Link
                      aria-current={active ? "page" : undefined}
                      className={active ? "navLink active" : "navLink"}
                      href={href}
                      key={workspace.id}
                      onClick={() => setMobileOpen(false)}
                    >
                      <Icon name="briefcase" />
                      <span>{workspace.name}</span>
                    </Link>
                  );
                })}
              </nav>
            </>
          ) : null}

          {systemItems.length ? (
            <>
              <p className="navLabel">Platform</p>
              <NavigationGroup items={systemItems} pathname={pathname} onNavigate={() => setMobileOpen(false)} />
            </>
          ) : null}
        </div>

        <div className="environmentBadge"><span /> Pilot Internal · Data Sintetis</div>
      </aside>

      <div className="appColumn">
        <header className="topbar">
          <button
            aria-label="Buka navigasi"
            className="iconButton menuButton"
            onClick={() => setMobileOpen(true)}
            type="button"
          >
            <Icon name="menu" />
          </button>
          <div className="projectContext">
            <label htmlFor="active-project">Konteks proyek</label>
            <select
              id="active-project"
              onChange={(event) => session.setActiveProjectId(event.target.value || null)}
              value={session.activeProjectId || ""}
            >
              <option value="">Semua proyek yang dapat diakses</option>
              {session.projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.code} · {project.name}
                </option>
              ))}
            </select>
          </div>
          <div className="topbarActions">
            <Link className="iconButton" href="/work-queue" aria-label="Lihat pengingat">
              <Icon name="bell" />
            </Link>
            <details className="profileMenu">
              <summary>
                <span className="avatar">{sessionInitials(principal)}</span>
                <span className="profileCopy"><strong>{roleLabel}</strong><small>{divisionLabel}</small></span>
                <Icon name="chevron" />
              </summary>
              <div className="profileDropdown">
                <p><strong>{roleLabel}</strong><span>{divisionLabel}</span></p>
                <button className="logoutButton" onClick={session.logout} type="button">
                  <Icon name="logout" /> Keluar dari sesi
                </button>
              </div>
            </details>
          </div>
        </header>
        {session.error ? <div className="sessionNotice" role="status">{session.error}</div> : null}
        <main className="content" id="main-content">{children}</main>
      </div>
    </div>
  );
}

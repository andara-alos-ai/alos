"use client";

import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { type DashboardProfile } from "@/lib/dashboard-access";
import { type SessionActor } from "@/lib/governance";

export type AppShellProps = {
  actor: SessionActor | null;
  profile: DashboardProfile | null;
  pendingApprovalCount?: number;
  onLogout?: () => void | Promise<void>;
  onSearch?: (query: string) => void;
  searchPlaceholder?: string;
  variant?: "default" | "workspace" | "flush";
  contentClassName?: string;
  activeNavHref?: string;
  children: ReactNode;
};

export function AppShell({
  actor,
  profile,
  pendingApprovalCount = 0,
  onLogout,
  onSearch,
  searchPlaceholder,
  variant = "default",
  contentClassName,
  activeNavHref,
  children,
}: AppShellProps) {
  return (
    <div className="alos-shell-root">
      {/* Skip Link for Accessibility */}
      <a className="alos-skip-link" href="#alos-main-content">
        Lewati ke konten utama
      </a>

      {/* Left Sidebar */}
      <Sidebar
        activeNavHref={activeNavHref}
        actor={actor}
        onLogout={onLogout}
        pendingApprovalCount={pendingApprovalCount}
        profile={profile}
      />

      {/* Main Right Area */}
      <div className="alos-main-viewport">
        {/* Topbar */}
        <Topbar
          actor={actor}
          onSearch={onSearch}
          profile={profile}
          searchPlaceholder={searchPlaceholder}
        />

        {/* Dynamic Page Content */}
        <main
          className={`alos-page-content ${variant === "workspace" ? "alos-page-content-workspace" : variant === "flush" ? "alos-page-content-flush" : ""} ${contentClassName ?? ""}`.trim()}
          id="alos-main-content"
        >
          {children}
        </main>
      </div>
    </div>
  );
}

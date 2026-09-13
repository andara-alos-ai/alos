"use client";

import { useEffect, useState } from "react";

import { NotificationCenter } from "@/components/global-command";
import { type DashboardProfile } from "@/lib/dashboard-access";
import { type SessionActor } from "@/lib/governance";

export type TopbarProps = {
  actor?: SessionActor | null;
  profile: DashboardProfile | null;
  onSearch?: (query: string) => void;
  searchPlaceholder?: string;
};

export function Topbar({
  profile,
  onSearch,
  searchPlaceholder = "Cari dokumen, proyek, tugas, atau tanyakan apa saja ke ARA…",
}: TopbarProps) {
  const [searchValue, setSearchValue] = useState("");

  const profileTitle = profile?.homeLabel ?? "IT Operations";
  const profileSub = profile?.roleLabel ?? "IT Lead";

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (onSearch) {
      onSearch(searchValue);
    }
  }

  return (
    <header className="alos-topbar-panel" role="banner">
      {/* Global Search */}
      <form className="alos-topbar-search-form" onSubmit={handleSearchSubmit} role="search">
        <label className="sr-only" htmlFor="alos-global-search">
          Pencarian Global ALOS
        </label>
        <span className="alos-search-icon-wrap" aria-hidden="true">
          <SearchIcon />
        </span>
        <input
          autoComplete="off"
          className="alos-topbar-search-input"
          id="alos-global-search"
          name="q"
          onChange={(e) => setSearchValue(e.target.value)}
          placeholder={searchPlaceholder}
          type="search"
          value={searchValue}
        />
        <div className="alos-search-kbd-shortcut" aria-hidden="true">
          <kbd>Ctrl</kbd>
          <kbd>K</kbd>
        </div>
      </form>

      {/* Topbar Right Section */}
      <div className="alos-topbar-right">
        {/* Live Jakarta Clock */}
        <TopLiveClock />

        <div className="alos-topbar-divider" role="separator" />

        {/* Notification Center */}
        <div className="alos-topbar-notif-wrap">
          <NotificationCenter />
        </div>

        <div className="alos-topbar-divider" role="separator" />

        {/* User Profile Lockup */}
        <div
          aria-label={`Profil pengguna: ${profileTitle}, ${profileSub}`}
          className="alos-topbar-profile"
          tabIndex={0}
        >
          <div className="alos-topbar-avatar" aria-hidden="true">
            {roleInitials(profileTitle)}
          </div>
          <div className="alos-topbar-profile-copy">
            <strong className="alos-topbar-user-name">{profileTitle}</strong>
            <span className="alos-topbar-user-role">{profileSub}</span>
          </div>
          <span className="alos-topbar-chevron" aria-hidden="true">
            <ChevronDownIcon />
          </span>
        </div>
      </div>
    </header>
  );
}

function TopLiveClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setNow(new Date());
    }, 0);
    const interval = window.setInterval(() => {
      setNow(new Date());
    }, 30_000);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(interval);
    };
  }, []);

  return (
    <time className="alos-topbar-clock" dateTime={now?.toISOString()}>
      <span className="alos-clock-date">
        {now ? formatJakartaDate(now) : "Waktu Indonesia Barat"}
      </span>
      <span className="alos-clock-time">
        {now ? formatJakartaTime(now) : "--.-- WIB"}
      </span>
    </time>
  );
}

export function formatJakartaDate(value: Date): string {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "long",
    timeZone: "Asia/Jakarta",
    weekday: "long",
    year: "numeric",
  }).format(value);
}

export function formatJakartaTime(value: Date): string {
  const clock = new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    timeZone: "Asia/Jakarta",
  }).format(value);
  return `${clock.replace(":", ".")} WIB`;
}

function roleInitials(name: string): string {
  const parts = name.replace(/[^A-Za-z0-9\s]/g, "").trim().split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase() || "AL";
}

function SearchIcon() {
  return (
    <svg fill="none" height="18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="18">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg fill="none" height="14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="14">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

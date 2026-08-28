import Link from "next/link";
import type { ReactNode } from "react";

const navigation = [
  ["Ringkasan", "/"],
  ["Antrean Kerja", "/work-queue"],
  ["Persetujuan", "/approvals"],
  ["Agent Registry", "/agents"],
  ["Workflow", "/workflows"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">A</span>
          <div><strong>ALOS</strong><small>Internal v1</small></div>
        </div>
        <nav aria-label="Navigasi utama">
          {navigation.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
        </nav>
        <div className="environment"><span /> Pilot Internal · Data Sintetis</div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

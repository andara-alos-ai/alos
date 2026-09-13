import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppShell } from "./app-shell";
import { Sidebar } from "./sidebar";
import { Topbar, formatJakartaDate, formatJakartaTime } from "./topbar";
import { type DashboardProfile } from "@/lib/dashboard-access";
import { type SessionActor } from "@/lib/governance";

const mockActor: SessionActor = {
  user_id: "user-test-01",
  organization_id: "org-andara",
  roles: ["IT_LEAD"],
  division_codes: ["IT"],
  workspace_ids: ["ws-default"],
  issued_at: "2026-09-10T08:00:00Z",
  expires_at: "2026-12-31T23:59:59Z",
};

const mockDirectorProfile: DashboardProfile = {
  persona: "director",
  homeDescription: "Ringkasan eksekutif perusahaan.",
  homeEyebrow: "ALOS / EXECUTIVE VIEW",
  homeLabel: "Executive Dashboard",
  homeTitle: "Executive Dashboard",
  scopeDescription: "Ruang keputusan Director",
  scopeTitle: "Ruang keputusan Director",
  divisionLabel: null,
  governanceVisible: true,
  roleLabel: "Direktur Utama",
};

const mockMemberProfile: DashboardProfile = {
  persona: "member",
  homeDescription: "Ruang kerja personal anggota.",
  homeEyebrow: "ALOS / MY WORK",
  homeLabel: "My Work",
  homeTitle: "My Work",
  scopeDescription: "Ruang kerja anggota",
  scopeTitle: "Ruang kerja anggota",
  divisionLabel: "Keuangan",
  governanceVisible: false,
  roleLabel: "Anggota Divisi",
};

describe("AppShell Component Suite", () => {
  it("renders global shell layout with skip link, sidebar, topbar, and child content", () => {
    const html = renderToStaticMarkup(
      <AppShell
        actor={mockActor}
        profile={mockDirectorProfile}
      >
        <div data-testid="test-content">Selamat Datang di ALOS</div>
      </AppShell>,
    );

    expect(html).toContain("Lewati ke konten utama");
    expect(html).toContain("ALOS");
    expect(html).toContain("Integrated Business Platform");
    expect(html).toContain("PT Andara Rejo Makmur");
    expect(html).toContain("Selamat Datang di ALOS");
    expect(html).toContain("alos-main-content");
  });

  it("renders all canonical primary navigation links", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        actor={mockActor}
        profile={mockDirectorProfile}
      />,
    );

    expect(html).toContain("Divisi");
    expect(html).toContain("Proyek");
    expect(html).toContain("Tugas");
    expect(html).toContain("Approval");
    expect(html).toContain("Dokumen");
    expect(html).toContain("Laporan");
    expect(html).toContain("Temuan");
    expect(html).toContain("ARA Workspace");
    expect(html).toContain("Pengaturan");
    expect(html).toContain("Bersama AI,");
    expect(html).toContain("Mendorong Dampak Nyata");
  });

  it("strictly hides Governance & Agent Control for normal division member", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        actor={{ ...mockActor, roles: ["MEMBER"] }}
        profile={mockMemberProfile}
      />,
    );

    expect(html).not.toContain("Governance &amp; Agent Control");
    expect(html).not.toContain("/governance");
  });

  it("displays Governance & Agent Control for authorized director and IT leadership", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        actor={mockActor}
        profile={mockDirectorProfile}
      />,
    );

    expect(html).toContain("Governance &amp; Agent Control");
    expect(html).toContain("/governance");
  });

  it("displays pending approvals badge count when items require attention", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        actor={mockActor}
        pendingApprovalCount={8}
        profile={mockDirectorProfile}
      />,
    );

    expect(html).toContain('class="alos-nav-badge"');
    expect(html).toContain("8");
  });

  it("renders Topbar with global search shortcut, live clock, and profile avatar", () => {
    const html = renderToStaticMarkup(
      <Topbar
        profile={mockDirectorProfile}
      />,
    );

    expect(html).toContain("Pencarian Global ALOS");
    expect(html).toContain("Cari dokumen, proyek, tugas, atau tanyakan apa saja ke ARA…");
    expect(html).toContain("Ctrl");
    expect(html).toContain("K");
    expect(html).toContain("Executive Dashboard");
    expect(html).toContain("Direktur Utama");
  });

  it("formats Asia/Jakarta date and clock correctly", () => {
    const instant = new Date("2026-09-10T08:00:00Z"); // 15.00 WIB
    expect(formatJakartaDate(instant)).toBe("Kamis, 10 September 2026");
    expect(formatJakartaTime(instant)).toBe("15.00 WIB");
  });
});

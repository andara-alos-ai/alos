import { describe, expect, it } from "vitest";

import { primaryNavigation, systemNavigation, visibleNavigation } from "./navigation";

describe("navigasi berbasis peran", () => {
  it("memberi pengguna sales menu operasional tanpa kontrol platform", () => {
    const primary = visibleNavigation(primaryNavigation, ["SALES"], ["SALES_MARKETING"]);
    const system = visibleNavigation(systemNavigation, ["SALES"]);

    expect(primary.map((item) => item.href)).toEqual([
      "/",
      "/work-queue",
      "/sales",
      "/documents",
      "/risks",
      "/uat",
    ]);
    expect(system).toHaveLength(0);
  });

  it("membatasi kepala divisi ke workspace transaksinya", () => {
    const finance = visibleNavigation(primaryNavigation, ["DIVISION_HEAD"], ["FINANCE"]);

    expect(finance.some((item) => item.href === "/finance")).toBe(true);
    expect(finance.some((item) => item.href === "/sales")).toBe(false);
    expect(finance.some((item) => item.href === "/hr")).toBe(true);
  });

  it("memberi setiap operator domain hanya transaksi divisinya", () => {
    const property = visibleNavigation(primaryNavigation, ["PROPERTY"], ["PROPERTY"]);
    const legal = visibleNavigation(primaryNavigation, ["LEGAL"], ["LEGAL"]);
    const hr = visibleNavigation(primaryNavigation, ["HR"], ["HR"]);

    expect(property.map((item) => item.href)).toContain("/property");
    expect(property.map((item) => item.href)).not.toContain("/legal");
    expect(legal.map((item) => item.href)).toContain("/legal");
    expect(hr.map((item) => item.href)).toContain("/hr");
  });

  it("memberi IT akses observability tanpa menu persetujuan bisnis", () => {
    const primary = visibleNavigation(primaryNavigation, ["IT_ADMIN"]);
    const system = visibleNavigation(systemNavigation, ["IT_ADMIN"]);

    expect(primary.some((item) => item.href === "/approvals")).toBe(false);
    expect(system.map((item) => item.href)).toContain("/system-health");
    expect(system.map((item) => item.href)).toContain("/users");
    expect(system.map((item) => item.href)).toContain("/projects");
  });

  it("memberi direktur akses governance dan monitoring", () => {
    expect(visibleNavigation(primaryNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/approvals");
    expect(visibleNavigation(systemNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/agents");
    expect(visibleNavigation(systemNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/users");
    expect(visibleNavigation(systemNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/projects");
  });
});

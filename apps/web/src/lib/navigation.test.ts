import { describe, expect, it } from "vitest";

import { primaryNavigation, systemNavigation, visibleNavigation } from "./navigation";

describe("navigasi berbasis peran", () => {
  it("memberi pengguna sales menu operasional tanpa kontrol platform", () => {
    const primary = visibleNavigation(primaryNavigation, ["SALES"]);
    const system = visibleNavigation(systemNavigation, ["SALES"]);

    expect(primary.map((item) => item.href)).toEqual([
      "/",
      "/work-queue",
      "/documents",
      "/risks",
    ]);
    expect(system).toHaveLength(0);
  });

  it("memberi IT akses observability tanpa menu persetujuan bisnis", () => {
    const primary = visibleNavigation(primaryNavigation, ["IT_ADMIN"]);
    const system = visibleNavigation(systemNavigation, ["IT_ADMIN"]);

    expect(primary.some((item) => item.href === "/approvals")).toBe(false);
    expect(system.map((item) => item.href)).toContain("/system-health");
    expect(system.map((item) => item.href)).toContain("/users");
  });

  it("memberi direktur akses governance dan monitoring", () => {
    expect(visibleNavigation(primaryNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/approvals");
    expect(visibleNavigation(systemNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/agents");
    expect(visibleNavigation(systemNavigation, ["DIRECTOR"]).map((item) => item.href))
      .toContain("/users");
  });
});

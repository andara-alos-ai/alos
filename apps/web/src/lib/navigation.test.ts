import { describe, expect, it } from "vitest";

import { governanceNavigation, primaryNavigation, visibleNavigation } from "./navigation";

describe("Genesis MVP1 navigation", () => {
  it("keeps a compact Genesis-focused navigation", () => {
    expect(primaryNavigation.map((item) => item.href)).toEqual(["/", "/genesis", "/agents"]);
    expect(governanceNavigation.map((item) => item.href)).toEqual(["/approvals"]);
  });

  it("does not expose Genesis controls to an unprivileged division role", () => {
    expect(visibleNavigation(primaryNavigation, ["FINANCE"]).map((item) => item.href)).toEqual(["/"]);
  });
});

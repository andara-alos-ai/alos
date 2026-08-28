import { describe, expect, it } from "vitest";

import { sharedAgents, workflows, workspaces } from "./catalog";

describe("katalog ALOS", () => {
  it("memuat enam workspace divisi", () => {
    expect(workspaces).toHaveLength(6);
  });

  it("memetakan tepat 18 Core Agent", () => {
    const domainAgents = workspaces.flatMap((workspace) => [...workspace.agents]);
    expect(new Set([...sharedAgents, ...domainAgents]).size).toBe(18);
  });

  it("memuat enam workflow awal", () => {
    expect(workflows).toHaveLength(6);
  });
});

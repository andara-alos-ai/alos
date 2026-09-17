import { describe, expect, it } from "vitest";

import {
  isActionUsable,
  permissionForDomain,
  rndPermissionLabel,
  rndPermissionNextAction,
  rndPermissionTone,
  type RndDomainPermission,
} from "./rnd-permissions";

// M2-H02-FE-05 (R&D Permission UX): "UI hanya menampilkan action yang
// dikirim backend; denied/approval state mudah dipahami." No backend
// endpoint exists yet for R&D domain/backlog permissions, so an
// unspecified domain must default to NOT_CONNECTED — never a
// locally-fabricated ALLOWED state.
describe("rnd-permissions", () => {
  const permissions: RndDomainPermission[] = [
    { domain: "TECHNOLOGY", status: "ALLOWED" },
    { domain: "PROPERTY_MARKET", status: "DENIED", reason: "role not authorized" },
    { domain: "CORPORATE_MANAGEMENT", status: "NEEDS_APPROVAL" },
  ];

  it("defaults an unspecified domain to NOT_CONNECTED, never ALLOWED", () => {
    expect(permissionForDomain(permissions, "PROPERTY_BUSINESS_MODEL")).toBe("NOT_CONNECTED");
    expect(permissionForDomain(undefined, "TECHNOLOGY")).toBe("NOT_CONNECTED");
  });

  it("reads back an explicit backend decision for a known domain", () => {
    expect(permissionForDomain(permissions, "TECHNOLOGY")).toBe("ALLOWED");
    expect(permissionForDomain(permissions, "PROPERTY_MARKET")).toBe("DENIED");
    expect(permissionForDomain(permissions, "CORPORATE_MANAGEMENT")).toBe("NEEDS_APPROVAL");
  });

  it("labels every status in human, non-technical Indonesian, with no raw enum leak", () => {
    expect(rndPermissionLabel("ALLOWED")).toBe("Diizinkan");
    expect(rndPermissionLabel("DENIED")).toBe("Ditolak");
    expect(rndPermissionLabel("NEEDS_APPROVAL")).toBe("Perlu Persetujuan");
    expect(rndPermissionLabel("NOT_CONNECTED")).not.toMatch(/NOT_CONNECTED/);
  });

  it("gives each status a distinct, closed-set tone", () => {
    const tones = new Set([
      rndPermissionTone("ALLOWED"),
      rndPermissionTone("DENIED"),
      rndPermissionTone("NEEDS_APPROVAL"),
      rndPermissionTone("NOT_CONNECTED"),
    ]);
    expect(tones.size).toBe(4);
  });

  it("only suppresses the action for an explicit DENIED or NEEDS_APPROVAL, keeping NOT_CONNECTED/ALLOWED usable", () => {
    expect(isActionUsable("ALLOWED")).toBe(true);
    expect(isActionUsable("NOT_CONNECTED")).toBe(true);
    expect(isActionUsable("DENIED")).toBe(false);
    expect(isActionUsable("NEEDS_APPROVAL")).toBe(false);
  });

  it("gives DENIED and NEEDS_APPROVAL a human next-action message, understandable without backend jargon", () => {
    expect(rndPermissionNextAction("DENIED")).toMatch(/tidak diizinkan/i);
    expect(rndPermissionNextAction("NEEDS_APPROVAL")).toMatch(/persetujuan/i);
    expect(rndPermissionNextAction("ALLOWED")).toBeNull();
  });
});

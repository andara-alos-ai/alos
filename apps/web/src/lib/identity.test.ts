import { describe, expect, it } from "vitest";

import {
  canManageIdentity,
  canReadUserDirectory,
  divisionForRole,
  optionalDateTimeToIso,
  roleHasFixedDivision,
  validateAuditReason,
} from "./identity";

describe("aturan identitas", () => {
  it("memetakan role domain ke divisi yang dikunci backend", () => {
    expect(divisionForRole("SALES", "HR")).toBe("SALES_MARKETING");
    expect(divisionForRole("IT_ADMIN", "LEGAL")).toBe("IT");
    expect(roleHasFixedDivision("SALES")).toBe(true);
  });

  it("membiarkan kepala divisi memilih salah satu dari enam divisi", () => {
    expect(divisionForRole("DIVISION_HEAD", "PROPERTY")).toBe("PROPERTY");
    expect(roleHasFixedDivision("DIVISION_HEAD")).toBe(false);
  });

  it("tidak menempatkan role organisasi pada divisi", () => {
    expect(divisionForRole("DIRECTOR", "FINANCE")).toBeNull();
    expect(divisionForRole("AUDITOR", "LEGAL")).toBeNull();
  });

  it("memisahkan akses baca dan akses kelola", () => {
    expect(canReadUserDirectory(["DIRECTOR"])).toBe(true);
    expect(canReadUserDirectory(["AUDITOR"])).toBe(true);
    expect(canManageIdentity(["DIRECTOR"])).toBe(false);
    expect(canManageIdentity(["IT_ADMIN"])).toBe(true);
  });

  it("memvalidasi alasan audit dan waktu opsional", () => {
    expect(validateAuditReason("singkat")).not.toBeNull();
    expect(validateAuditReason("Akses untuk kebutuhan operasional")).toBeNull();
    expect(optionalDateTimeToIso("")).toBeNull();
    expect(optionalDateTimeToIso("2026-09-01T10:00")).toContain("2026-09-01T");
  });
});

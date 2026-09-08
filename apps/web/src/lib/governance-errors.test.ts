import { describe, expect, it } from "vitest";

import { ApiError } from "./api-client";
import { normalizeGovernanceError } from "./governance-errors";

describe("Governance error normalization", () => {
  it("explains SoD failures with a next action and reference", () => {
    expect(normalizeGovernanceError(new ApiError(409, "maker cannot act as checker", "corr-1"))).toEqual({
      title: "Separation of Duties memblokir aksi",
      reason: "Maker pada release request ini tidak boleh menjadi Checker.",
      nextAction: "Masuk dengan akun Checker independen, lalu jalankan test kembali.",
      status: 409,
      correlationId: "corr-1",
    });
  });

  it("keeps authorization, validation, rate limit, and server failures distinct", () => {
    expect(normalizeGovernanceError(new ApiError(403, "workspace denied", null)).title).toBe("Aksi tidak diizinkan");
    expect(normalizeGovernanceError(new ApiError(422, "field required", null)).title).toBe("Form belum dapat diproses");
    expect(normalizeGovernanceError(new ApiError(429, "budget exhausted", null)).title).toBe("Batas penggunaan tercapai");
    expect(normalizeGovernanceError(new ApiError(500, "database unavailable", "corr-500"))).toMatchObject({
      title: "Layanan Governance mengalami gangguan", correlationId: "corr-500",
    });
  });
});

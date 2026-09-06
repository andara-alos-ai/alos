import { describe, expect, it } from "vitest";

import { formatUploadSize, supportsGenesisUpload } from "./genesis-uploads";

describe("Genesis upload helpers", () => {
  it("accepts the supported document formats only", () => {
    expect(supportsGenesisUpload("Business Plan.PDF")).toBe(true);
    expect(supportsGenesisUpload("KPI.xlsx")).toBe(true);
    expect(supportsGenesisUpload("script.exe")).toBe(false);
  });

  it("formats a concise file size for the workspace", () => {
    expect(formatUploadSize(900)).toBe("900 B");
    expect(formatUploadSize(2048)).toBe("2 KB");
    expect(formatUploadSize(1_572_864)).toBe("1.5 MB");
  });
});

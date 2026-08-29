import { describe, expect, it } from "vitest";

import { formatDateTime, humanizeCode, relativeDeadline, shortId } from "./format";

describe("format tampilan operasional", () => {
  it("mengubah kode sistem menjadi label yang mudah dibaca", () => {
    expect(humanizeCode("SALES_MARKETING")).toBe("Sales Marketing");
  });

  it("tidak menampilkan identifier lengkap pada tabel", () => {
    expect(shortId("12345678-1234-1234-1234-123456789012")).toBe("12345678");
  });

  it("menandai deadline yang telah lewat", () => {
    expect(relativeDeadline("2026-08-28T00:00:00Z", new Date("2026-08-29T00:00:00Z")))
      .toBe("Terlambat 24 jam");
  });

  it("aman untuk tanggal kosong atau tidak valid", () => {
    expect(formatDateTime(null)).toBe("Belum ditetapkan");
    expect(formatDateTime("bukan-tanggal")).toBe("Waktu tidak valid");
  });
});

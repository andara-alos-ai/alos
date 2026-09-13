import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { FindingViews } from "./finding-views";
import type { SessionActor } from "@/lib/governance";

const mockActor: SessionActor = {
  user_id: "test.lead",
  organization_id: "org-1",
  roles: ["DIVISION_LEAD"],
  division_codes: ["IT"],
  workspace_ids: ["ws-1"],
  issued_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-12-31T23:59:59Z",
};

describe("FindingViews Presentation Components", () => {
  it("renders FindingViews hero header, title, subtitle, and primary action button", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Temuan");
    expect(html).toContain("Pantau, analisis, dan tindak lanjuti temuan dari audit, review, dan operasional.");
    expect(html).toContain("Catat Temuan Baru");
  });

  it("renders all 5 severity KPI cards with labels, counts, and subtexts", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Kritis");
    expect(html).toContain("8");
    expect(html).toContain("Perlu segera ditindaklanjuti");

    expect(html).toContain("Tinggi");
    expect(html).toContain("14");
    expect(html).toContain("Dalam proses penanganan");

    expect(html).toContain("Sedang");
    expect(html).toContain("11");
    expect(html).toContain("Dalam pemantauan");

    expect(html).toContain("Rendah");
    expect(html).toContain("6");
    expect(html).toContain("Sudah ditangani");

    expect(html).toContain("Total Temuan");
    expect(html).toContain("39");
    expect(html).toContain("Seluruh periode");
  });

  it("renders toolbar filter controls and search placeholder", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Cari temuan...");
    expect(html).toContain("Semua Kategori");
    expect(html).toContain("Semua Status");
    expect(html).toContain("Semua Divisi");
    expect(html).toContain("Semua Sumber");
    expect(html).toContain("Semua Periode");
  });

  it("renders master findings table headers and rows with codes", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("TMN-2026-001");
    expect(html).toContain("Akses sistem tanpa MFA");
    expect(html).toContain("TMN-2026-002");
    expect(html).toContain("Dokumentasi perubahan tidak lengkap");
    expect(html).toContain("TMN-2026-003");
    expect(html).toContain("Backup data tidak sesuai jadwal");
  });

  it("renders owner names, divisions, and badges in table rows", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Adi Wibowo");
    expect(html).toContain("IT Operations");
    expect(html).toContain("Sari Rahma");
    expect(html).toContain("Deni Nugroho");
    expect(html).toContain("Keamanan");
    expect(html).toContain("Infrastruktur");
  });

  it("renders detail panel with selected finding title, code, and Analisis & Dampak box", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Analisis &amp; Dampak");
    expect(html).toContain("Tidak digunakannya MFA pada akun dengan hak akses tinggi");
    expect(html).toContain("Tingkat Risiko");
    expect(html).toContain("Dampak Area");
    expect(html).toContain("Keamanan, Data, Operasional");
  });

  it("renders detail panel metadata fields", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Sumber Temuan");
    expect(html).toContain("Internal Audit");
    expect(html).toContain("Divisi Terkait");
    expect(html).toContain("Target Selesai");
    expect(html).toContain("12 Sep 2026 (2 hari lagi)");
  });

  it("renders related evidences with download actions and CTA button", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Bukti Terkait");
    expect(html).toContain("daftar-akun-tanpa-mfa.xlsx");
    expect(html).toContain("hasil-audit-akses.pdf");
    expect(html).toContain("tangkapan-layar.png");
    expect(html).toContain("Tindak Lanjut Temuan");
  });

  it("renders pagination footer with summary text and page controls", () => {
    const html = renderToStaticMarkup(createElement(FindingViews, { actor: mockActor }));
    expect(html).toContain("Menampilkan 1-8 dari 39 temuan");
  });
});

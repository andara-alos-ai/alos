import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { AraViews } from "./ara-views";
import type { SessionActor } from "@/lib/governance";

describe("AraViews Presentation Component", () => {
  const mockActor: SessionActor = {
    user_id: "test.lead",
    organization_id: "org-1",
    roles: ["DIVISION_LEAD"],
    division_codes: ["IT"],
    workspace_ids: ["ws-1"],
    issued_at: "2026-09-01T00:00:00Z",
    expires_at: "2026-12-31T23:59:59Z",
  };

  it("renders 3-column ARA workspace layout structure", () => {
    const html = renderToStaticMarkup(createElement(AraViews, { actor: mockActor }));
    expect(html).toContain("alos-ara-container");
    expect(html).toContain("alos-ara-workspace-grid");
    expect(html).toContain("alos-ara-sidebar");
    expect(html).toContain("alos-ara-main-stream");
    expect(html).toContain("alos-ara-right-panel");
  });

  it("renders Column 1: Percakapan sidebar with new chat button and grouped list", () => {
    const html = renderToStaticMarkup(createElement(AraViews, { actor: mockActor }));
    expect(html).toContain("Percakapan");
    expect(html).toContain("+ Percakapan Baru");
    expect(html).toContain("Cari percakapan...");
    expect(html).toContain("Hari Ini");
    expect(html).toContain("Kemarin");
    expect(html).toContain("7 Hari Terakhir");
    expect(html).toContain("Analisis risiko proyek digitalisasi");
    expect(html).toContain("Ringkasan progres divisi IT");
    expect(html).toContain("Draft laporan bulanan IT");
  });

  it("renders Column 2: Main ARA Stream with header, model select, and messages", () => {
    const html = renderToStaticMarkup(createElement(AraViews, { actor: mockActor }));
    expect(html).toContain("ARA");
    expect(html).toContain("Asisten AI untuk kerja yang lebih cerdas, cepat, dan berdampak.");
    expect(html).toContain("GENESIS Core");
    expect(html).toContain("Halo! Saya ARA, asisten AI ALOS.");
    expect(html).toContain("Tolong buatkan ringkasan progres proyek digitalisasi");
    expect(html).toContain("ARA sedang menganalisis data proyek...");
    expect(html).toContain("Ringkas dokumen yang saya upload");
  });

  it("renders Column 2: Composer input, toolbar and send button", () => {
    const html = renderToStaticMarkup(createElement(AraViews, { actor: mockActor }));
    expect(html).toContain("Tulis pertanyaan atau minta bantuan apa saja...");
    expect(html).toContain("Lampirkan");
    expect(html).toContain("Gunakan Konteks ⌵");
    expect(html).toContain("Shift + Enter untuk baris baru");
    expect(html).toContain("Kirim");
  });

  it("renders Column 3: Context card, active agents, and suggestions", () => {
    const html = renderToStaticMarkup(createElement(AraViews, { actor: mockActor }));
    expect(html).toContain("Konteks Saat Ini");
    expect(html).toContain("Belum ada konteks");
    expect(html).toContain("Agen Aktif");
    expect(html).toContain("Kelola Agen →");
    expect(html).toContain("Document Analyst");
    expect(html).toContain("Project Analyst");
    expect(html).toContain("Data Insight");
    expect(html).toContain("+ Request Agen Baru");
    expect(html).toContain("Saran untuk Anda");
    expect(html).toContain("Buat ringkasan progres divisi saya");
    expect(html).toContain("Dari Data Menuju Dampak");
  });
});

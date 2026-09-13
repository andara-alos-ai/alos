import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  DocumentViews,
  DocumentHero,
  DocumentAiBanner,
  DocumentCategoriesGrid,
  DocumentTable,
  DocumentDetailAiPanel,
  UploadDocumentModal,
  defaultReferenceDocuments,
} from "./document-views";

describe("Document Module Components", () => {
  it("renders DocumentHero with title, subtitle, and upload button", () => {
    const html = renderToStaticMarkup(
      createElement(DocumentHero, { onOpenUpload: () => {} }),
    );
    expect(html).toContain("Dokumen");
    expect(html).toContain("Kelola, temukan, dan pahami dokumen perusahaan dengan bantuan AI.");
    expect(html).toContain("Unggah Dokumen");
  });

  it("renders DocumentAiBanner with AI intelligence copy and action button", () => {
    const html = renderToStaticMarkup(
      createElement(DocumentAiBanner, { onAskAra: () => {} }),
    );
    expect(html).toContain("Temukan informasi lebih cepat dengan kecerdasan dokumen");
    expect(html).toContain("ARA dapat membaca, memahami, dan merangkum dokumen Anda");
    expect(html).toContain("Tanyakan ke ARA");
    expect(html).toContain("Ringkas isi dokumen ini untuk saya...");
  });

  it("renders DocumentCategoriesGrid with all 7 categories", () => {
    const html = renderToStaticMarkup(
      createElement(DocumentCategoriesGrid, {
        activeCategory: "all",
        onSelectCategory: () => {},
      }),
    );
    expect(html).toContain("Kategori Dokumen");
    expect(html).toContain("Semua Dokumen");
    expect(html).toContain("Kebijakan");
    expect(html).toContain("SOP");
    expect(html).toContain("Panduan");
    expect(html).toContain("Laporan");
    expect(html).toContain("Kontrak");
    expect(html).toContain("Lainnya");
  });

  it("renders DocumentTable with tabs, headers, and document rows", () => {
    const html = renderToStaticMarkup(
      createElement(DocumentTable, {
        activeStatusTab: "recent",
        items: defaultReferenceDocuments,
        onRowClick: () => {},
        onSelectStatusTab: () => {},
        onSortChange: () => {},
        selectedDocId: "doc-ref-001",
        sortOrder: "newest",
      }),
    );
    expect(html).toContain("Terbaru");
    expect(html).toContain("Draft (12)");
    expect(html).toContain("Dalam Review (8)");
    expect(html).toContain("Disetujui (108)");
    expect(html).toContain("Nama Dokumen");
    expect(html).toContain("Kategori");
    expect(html).toContain("Diubah Oleh");
    expect(html).toContain("Terakhir Diubah");
    expect(html).toContain("Kebijakan Keamanan Informasi v2.0.pdf");
    expect(html).toContain("Andi Setiawan");
  });

  it("renders DocumentDetailAiPanel with Ringkasan oleh ARA, Poin Penting, and Informasi Dokumen", () => {
    const html = renderToStaticMarkup(
      createElement(DocumentDetailAiPanel, {
        doc: defaultReferenceDocuments[0],
        onAskAra: () => {},
      }),
    );
    expect(html).toContain("Kebijakan Keamanan Informasi v2.0.pdf");
    expect(html).toContain("Ringkasan AI");
    expect(html).toContain("Ringkasan oleh ARA");
    expect(html).toContain("Poin Penting");
    expect(html).toContain("Menetapkan prinsip keamanan informasi");
    expect(html).toContain("Informasi Dokumen");
    expect(html).toContain("Andi Setiawan");
    expect(html).toContain("IT Operations / Kebijakan");
    expect(html).toContain("iso27001");
  });

  it("renders UploadDocumentModal with dropzone and form fields", () => {
    const html = renderToStaticMarkup(
      createElement(UploadDocumentModal, {
        onClose: () => {},
        onSubmit: () => {},
      }),
    );
    expect(html).toContain("Unggah Dokumen Baru");
    expect(html).toContain("Tarik &amp; lepas file dokumen ke sini");
    expect(html).toContain("Nama Dokumen *");
    expect(html).toContain("Klasifikasi Akses");
  });

  it("renders complete DocumentViews container with layout sections", () => {
    const html = renderToStaticMarkup(createElement(DocumentViews));
    expect(html).toContain("alos-doc-container");
    expect(html).toContain("Dokumen");
    expect(html).toContain("alos-doc-ai-banner");
    expect(html).toContain("alos-doc-categories-grid");
    expect(html).toContain("alos-doc-split-layout");
  });
});

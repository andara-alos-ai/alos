import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ApprovalViews,
  ApprovalHero,
  ApprovalMetricsRow,
  ApprovalCategoryTabs,
  ApprovalSearchBar,
  ApprovalCardItem,
  ApprovalPaginationBar,
  ApprovalDetailPanel,
  ApprovalDecisionModal,
} from "./approval-views";

describe("Approval Module Components", () => {
  it("renders ApprovalHero with title, subtitle, and quote banner", () => {
    const html = renderToStaticMarkup(createElement(ApprovalHero));
    expect(html).toContain("Pusat Persetujuan");
    expect(html).toContain("Kelola, tinjau, dan ambil keputusan untuk semua pengajuan di ALOS");
    expect(html).toContain("Keputusan hari ini,");
    expect(html).toContain("untuk dampak yang lebih besar.");
  });

  it("renders ApprovalMetricsRow with 4 cards", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalMetricsRow, {
        pending: 8,
        inProgress: 4,
        approved: 24,
        rejected: 3,
      }),
    );
    expect(html).toContain("Menunggu Persetujuan");
    expect(html).toContain("8");
    expect(html).toContain("Dalam Proses");
    expect(html).toContain("4");
    expect(html).toContain("Disetujui");
    expect(html).toContain("24");
    expect(html).toContain("Ditolak");
    expect(html).toContain("3");
  });

  it("renders ApprovalCategoryTabs with all category options", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalCategoryTabs, {
        activeCategory: "all",
        onSelectCategory: () => {},
      }),
    );
    expect(html).toContain("Semua");
    expect(html).toContain("Permintaan Akses");
    expect(html).toContain("Pengajuan Proyek");
    expect(html).toContain("Pengadaan");
    expect(html).toContain("Perubahan");
    expect(html).toContain("Lainnya ⌵");
  });

  it("renders ApprovalSearchBar with placeholder and filter button", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalSearchBar, {
        searchQuery: "",
        onSearchChange: () => {},
        sortOrder: "newest",
        onSortChange: () => {},
      }),
    );
    expect(html).toContain("Cari judul, pemohon, atau ID pengajuan...");
    expect(html).toContain("Filter ⌵");
    expect(html).toContain("Terbaru dulu ⌵");
  });

  it("renders ApprovalCardItem with title, code, status pill, and relative time", () => {
    const sampleItem = {
      approval_request_id: "test-001",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "BUSINESS",
      subject_type: "PROCUREMENT",
      subject_id: "subj-001",
      payload_digest: "abcdef",
      title: "Pengadaan Laptop Tim IT",
      description: "Pengajuan 5 unit laptop untuk engineer.",
      urgency: "NORMAL" as const,
      status: "PENDING" as const,
      requested_by_user_id: "Budi",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T12:00:00Z",
      decided_at: null,
      code: "IT-PRC-2026-0012",
      categoryLabel: "Pengadaan",
      relativeTime: "2 jam yang lalu",
    };

    const html = renderToStaticMarkup(
      createElement(ApprovalCardItem, {
        item: sampleItem,
        isSelected: true,
        onSelect: () => {},
      }),
    );
    expect(html).toContain("Pengadaan Laptop Tim IT");
    expect(html).toContain("IT-PRC-2026-0012");
    expect(html).toContain("Pengadaan");
    expect(html).toContain("Menunggu Persetujuan");
    expect(html).toContain("2 jam yang lalu");
  });

  it("renders ApprovalDetailPanel with Informasi Pengajuan, Dokumen Pendukung, and action buttons", () => {
    const sampleItem = {
      approval_request_id: "test-001",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "BUSINESS",
      subject_type: "PROCUREMENT",
      subject_id: "subj-001",
      payload_digest: "abcdef",
      title: "Pengadaan Laptop Tim IT",
      description: "Pengajuan 5 unit laptop untuk operasional.",
      urgency: "NORMAL" as const,
      status: "PENDING" as const,
      requested_by_user_id: "Budi",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T12:00:00Z",
      decided_at: null,
      code: "IT-PRC-2026-0012",
      categoryLabel: "Pengadaan",
      submitterName: "Budi Santoso",
      valueAmount: "Rp 125.000.000",
      projectName: "Infrastruktur IT 2026",
      divisionName: "IT Operations",
      priorityLabel: "Tinggi" as const,
      requiredDate: "30 September 2026",
      attachments: [
        { name: "Proposal_Laptop_IT.pdf", size: "1.2 MB", type: "pdf" as const },
        { name: "Rincian_Harga.xlsx", size: "320 KB", type: "excel" as const },
      ],
    };

    const html = renderToStaticMarkup(
      createElement(ApprovalDetailPanel, {
        item: sampleItem,
        onDecide: () => {},
      }),
    );
    expect(html).toContain("Pengadaan Laptop Tim IT");
    expect(html).toContain("Diajukan oleh Budi Santoso");
    expect(html).toContain("Informasi Pengajuan");
    expect(html).toContain("Rp 125.000.000");
    expect(html).toContain("Infrastruktur IT 2026");
    expect(html).toContain("IT Operations");
    expect(html).toContain("Dokumen Pendukung");
    expect(html).toContain("Proposal_Laptop_IT.pdf");
    expect(html).toContain("Minta Revisi");
    expect(html).toContain("Tolak");
    expect(html).toContain("Setujui");
  });

  it("renders ApprovalDecisionModal with mandatory notes form field", () => {
    const sampleItem = {
      approval_request_id: "test-001",
      workspace_id: "ws-01",
      division_code: "IT",
      approval_kind: "BUSINESS",
      subject_type: "PROCUREMENT",
      subject_id: "subj-001",
      payload_digest: "abcdef",
      title: "Pengadaan Laptop Tim IT",
      description: "Pengajuan 5 unit laptop.",
      urgency: "NORMAL" as const,
      status: "PENDING" as const,
      requested_by_user_id: "Budi",
      approver_user_id: null,
      decision_notes: null,
      requested_at: "2026-09-10T12:00:00Z",
      decided_at: null,
      code: "IT-PRC-2026-0012",
      submitterName: "Budi Santoso",
    };

    const html = renderToStaticMarkup(
      createElement(ApprovalDecisionModal, {
        item: sampleItem,
        decision: "APPROVED",
        onClose: () => {},
        onSubmit: () => {},
      }),
    );
    expect(html).toContain("Setujui Pengajuan");
    expect(html).toContain("Catatan Keputusan *");
    expect(html).toContain("Konfirmasi Setujui Pengajuan");
  });

  it("renders ApprovalPaginationBar with total items and pagination buttons", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalPaginationBar, {
        currentPage: 1,
        totalPages: 5,
        totalItems: 39,
        visibleCount: 5,
      }),
    );
    expect(html).toContain("Menampilkan 1 - 5 dari 39 pengajuan");
  });

  it("renders complete ApprovalViews container with master-detail split layout", () => {
    const html = renderToStaticMarkup(createElement(ApprovalViews));
    expect(html).toContain("alos-appr-container");
    expect(html).toContain("Pusat Persetujuan");
    expect(html).toContain("alos-appr-split-layout");
    expect(html).toContain("alos-appr-master-col");
    expect(html).toContain("alos-appr-detail-col");
  });
});

"use client";

import { useMemo, useState } from "react";
import type { SessionActor } from "@/lib/governance";
import type { DocumentDetail, DocumentRecord } from "@/lib/documents";

export type DocumentCategoryKey =
  | "all"
  | "policy"
  | "sop"
  | "guide"
  | "report"
  | "contract"
  | "other";

export type DocumentStatusTab = "recent" | "draft" | "review" | "approved";

export type DocumentItemViewModel = DocumentRecord & {
  fileName?: string;
  subtitle?: string;
  fileType?: "pdf" | "doc" | "sheet" | "img";
  fileSize?: string;
  authorName?: string;
  authorInitials?: string;
  lastModifiedDate?: string;
  lastModifiedTime?: string;
  createdDate?: string;
  location?: string;
  accessLevel?: string;
  tags?: string[];
  aiSummary?: string;
  keyPoints?: string[];
  versionsCount?: number;
};

export type DocumentViewsProps = {
  actor?: SessionActor;
  documents?: DocumentRecord[];
  selectedDetail?: DocumentDetail | null;
  onSelectDocument?: (documentId: string) => void;
  onCreateDraft?: (
    title: string,
    content: string,
    category: string,
    classification: string,
  ) => Promise<void>;
  onAskAra?: (documentId: string, prompt?: string) => void;
  isLoading?: boolean;
  onRefresh?: () => void;
};

// Seed dataset matching the reference image layout when live documents are fewer
export const defaultReferenceDocuments: DocumentItemViewModel[] = [
  {
    document_id: "doc-ref-001",
    organization_id: "org-01",
    workspace_id: "ws-01",
    division_code: "IT",
    genesis_conversation_id: "conv-001",
    genesis_upload_id: null,
    title: "Kebijakan Keamanan Informasi v2.0.pdf",
    fileName: "Kebijakan Keamanan Informasi v2.0.pdf",
    subtitle: "Kebijakan keamanan informasi perusahaan",
    category: "Kebijakan",
    classification: "INTERNAL",
    origin: "MANUAL",
    status: "APPROVED",
    owner_user_id: "user-01",
    created_by_user_id: "user-01",
    version_number: 2,
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-10T14:32:00Z",
    fileType: "pdf",
    fileSize: "2.4 MB",
    authorName: "Andi Setiawan",
    authorInitials: "AS",
    lastModifiedDate: "10 Sep 2026",
    lastModifiedTime: "14.32 WIB",
    createdDate: "1 Sep 2026, 09.00 WIB",
    location: "IT Operations / Kebijakan",
    accessLevel: "Internal",
    tags: ["keamanan", "informasi", "kebijakan", "iso27001"],
    aiSummary:
      "Dokumen ini berisi kebijakan keamanan informasi perusahaan yang mencakup prinsip, tanggung jawab, klasifikasi data, pengelolaan akses, serta prosedur penanganan insiden keamanan. Tujuannya adalah melindungi aset informasi perusahaan dan memastikan kepatuhan terhadap regulasi yang berlaku.",
    keyPoints: [
      "Menetapkan prinsip keamanan informasi",
      "Mengatur klasifikasi dan penanganan data",
      "Menjelaskan peran dan tanggung jawab setiap pihak",
      "Prosedur pelaporan dan penanganan insiden",
      "Mengacu pada standar ISO 27001",
    ],
    versionsCount: 3,
  },
  {
    document_id: "doc-ref-002",
    organization_id: "org-01",
    workspace_id: "ws-01",
    division_code: "IT",
    genesis_conversation_id: null,
    genesis_upload_id: null,
    title: "SOP Pengelolaan Akses Sistem.docx",
    fileName: "SOP Pengelolaan Akses Sistem.docx",
    subtitle: "Prosedur standar pengelolaan akses",
    category: "SOP",
    classification: "INTERNAL",
    origin: "MANUAL",
    status: "ACTIVE",
    owner_user_id: "user-02",
    created_by_user_id: "user-02",
    version_number: 1,
    created_at: "2026-09-02T10:00:00Z",
    updated_at: "2026-09-09T10:15:00Z",
    fileType: "doc",
    fileSize: "1.8 MB",
    authorName: "Siti Rahma",
    authorInitials: "SR",
    lastModifiedDate: "9 Sep 2026",
    lastModifiedTime: "10.15 WIB",
    createdDate: "2 Sep 2026, 10.00 WIB",
    location: "IT Operations / SOP",
    accessLevel: "Internal",
    tags: ["akses", "keamanan", "sop", "user-management"],
    aiSummary:
      "Standar operasional prosedur untuk tata kelola pendaftaran, pengubahan hak akses, serta penutupan akun pengguna sistem internal secara berkala.",
    keyPoints: [
      "Proses permohonan akses berbasis least-privilege",
      "Otorisasi bertingkat oleh kepala divisi",
      "Audit berkala akun setiap kuartal",
    ],
    versionsCount: 2,
  },
  {
    document_id: "doc-ref-003",
    organization_id: "org-01",
    workspace_id: "ws-01",
    division_code: "IT",
    genesis_conversation_id: null,
    genesis_upload_id: null,
    title: "Laporan Evaluasi Infrastruktur Q3 2026.pdf",
    fileName: "Laporan Evaluasi Infrastruktur Q3 2026.pdf",
    subtitle: "Laporan evaluasi infrastruktur IT",
    category: "Laporan",
    classification: "CONFIDENTIAL",
    origin: "MANUAL",
    status: "IN_REVIEW",
    owner_user_id: "user-03",
    created_by_user_id: "user-03",
    version_number: 1,
    created_at: "2026-09-03T11:00:00Z",
    updated_at: "2026-09-08T16:20:00Z",
    fileType: "pdf",
    fileSize: "3.1 MB",
    authorName: "Budi Santoso",
    authorInitials: "BS",
    lastModifiedDate: "8 Sep 2026",
    lastModifiedTime: "16.20 WIB",
    createdDate: "3 Sep 2026, 11.00 WIB",
    location: "IT Operations / Laporan",
    accessLevel: "Confidential",
    tags: ["infrastruktur", "q3-2026", "evaluasi", "cloud"],
    aiSummary:
      "Evaluasi performa jaringan, kapasitas server on-premise dan cloud, serta proyeksi peningkatan beban untuk kesiapan peluncuran sistem enterprise Q4.",
    keyPoints: [
      "Ketersediaan layanan cloud mencapai 99.95%",
      "Kapasitas storage tersisa 35% sebelum ekspansi",
      "Rekomendasi upgrade link konektivitas antar-cabang",
    ],
    versionsCount: 1,
  },
  {
    document_id: "doc-ref-004",
    organization_id: "org-01",
    workspace_id: "ws-01",
    division_code: "IT",
    genesis_conversation_id: null,
    genesis_upload_id: null,
    title: "Kontrak Vendor Cloud Services.docx",
    fileName: "Kontrak Vendor Cloud Services.docx",
    subtitle: "Perjanjian layanan cloud dengan PT Nusa Data",
    category: "Kontrak",
    classification: "RESTRICTED",
    origin: "MANUAL",
    status: "DRAFT",
    owner_user_id: "user-01",
    created_by_user_id: "user-01",
    version_number: 1,
    created_at: "2026-09-04T08:30:00Z",
    updated_at: "2026-09-07T11:45:00Z",
    fileType: "doc",
    fileSize: "1.5 MB",
    authorName: "Andi Setiawan",
    authorInitials: "AS",
    lastModifiedDate: "7 Sep 2026",
    lastModifiedTime: "11.45 WIB",
    createdDate: "4 Sep 2026, 08.30 WIB",
    location: "IT Operations / Kontrak",
    accessLevel: "Restricted",
    tags: ["vendor", "kontrak", "sla", "cloud"],
    aiSummary:
      "Draft perjanjian kerja sama tahunan penyediaan infrastruktur komputasi awan mencakup komitmen SLA 99.9%, batasan liabilitas, dan ketentuan eskalasi gangguan.",
    keyPoints: [
      "Jaminan SLA availability 99.9%",
      "Waktu respons penanganan insiden prioritas P1 di bawah 15 menit",
      "Klausul kerahasiaan dan kepemilikan data perusahaan",
    ],
    versionsCount: 1,
  },
  {
    document_id: "doc-ref-005",
    organization_id: "org-01",
    workspace_id: "ws-01",
    division_code: "IT",
    genesis_conversation_id: null,
    genesis_upload_id: null,
    title: "Panduan Onboarding Karyawan IT.pdf",
    fileName: "Panduan Onboarding Karyawan IT.pdf",
    subtitle: "Panduan orientasi untuk tim IT baru",
    category: "Panduan",
    classification: "INTERNAL",
    origin: "MANUAL",
    status: "APPROVED",
    owner_user_id: "user-04",
    created_by_user_id: "user-04",
    version_number: 1,
    created_at: "2026-09-05T09:12:00Z",
    updated_at: "2026-09-05T09:12:00Z",
    fileType: "pdf",
    fileSize: "4.2 MB",
    authorName: "Dewi Lestari",
    authorInitials: "DL",
    lastModifiedDate: "5 Sep 2026",
    lastModifiedTime: "09.12 WIB",
    createdDate: "5 Sep 2026, 09.12 WIB",
    location: "IT Operations / Panduan",
    accessLevel: "Internal",
    tags: ["onboarding", "panduan", "it-team", "sop"],
    aiSummary:
      "Buku panduan pengenalan lingkungan kerja teknis bagi anggota tim baru meliputi alur kerja Git, standar kode, pengaturan VPN, dan panduan keamanan perangkat kerja.",
    keyPoints: [
      "Setup lingkungan pengembangan dan akses repository",
      "Ketentuan branching Git dan pull request review",
      "Daftar kontak penting tim infrastruktur dan sekuriti",
    ],
    versionsCount: 1,
  },
];

export function DocumentViews({
  documents = [],
  onSelectDocument,
  onCreateDraft,
  onAskAra,
}: DocumentViewsProps) {
  const [selectedCategoryId, setSelectedCategoryId] =
    useState<DocumentCategoryKey>("all");
  const [selectedStatusTab, setSelectedStatusTab] =
    useState<DocumentStatusTab>("recent");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [selectedDocId, setSelectedDocId] = useState<string>("doc-ref-001");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  // Merge live documents with reference items
  const allItems: DocumentItemViewModel[] = useMemo(() => {
    if (!documents || documents.length === 0) {
      return defaultReferenceDocuments;
    }

    const merged = documents.map((live, idx) => {
      const fallback =
        defaultReferenceDocuments[idx % defaultReferenceDocuments.length];
      return {
        ...fallback,
        ...live,
        fileName: live.title.endsWith(".pdf") || live.title.endsWith(".docx")
          ? live.title
          : `${live.title}.pdf`,
        subtitle: fallback?.subtitle ?? `Dokumen kategori ${live.category}`,
        fileType: live.title.endsWith(".docx") || live.title.endsWith(".doc")
          ? "doc"
          : "pdf",
        fileSize: fallback?.fileSize ?? "2.4 MB",
        authorName: fallback?.authorName ?? "Andi Setiawan",
        authorInitials: fallback?.authorInitials ?? "AS",
        lastModifiedDate: fallback?.lastModifiedDate ?? "10 Sep 2026",
        lastModifiedTime: fallback?.lastModifiedTime ?? "14.32 WIB",
        createdDate: fallback?.createdDate ?? "1 Sep 2026, 09.00 WIB",
        location: `IT Operations / ${live.category}`,
        accessLevel: live.classification === "PUBLIC" ? "Publik" : "Internal",
        tags: fallback?.tags ?? ["dokumen", "it", live.category.toLowerCase()],
        aiSummary: fallback?.aiSummary ?? "Dokumen operasional internal ALOS.",
        keyPoints: fallback?.keyPoints ?? [
          "Dokumen resmi terdaftar di repositori ALOS",
          "Memenuhi standar klasifikasi keamanan data",
        ],
        versionsCount: live.version_number || 1,
      } as DocumentItemViewModel;
    });

    if (merged.length < defaultReferenceDocuments.length) {
      const remaining = defaultReferenceDocuments.slice(merged.length);
      return [...merged, ...remaining];
    }
    return merged;
  }, [documents]);

  // Filtered documents
  const filteredItems = useMemo(() => {
    let result = [...allItems];

    // Filter by Category Card
    if (selectedCategoryId !== "all") {
      result = result.filter((item) => {
        const cat = item.category.toLowerCase();
        if (selectedCategoryId === "policy") return cat.includes("kebijakan");
        if (selectedCategoryId === "sop") return cat.includes("sop");
        if (selectedCategoryId === "guide") return cat.includes("panduan");
        if (selectedCategoryId === "report") return cat.includes("laporan");
        if (selectedCategoryId === "contract") return cat.includes("kontrak");
        return true;
      });
    }

    // Filter by Status Tab
    if (selectedStatusTab === "draft") {
      result = result.filter((item) => item.status === "DRAFT");
    } else if (selectedStatusTab === "review") {
      result = result.filter((item) => item.status === "IN_REVIEW");
    } else if (selectedStatusTab === "approved") {
      result = result.filter(
        (item) => item.status === "APPROVED" || item.status === "ACTIVE",
      );
    }

    // Sort
    if (sortOrder === "oldest") {
      result.sort(
        (a, b) =>
          new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(),
      );
    } else {
      result.sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
    }

    return result;
  }, [allItems, selectedCategoryId, selectedStatusTab, sortOrder]);

  // Selected item for detail panel
  const selectedDoc = useMemo(() => {
    const found = allItems.find((d) => d.document_id === selectedDocId);
    return found || filteredItems[0] || allItems[0];
  }, [allItems, selectedDocId, filteredItems]);

  const handleRowClick = (docId: string) => {
    setSelectedDocId(docId);
    if (onSelectDocument) {
      onSelectDocument(docId);
    }
  };

  return (
    <div className="alos-doc-container">
      {/* Header & CTA */}
      <DocumentHero onOpenUpload={() => setUploadModalOpen(true)} />

      {/* AI Document Intelligence Banner */}
      <DocumentAiBanner
        onAskAra={() => {
          if (onAskAra && selectedDoc) {
            onAskAra(selectedDoc.document_id);
          }
        }}
      />

      {/* Categories Grid Carousel */}
      <DocumentCategoriesGrid
        activeCategory={selectedCategoryId}
        onSelectCategory={setSelectedCategoryId}
      />

      {/* Master-Detail Split Layout */}
      <div className="alos-doc-split-layout">
        {/* Left Column: Documents Table */}
        <div className="alos-doc-master-col">
          <DocumentTable
            activeStatusTab={selectedStatusTab}
            items={filteredItems}
            onRowClick={handleRowClick}
            onSelectStatusTab={setSelectedStatusTab}
            onSortChange={setSortOrder}
            selectedDocId={selectedDoc?.document_id}
            sortOrder={sortOrder}
          />
        </div>

        {/* Right Column: Selected Document Detail & AI Summary */}
        <div className="alos-doc-detail-col">
          {selectedDoc ? (
            <DocumentDetailAiPanel
              doc={selectedDoc}
              onAskAra={(prompt) => {
                if (onAskAra) onAskAra(selectedDoc.document_id, prompt);
              }}
            />
          ) : (
            <div className="alos-doc-empty-detail">
              <p>Pilih salah satu dokumen untuk melihat rincian dan ringkasan AI.</p>
            </div>
          )}
        </div>
      </div>

      {/* Modal Upload Dokumen */}
      {uploadModalOpen && (
        <UploadDocumentModal
          onClose={() => setUploadModalOpen(false)}
          onSubmit={async (name, cat, classif, desc) => {
            if (onCreateDraft) {
              await onCreateDraft(name, desc, cat, classif);
            }
            setUploadModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

/* =========================================================================
   SUB-COMPONENTS
   ========================================================================= */

export function DocumentHero({ onOpenUpload }: { onOpenUpload: () => void }) {
  return (
    <div className="alos-doc-hero">
      <div className="alos-doc-hero-copy">
        <h1 className="alos-doc-hero-title">Dokumen</h1>
        <p className="alos-doc-hero-subtitle">
          Kelola, temukan, dan pahami dokumen perusahaan dengan bantuan AI.
        </p>
      </div>

      <button className="alos-doc-btn-upload" onClick={onOpenUpload} type="button">
        <span className="plus" aria-hidden="true">+</span>
        <span>Unggah Dokumen</span>
      </button>
    </div>
  );
}

export function DocumentAiBanner({ onAskAra }: { onAskAra: () => void }) {
  return (
    <div className="alos-doc-ai-banner" role="region" aria-label="Kecerdasan Dokumen ARA">
      <div className="alos-doc-ai-content">
        <h2 className="alos-doc-ai-title">
          Temukan informasi lebih cepat dengan kecerdasan dokumen
        </h2>
        <p className="alos-doc-ai-desc">
          ARA dapat membaca, memahami, dan merangkum dokumen Anda, sehingga Anda bisa
          mendapatkan informasi yang relevan secara instan.
        </p>
        <button className="alos-doc-ai-btn" onClick={onAskAra} type="button">
          <svg
            className="sparkle-icon"
            fill="none"
            height="18"
            stroke="#eab308"
            viewBox="0 0 24 24"
            width="18"
            aria-hidden="true"
          >
            <path
              d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"
              fill="#eab308"
              stroke="#eab308"
              strokeWidth="1.5"
            />
          </svg>
          <span>Tanyakan ke ARA</span>
        </button>
      </div>

      <div className="alos-doc-ai-illustration" aria-hidden="true">
        <div className="alos-doc-ai-mockup">
          <div className="mockup-header">
            <span className="mockup-bar short" />
            <span className="mockup-bar" />
          </div>
          <div className="mockup-body">
            <span className="mockup-line" />
            <span className="mockup-line" />
            <span className="mockup-line short" />
          </div>
          <div className="mockup-bubble">
            <span>&ldquo;Ringkas isi dokumen ini untuk saya...&rdquo;</span>
          </div>
          <div className="mockup-star">✦</div>
        </div>
      </div>
    </div>
  );
}

export function DocumentCategoriesGrid({
  activeCategory,
  onSelectCategory,
}: {
  activeCategory: DocumentCategoryKey;
  onSelectCategory: (cat: DocumentCategoryKey) => void;
}) {
  const categories: Array<{
    id: DocumentCategoryKey;
    title: string;
    count: string;
    icon: string;
  }> = [
    { id: "all", title: "Semua Dokumen", count: "128 dokumen", icon: "folder" },
    { id: "policy", title: "Kebijakan", count: "24 dokumen", icon: "folder" },
    { id: "sop", title: "SOP", count: "18 dokumen", icon: "file" },
    { id: "guide", title: "Panduan", count: "16 dokumen", icon: "book" },
    { id: "report", title: "Laporan", count: "22 dokumen", icon: "chart" },
    { id: "contract", title: "Kontrak", count: "14 dokumen", icon: "folder" },
    { id: "other", title: "Lainnya", count: "34 dokumen", icon: "dots" },
  ];

  return (
    <div className="alos-doc-categories-wrap">
      <div className="alos-doc-categories-header">
        <h3 className="alos-doc-categories-heading">Kategori Dokumen</h3>
        <button
          className="alos-doc-link-more"
          onClick={() => onSelectCategory("all")}
          type="button"
        >
          Lihat Semua →
        </button>
      </div>

      <div className="alos-doc-categories-grid" role="tablist">
        {categories.map((cat) => (
          <button
            className={`alos-doc-category-card ${activeCategory === cat.id ? "active" : ""}`}
            key={cat.id}
            onClick={() => onSelectCategory(cat.id)}
            role="tab"
            aria-selected={activeCategory === cat.id}
            type="button"
          >
            <div className="alos-doc-category-icon">
              {cat.icon === "folder" && (
                <svg fill="none" height="18" stroke="#10b981" viewBox="0 0 24 24" width="18">
                  <path
                    d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                </svg>
              )}
              {cat.icon === "file" && (
                <svg fill="none" height="18" stroke="#10b981" viewBox="0 0 24 24" width="18">
                  <path
                    d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" strokeLinecap="round" strokeWidth="1.8" />
                </svg>
              )}
              {cat.icon === "book" && (
                <svg fill="none" height="18" stroke="#10b981" viewBox="0 0 24 24" width="18">
                  <path
                    d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                </svg>
              )}
              {cat.icon === "chart" && (
                <svg fill="none" height="18" stroke="#10b981" viewBox="0 0 24 24" width="18">
                  <line x1="18" x2="18" y1="20" y2="10" strokeWidth="1.8" strokeLinecap="round" />
                  <line x1="12" x2="12" y1="20" y2="4" strokeWidth="1.8" strokeLinecap="round" />
                  <line x1="6" x2="6" y1="20" y2="14" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              )}
              {cat.icon === "dots" && (
                <svg fill="none" height="18" stroke="#10b981" viewBox="0 0 24 24" width="18">
                  <circle cx="12" cy="12" r="1.5" fill="#10b981" />
                  <circle cx="19" cy="12" r="1.5" fill="#10b981" />
                  <circle cx="5" cy="12" r="1.5" fill="#10b981" />
                </svg>
              )}
            </div>
            <div className="alos-doc-category-info">
              <span className="alos-doc-category-title">{cat.title}</span>
              <span className="alos-doc-category-count">{cat.count}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function DocumentTable({
  items,
  activeStatusTab,
  onSelectStatusTab,
  selectedDocId,
  onRowClick,
  sortOrder,
  onSortChange,
}: {
  items: DocumentItemViewModel[];
  activeStatusTab: DocumentStatusTab;
  onSelectStatusTab: (t: DocumentStatusTab) => void;
  selectedDocId?: string;
  onRowClick: (id: string) => void;
  sortOrder: "newest" | "oldest";
  onSortChange: (s: "newest" | "oldest") => void;
}) {
  const statusTabs: Array<{ id: DocumentStatusTab; label: string }> = [
    { id: "recent", label: "Terbaru" },
    { id: "draft", label: "Draft (12)" },
    { id: "review", label: "Dalam Review (8)" },
    { id: "approved", label: "Disetujui (108)" },
  ];

  return (
    <div className="alos-doc-table-card">
      {/* Table Controls Header */}
      <div className="alos-doc-table-controls">
        <div className="alos-doc-tabs" role="tablist">
          {statusTabs.map((tab) => (
            <button
              className={`alos-doc-tab ${activeStatusTab === tab.id ? "active" : ""}`}
              key={tab.id}
              onClick={() => onSelectStatusTab(tab.id)}
              role="tab"
              aria-selected={activeStatusTab === tab.id}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="alos-doc-table-actions">
          <button className="alos-doc-btn-filter" type="button" aria-label="Buka Filter">
            <svg fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" strokeWidth="1.8" />
            </svg>
            <span>Filter ⌵</span>
          </button>

          <select
            aria-label="Urutkan Dokumen"
            className="alos-doc-sort-select"
            onChange={(e) => onSortChange(e.target.value as "newest" | "oldest")}
            value={sortOrder}
          >
            <option value="newest">Terbaru ⌵</option>
            <option value="oldest">Terlama ⌵</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="alos-doc-table-wrap">
        <table className="alos-doc-table" aria-label="Daftar Dokumen Resmi">
          <thead>
            <tr>
              <th>Nama Dokumen</th>
              <th>Kategori</th>
              <th>Diubah Oleh</th>
              <th>Terakhir Diubah</th>
              <th aria-label="Aksi" />
            </tr>
          </thead>
          <tbody>
            {items.map((doc) => {
              const isSelected = doc.document_id === selectedDocId;
              const catKind = doc.category.toLowerCase();

              return (
                <tr
                  className={`alos-doc-row ${isSelected ? "selected" : ""}`}
                  key={doc.document_id}
                  onClick={() => onRowClick(doc.document_id)}
                >
                  <td className="doc-col-name">
                    <div className="doc-name-wrap">
                      <div className={`doc-type-badge ${doc.fileType || "pdf"}`}>
                        {doc.fileType === "doc" ? "DOC" : "PDF"}
                      </div>
                      <div className="doc-titles">
                        <span className="doc-file-title">{doc.fileName || doc.title}</span>
                        <span className="doc-file-sub">{doc.subtitle}</span>
                      </div>
                    </div>
                  </td>

                  <td className="doc-col-category">
                    <span
                      className={`alos-doc-badge ${
                        catKind.includes("kebijakan")
                          ? "policy"
                          : catKind.includes("sop")
                            ? "sop"
                            : catKind.includes("panduan")
                              ? "guide"
                              : catKind.includes("laporan")
                                ? "report"
                                : "contract"
                      }`}
                    >
                      {doc.category}
                    </span>
                  </td>

                  <td className="doc-col-author">
                    <div className="doc-author-wrap">
                      <div className="doc-author-avatar">{doc.authorInitials || "AS"}</div>
                      <span className="doc-author-name">{doc.authorName || "Andi Setiawan"}</span>
                    </div>
                  </td>

                  <td className="doc-col-date">
                    <div className="doc-date-wrap">
                      <span className="doc-date">{doc.lastModifiedDate || "10 Sep 2026"}</span>
                      <span className="doc-time">{doc.lastModifiedTime || "14.32 WIB"}</span>
                    </div>
                  </td>

                  <td className="doc-col-action">
                    <button
                      className="alos-doc-btn-more"
                      onClick={(e) => {
                        e.stopPropagation();
                      }}
                      type="button"
                      aria-label="Opsi Dokumen"
                    >
                      ···
                    </button>
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="alos-doc-empty-table">
                  Tidak ada dokumen yang cocok dengan filter yang dipilih.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DocumentDetailAiPanel({
  doc,
  onAskAra,
}: {
  doc: DocumentItemViewModel;
  onAskAra: (prompt?: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<"ai" | "detail" | "versions">("ai");

  return (
    <div className="alos-doc-detail-card" aria-label="Rincian Dokumen & Ringkasan AI">
      {/* Header */}
      <div className="alos-doc-detail-header">
        <div className="alos-doc-detail-head-top">
          <div className={`doc-type-badge large ${doc.fileType || "pdf"}`}>
            {doc.fileType === "doc" ? "DOC" : "PDF"}
          </div>
          <div className="alos-doc-detail-titles">
            <h3 className="alos-doc-detail-title">{doc.fileName || doc.title}</h3>
            <div className="alos-doc-detail-meta">
              <span>{doc.category}</span>
              <span className="dot">•</span>
              <span>{doc.fileSize || "2.4 MB"}</span>
              <span className="dot">•</span>
              <span>Diubah {doc.lastModifiedDate || "10 Sep 2026"}</span>
            </div>
          </div>
          <button className="alos-doc-detail-close" type="button" aria-label="Tutup Rincian">
            ✕
          </button>
        </div>

        {/* Sub-Tabs */}
        <div className="alos-doc-detail-tabs" role="tablist">
          <button
            className={`alos-doc-detail-tab ${activeTab === "ai" ? "active" : ""}`}
            onClick={() => setActiveTab("ai")}
            role="tab"
            aria-selected={activeTab === "ai"}
            type="button"
          >
            Ringkasan AI
          </button>
          <button
            className={`alos-doc-detail-tab ${activeTab === "detail" ? "active" : ""}`}
            onClick={() => setActiveTab("detail")}
            role="tab"
            aria-selected={activeTab === "detail"}
            type="button"
          >
            Detail
          </button>
          <button
            className={`alos-doc-detail-tab ${activeTab === "versions" ? "active" : ""}`}
            onClick={() => setActiveTab("versions")}
            role="tab"
            aria-selected={activeTab === "versions"}
            type="button"
          >
            Versi ({doc.versionsCount || 3})
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="alos-doc-detail-body">
        {activeTab === "ai" && (
          <>
            {/* Box 1: Ringkasan oleh ARA */}
            <div className="alos-doc-ai-box">
              <div className="alos-doc-ai-box-head">
                <svg fill="none" height="18" stroke="#eab308" viewBox="0 0 24 24" width="18">
                  <path
                    d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"
                    fill="#eab308"
                    stroke="#eab308"
                    strokeWidth="1.5"
                  />
                </svg>
                <h4>Ringkasan oleh ARA</h4>
              </div>
              <p className="alos-doc-ai-paragraph">{doc.aiSummary}</p>
            </div>

            {/* Box 2: Poin Penting */}
            <div className="alos-doc-keypoints-box">
              <h4 className="alos-doc-keypoints-title">Poin Penting</h4>
              <ul className="alos-doc-keypoints-list">
                {(doc.keyPoints || defaultReferenceDocuments[0].keyPoints!).map(
                  (pt, idx) => (
                    <li key={idx}>{pt}</li>
                  ),
                )}
              </ul>
            </div>

            {/* AI Action Buttons */}
            <div className="alos-doc-ai-actions-row">
              <button
                className="alos-doc-btn-ai-action primary"
                onClick={() => onAskAra("Jelaskan implementasi kebijakan ini")}
                type="button"
              >
                <svg fill="none" height="16" stroke="#047857" viewBox="0 0 24 24" width="16">
                  <path
                    d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"
                    fill="#047857"
                    stroke="#047857"
                    strokeWidth="1.5"
                  />
                </svg>
                <span>Tanyakan ke ARA</span>
              </button>

              <button
                className="alos-doc-btn-ai-action secondary"
                onClick={() => onAskAra("Buat ringkasan lebih detail")}
                type="button"
              >
                <svg fill="none" height="16" stroke="#334155" viewBox="0 0 24 24" width="16">
                  <path
                    d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" strokeLinecap="round" strokeWidth="1.8" />
                </svg>
                <span>Buat Ringkasan Lebih Detail</span>
              </button>
            </div>

            {/* Section: Informasi Dokumen */}
            <div className="alos-doc-info-section">
              <h4 className="alos-doc-info-heading">Informasi Dokumen</h4>
              <div className="alos-doc-info-grid">
                <div className="info-item">
                  <span className="info-label">Nama File</span>
                  <span className="info-value bold">{doc.fileName || doc.title}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Kategori</span>
                  <span className="info-value">{doc.category}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Ukuran</span>
                  <span className="info-value">{doc.fileSize || "2.4 MB"}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Dibuat Oleh</span>
                  <span className="info-value">{doc.authorName || "Andi Setiawan"}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Tanggal Dibuat</span>
                  <span className="info-value">{doc.createdDate || "1 Sep 2026, 09.00 WIB"}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Terakhir Diubah</span>
                  <span className="info-value">
                    {doc.lastModifiedDate}, {doc.lastModifiedTime}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Lokasi</span>
                  <span className="info-value">{doc.location || "IT Operations / Kebijakan"}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Akses</span>
                  <span className="info-value">{doc.accessLevel || "Internal"}</span>
                </div>
              </div>
            </div>

            {/* Section: Tag */}
            <div className="alos-doc-tags-section">
              <h4 className="alos-doc-tags-heading">Tag</h4>
              <div className="alos-doc-tags-list">
                {(doc.tags || ["keamanan", "informasi", "kebijakan", "iso27001"]).map(
                  (tag, idx) => (
                    <span className="alos-doc-tag-pill" key={idx}>
                      {tag}
                    </span>
                  ),
                )}
                <button className="alos-doc-btn-add-tag" type="button">
                  + Tambah Tag
                </button>
              </div>
            </div>
          </>
        )}

        {activeTab === "detail" && (
          <div className="alos-doc-detail-tab-content">
            <h4 className="alos-doc-info-heading">Pemeriksaan &amp; Kepatuhan</h4>
            <div className="alos-doc-checklist">
              <div className="checklist-item done">
                <span className="check-icon">✓</span>
                <div>
                  <strong>Klasifikasi Data Terverifikasi</strong>
                  <span>Sesuai standar penanganan data internal perusahaan.</span>
                </div>
              </div>
              <div className="checklist-item done">
                <span className="check-icon">✓</span>
                <div>
                  <strong>Audit Log SHA-256 Valid</strong>
                  <span>Integritas hash file konsisten dengan riwayat repositori.</span>
                </div>
              </div>
              <div className="checklist-item done">
                <span className="check-icon">✓</span>
                <div>
                  <strong>Persetujuan Lead Divisi</strong>
                  <span>Telah ditinjau dan disetujui untuk rilis staging.</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "versions" && (
          <div className="alos-doc-versions-tab-content">
            <h4 className="alos-doc-info-heading">Riwayat Versi Dokumen</h4>
            <div className="alos-doc-version-list">
              <div className="version-item active">
                <div className="version-badge">v2.0 (Terkini)</div>
                <div className="version-info">
                  <strong>Pembaruan klausul insiden keamanan ISO 27001</strong>
                  <span>Diubah oleh Andi Setiawan • 10 Sep 2026, 14.32 WIB</span>
                </div>
              </div>
              <div className="version-item">
                <div className="version-badge">v1.1</div>
                <div className="version-info">
                  <strong>Penyesuaian klasifikasi data internal</strong>
                  <span>Diubah oleh Siti Rahma • 15 Agu 2026, 10.00 WIB</span>
                </div>
              </div>
              <div className="version-item">
                <div className="version-badge">v1.0</div>
                <div className="version-info">
                  <strong>Rilis inisial kebijakan</strong>
                  <span>Diubah oleh Andi Setiawan • 1 Sep 2026, 09.00 WIB</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function UploadDocumentModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (
    name: string,
    category: string,
    classification: string,
    description: string,
  ) => void | Promise<void>;
}) {
  const [docName, setDocName] = useState("");
  const [category, setCategory] = useState("Kebijakan");
  const [classification, setClassification] = useState("INTERNAL");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docName.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(docName.trim(), category, classification, description.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="alos-modal-backdrop" role="dialog" aria-modal="true">
      <div className="alos-modal-dialog">
        <div className="alos-modal-header">
          <div>
            <p className="alos-dash-kicker">MANAJEMEN PENGETAHUAN</p>
            <h2 className="alos-modal-title">Unggah Dokumen Baru</h2>
          </div>
          <button
            className="alos-modal-close-btn"
            onClick={onClose}
            type="button"
            aria-label="Tutup modal"
          >
            ✕
          </button>
        </div>

        <form className="alos-modal-form" onSubmit={handleSubmit}>
          {/* File Drop Zone Mock */}
          <div className="alos-doc-dropzone">
            <svg fill="none" height="32" stroke="#10b981" viewBox="0 0 24 24" width="32">
              <path
                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.8"
              />
            </svg>
            <p className="dropzone-title">Tarik &amp; lepas file dokumen ke sini, atau klik untuk memilih file</p>
            <span className="dropzone-hint">Mendukung PDF, DOCX, XLSX, max 25MB</span>
          </div>

          <div className="alos-form-group">
            <label className="alos-form-label" htmlFor="doc-name-input">
              Nama Dokumen *
            </label>
            <input
              className="alos-form-input"
              id="doc-name-input"
              onChange={(e) => setDocName(e.target.value)}
              placeholder="Contoh: Kebijakan Operasional Tim IT 2026.pdf"
              required
              value={docName}
            />
          </div>

          <div className="alos-form-row-2">
            <div className="alos-form-group">
              <label className="alos-form-label" htmlFor="doc-cat-select">
                Kategori
              </label>
              <select
                className="alos-form-select"
                id="doc-cat-select"
                onChange={(e) => setCategory(e.target.value)}
                value={category}
              >
                <option value="Kebijakan">Kebijakan</option>
                <option value="SOP">SOP</option>
                <option value="Panduan">Panduan</option>
                <option value="Laporan">Laporan</option>
                <option value="Kontrak">Kontrak</option>
                <option value="Lainnya">Lainnya</option>
              </select>
            </div>

            <div className="alos-form-group">
              <label className="alos-form-label" htmlFor="doc-class-select">
                Klasifikasi Akses
              </label>
              <select
                className="alos-form-select"
                id="doc-class-select"
                onChange={(e) => setClassification(e.target.value)}
                value={classification}
              >
                <option value="INTERNAL">Internal</option>
                <option value="PUBLIC">Publik</option>
                <option value="CONFIDENTIAL">Rahasia (Confidential)</option>
                <option value="RESTRICTED">Sangat Rahasia (Restricted)</option>
              </select>
            </div>
          </div>

          <div className="alos-form-group">
            <label className="alos-form-label" htmlFor="doc-desc-input">
              Deskripsi Singkat
            </label>
            <textarea
              className="alos-form-textarea"
              id="doc-desc-input"
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Jelaskan secara singkat isi dan tujuan dokumen ini..."
              rows={3}
              value={description}
            />
          </div>

          <div className="alos-modal-footer">
            <button className="alos-btn-secondary" onClick={onClose} type="button">
              Batal
            </button>
            <button
              className="alos-btn-primary"
              disabled={submitting || !docName.trim()}
              type="submit"
            >
              {submitting ? "Mengunggah…" : "Unggah Dokumen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

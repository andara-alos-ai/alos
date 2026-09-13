"use client";

import { useState, useMemo, type FormEvent } from "react";
import type { SessionActor } from "@/lib/governance";
import type { Finding, OperationalDashboard } from "@/lib/operational";

export type FindingItem = {
  id: string;
  code: string;
  title: string;
  description: string;
  category: "Keamanan" | "Proses" | "Infrastruktur" | "Akses" | "Kepatuhan" | "SDM" | "Monitoring" | string;
  priority: "Kritis" | "Tinggi" | "Sedang" | "Rendah";
  status: "Open" | "In Progress" | "Resolved";
  owner: {
    initials: string;
    name: string;
    division: string;
  };
  dueDate: string;
  dueText?: string;
  isOverdueOrNear?: boolean;
  attachmentCount: number;
  impactAnalysis?: string;
  riskLevel?: "Kritis" | "Tinggi" | "Sedang" | "Rendah";
  impactArea?: string;
  sourceKind?: string;
  divisionRelated?: string;
  createdAt?: string;
  evidences?: Array<{
    name: string;
    size: string;
    date: string;
  }>;
  actionPlans?: Array<{
    title: string;
    status: "Selesai" | "Sedang Berjalan" | "Menunggu";
    targetDate: string;
  }>;
  activities?: Array<{
    timestamp: string;
    actor: string;
    description: string;
  }>;
};

export const INITIAL_FINDINGS: FindingItem[] = [
  {
    id: "f-1",
    code: "TMN-2026-001",
    title: "Akses sistem tanpa MFA",
    description: "Ditemukan beberapa akun pengguna dengan hak akses sistem kritikal yang belum mengaktifkan MFA.",
    category: "Keamanan",
    priority: "Kritis",
    status: "Open",
    owner: {
      initials: "AW",
      name: "Adi Wibowo",
      division: "IT Operations",
    },
    dueDate: "12 Sep 2026",
    dueText: "12 Sep 2026 (2 hari lagi)",
    isOverdueOrNear: true,
    attachmentCount: 3,
    impactAnalysis:
      "Tidak digunakannya MFA pada akun dengan hak akses tinggi meningkatkan risiko akses tidak sah, potensi kebocoran data, dan pelanggaran terhadap kebijakan keamanan informasi perusahaan.",
    riskLevel: "Tinggi",
    impactArea: "Keamanan, Data, Operasional",
    sourceKind: "Internal Audit",
    divisionRelated: "IT Operations",
    createdAt: "5 Sep 2026, 10.24 WIB",
    evidences: [
      { name: "daftar-akun-tanpa-mfa.xlsx", size: "245 KB", date: "5 Sep 2026" },
      { name: "hasil-audit-akses.pdf", size: "1.2 MB", date: "5 Sep 2026" },
      { name: "tangkapan-layar.png", size: "980 KB", date: "5 Sep 2026" },
    ],
    actionPlans: [
      { title: "Identifikasi akun-akun privileged yang belum mengaktifkan MFA", status: "Selesai", targetDate: "7 Sep 2026" },
      { title: "Kirimkan instruksi aktivasi dan panduan setup autentikator", status: "Sedang Berjalan", targetDate: "10 Sep 2026" },
      { title: "Enforce policy MFA wajib pada IdP/SSO untuk seluruh level admin", status: "Menunggu", targetDate: "12 Sep 2026" },
    ],
    activities: [
      { timestamp: "5 Sep 2026, 10.24 WIB", actor: "Internal Audit", description: "Temuan dicatat oleh Tim Internal Audit." },
      { timestamp: "6 Sep 2026, 09.15 WIB", actor: "Adi Wibowo", description: "Temuan diakui dan siap ditindaklanjuti." },
      { timestamp: "8 Sep 2026, 11.00 WIB", actor: "Adi Wibowo", description: "Dokumen bukti hasil-audit-akses.pdf diunggah." },
    ],
  },
  {
    id: "f-2",
    code: "TMN-2026-002",
    title: "Dokumentasi perubahan tidak lengkap",
    description: "Catatan perubahan pada sistem produksi tidak menyertakan approval formal dan rollback plan.",
    category: "Proses",
    priority: "Tinggi",
    status: "In Progress",
    owner: {
      initials: "SR",
      name: "Sari Rahma",
      division: "IT Operations",
    },
    dueDate: "20 Sep 2026",
    dueText: "20 Sep 2026",
    isOverdueOrNear: false,
    attachmentCount: 1,
    impactAnalysis: "Kurangnya dokumentasi dan rencana rollback meningkatkan risiko downtime berkepanjangan saat deployment.",
    riskLevel: "Tinggi",
    impactArea: "Operasional, Kepatuhan",
    sourceKind: "Review Operasional",
    divisionRelated: "IT Operations",
    createdAt: "6 Sep 2026, 14.10 WIB",
    evidences: [{ name: "form-perubahan-sistem.pdf", size: "640 KB", date: "6 Sep 2026" }],
  },
  {
    id: "f-3",
    code: "TMN-2026-003",
    title: "Backup data tidak sesuai jadwal",
    description: "Pencadangan basis data mingguan mengalami keterlambatan eksekusi hingga 14 jam dari jendela pemeliharaan.",
    category: "Infrastruktur",
    priority: "Tinggi",
    status: "Open",
    owner: {
      initials: "DN",
      name: "Deni Nugroho",
      division: "Infrastructure",
    },
    dueDate: "18 Sep 2026",
    dueText: "18 Sep 2026",
    isOverdueOrNear: false,
    attachmentCount: 2,
    impactAnalysis: "Keterlambatan snapshot berpotensi memperbesar RPO (Recovery Point Objective) jika terjadi kegagalan hardware.",
    riskLevel: "Tinggi",
    impactArea: "Infrastruktur, Data",
    sourceKind: "Sistem Monitoring",
    divisionRelated: "Infrastructure",
    createdAt: "4 Sep 2026, 08.45 WIB",
    evidences: [
      { name: "log-backup-database.log", size: "3.1 MB", date: "4 Sep 2026" },
      { name: "storage-capacity-report.pdf", size: "820 KB", date: "4 Sep 2026" },
    ],
  },
  {
    id: "f-4",
    code: "TMN-2026-004",
    title: "Hak akses berlebih pada akun vendor",
    description: "Akun pihak ketiga memiliki hak administrasi di luar lingkup kontrak kerja aktif.",
    category: "Akses",
    priority: "Sedang",
    status: "In Progress",
    owner: {
      initials: "RT",
      name: "Rudi Tantra",
      division: "IT Operations",
    },
    dueDate: "25 Sep 2026",
    dueText: "25 Sep 2026",
    isOverdueOrNear: false,
    attachmentCount: 4,
    impactAnalysis: "Potensi penyalahgunaan wewenang dan akses ke data sensitif yang tidak relevan dengan SLA vendor.",
    riskLevel: "Sedang",
    impactArea: "Keamanan, Tata Kelola",
    sourceKind: "Internal Audit",
    divisionRelated: "IT Operations",
    createdAt: "3 Sep 2026, 16.30 WIB",
    evidences: [
      { name: "kontrak-vendor-nda.pdf", size: "1.8 MB", date: "3 Sep 2026" },
      { name: "matrix-akses-rbac.xlsx", size: "410 KB", date: "3 Sep 2026" },
    ],
  },
  {
    id: "f-5",
    code: "TMN-2026-005",
    title: "Lisensi software tidak termonitor",
    description: "Inventaris lisensi software development belum terdata secara terpusat dan berisiko penalti kepatuhan.",
    category: "Kepatuhan",
    priority: "Sedang",
    status: "Open",
    owner: {
      initials: "PL",
      name: "Putri Lestari",
      division: "Procurement",
    },
    dueDate: "28 Sep 2026",
    dueText: "28 Sep 2026",
    isOverdueOrNear: false,
    attachmentCount: 1,
    impactAnalysis: "Risiko ketidaksesuaian lisensi saat audit software vendor dan inefisiensi pengadaan aset digital.",
    riskLevel: "Sedang",
    impactArea: "Keuangan, Kepatuhan",
    sourceKind: "Internal Review",
    divisionRelated: "Procurement",
    createdAt: "2 Sep 2026, 11.15 WIB",
    evidences: [{ name: "daftar-software-aktiva.xlsx", size: "512 KB", date: "2 Sep 2026" }],
  },
  {
    id: "f-6",
    code: "TMN-2026-006",
    title: "Perangkat end-of-life masih aktif",
    description: "Ditemukan 3 switch network yang sudah melewati masa garansi dan dukungan pembaruan pabrikan.",
    category: "Infrastruktur",
    priority: "Rendah",
    status: "Resolved",
    owner: {
      initials: "BS",
      name: "Bima Santoso",
      division: "IT Operations",
    },
    dueDate: "30 Sep 2026",
    dueText: "30 Sep 2026",
    isOverdueOrNear: false,
    attachmentCount: 1,
    impactAnalysis: "Perangkat tanpa firmware update rentan terhadap eksploitasi celah keamanan baru.",
    riskLevel: "Rendah",
    impactArea: "Infrastruktur",
    sourceKind: "Audit Fisik",
    divisionRelated: "IT Operations",
    createdAt: "1 Sep 2026, 13.00 WIB",
    evidences: [{ name: "berita-acara-penggantian-switch.pdf", size: "750 KB", date: "1 Sep 2026" }],
  },
  {
    id: "f-7",
    code: "TMN-2026-007",
    title: "Pelatihan keamanan belum merata",
    description: "Partisipasi sosialisasi awareness phishing kuartal 3 belum mencapai target minimum 80%.",
    category: "SDM",
    priority: "Rendah",
    status: "In Progress",
    owner: {
      initials: "DN",
      name: "Dewi Nurul",
      division: "Human Capital",
    },
    dueDate: "10 Okt 2026",
    dueText: "10 Okt 2026",
    isOverdueOrNear: false,
    attachmentCount: 2,
    impactAnalysis: "Kurangnya pemahaman pegawai meningkatkan kerentanan terhadap social engineering attack.",
    riskLevel: "Rendah",
    impactArea: "SDM, Budaya Keamanan",
    sourceKind: "HR Audit",
    divisionRelated: "Human Capital",
    createdAt: "30 Ags 2026, 09.30 WIB",
    evidences: [{ name: "rekap-kehadiran-training.xlsx", size: "380 KB", date: "30 Ags 2026" }],
  },
  {
    id: "f-8",
    code: "TMN-2026-008",
    title: "Monitoring log belum optimal",
    description: "Aggregator log belum mengindeks alert kegagalan autentikasi secara realtime dan terpusat.",
    category: "Monitoring",
    priority: "Kritis",
    status: "Open",
    owner: {
      initials: "AW",
      name: "Adi Wibowo",
      division: "IT Operations",
    },
    dueDate: "15 Sep 2026",
    dueText: "15 Sep 2026",
    isOverdueOrNear: true,
    attachmentCount: 3,
    impactAnalysis: "Keterlambatan deteksi insiden keamanan cyber (Mean Time to Detect) berpotensi memperparah dampak serangan.",
    riskLevel: "Kritis",
    impactArea: "Keamanan, Operasional",
    sourceKind: "SOC Evaluation",
    divisionRelated: "IT Operations",
    createdAt: "7 Sep 2026, 17.20 WIB",
    evidences: [
      { name: "siem-coverage-matrix.pdf", size: "1.4 MB", date: "7 Sep 2026" },
      { name: "incident-simulation-log.json", size: "880 KB", date: "7 Sep 2026" },
    ],
  },
];

export type FindingViewsProps = {
  actor?: SessionActor;
  operational?: OperationalDashboard | null;
  findings?: Finding[];
  onCreateFinding?: (data: {
    title: string;
    description: string;
    severity: string;
    category: string;
    dueDate?: string;
  }) => Promise<void>;
  onUpdateStatus?: (findingId: string, status: string, resolution?: string) => Promise<void>;
  onDeleteFinding?: (findingId: string) => Promise<void>;
};

export function FindingViews({
  actor,
  findings: backendFindings,
  onCreateFinding,
  onUpdateStatus,
}: FindingViewsProps) {
  // Merge backend findings or fallback to rich mock
  const [localFindings, setLocalFindings] = useState<FindingItem[]>(INITIAL_FINDINGS);
  const [selectedFindingId, setSelectedFindingId] = useState<string>("f-1");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("Semua Kategori");
  const [selectedStatus, setSelectedStatus] = useState("Semua Status");
  const [selectedDivision, setSelectedDivision] = useState("Semua Divisi");
  const [selectedSource, setSelectedSource] = useState("Semua Sumber");
  const [selectedPeriod, setSelectedPeriod] = useState("Semua Periode");
  const [activeTab, setActiveTab] = useState<"analisis" | "rencana" | "aktivitas">("analisis");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isActionModalOpen, setIsActionModalOpen] = useState(false);
  const [checkedIds, setCheckedIds] = useState<Record<string, boolean>>({});

  // Merge backend findings if available
  const allFindings = useMemo(() => {
    if (!backendFindings || backendFindings.length === 0) {
      return localFindings;
    }
    const mappedBackend: FindingItem[] = backendFindings.map((f, idx) => {
      const existing = localFindings.find((lf) => lf.id === f.finding_id);
      if (existing) return existing;
      const priorityMap: Record<string, "Kritis" | "Tinggi" | "Sedang" | "Rendah"> = {
        CRITICAL: "Kritis",
        HIGH: "Tinggi",
        MEDIUM: "Sedang",
        LOW: "Rendah",
      };
      const statusMap: Record<string, "Open" | "In Progress" | "Resolved"> = {
        OPEN: "Open",
        ACKNOWLEDGED: "In Progress",
        IN_PROGRESS: "In Progress",
        RESOLVED: "Resolved",
        DISMISSED: "Resolved",
      };
      return {
        id: f.finding_id,
        code: `TMN-2026-${String(idx + 1).padStart(3, "0")}`,
        title: f.title,
        description: f.description,
        category: "Keamanan",
        priority: priorityMap[f.severity] ?? "Sedang",
        status: statusMap[f.status] ?? "Open",
        owner: {
          initials: "IT",
          name: actor?.user_id ?? "IT Lead",
          division: "IT Operations",
        },
        dueDate: f.due_date ? f.due_date.slice(0, 10) : "20 Sep 2026",
        dueText: f.due_date ? f.due_date.slice(0, 10) : "20 Sep 2026",
        attachmentCount: 1,
        impactAnalysis: f.recommendation || f.description,
        riskLevel: priorityMap[f.severity] ?? "Sedang",
        impactArea: "Operasional, Keamanan",
        sourceKind: f.source_kind || "GENESIS",
        divisionRelated: f.division_code || "IT Operations",
        createdAt: f.created_at.slice(0, 10),
        evidences: [{ name: "dokumen-pendukung.pdf", size: "520 KB", date: f.created_at.slice(0, 10) }],
      };
    });
    return mappedBackend;
  }, [backendFindings, localFindings, actor]);

  // Filtered findings
  const filteredFindings = useMemo(() => {
    return allFindings.filter((item) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const match =
          item.title.toLowerCase().includes(q) ||
          item.code.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q) ||
          item.owner.name.toLowerCase().includes(q);
        if (!match) return false;
      }
      if (selectedCategory !== "Semua Kategori" && item.category !== selectedCategory) {
        return false;
      }
      if (selectedStatus !== "Semua Status" && item.status !== selectedStatus) {
        return false;
      }
      if (selectedDivision !== "Semua Divisi" && item.owner.division !== selectedDivision) {
        return false;
      }
      if (selectedSource !== "Semua Sumber" && item.sourceKind !== selectedSource) {
        return false;
      }
      return true;
    });
  }, [allFindings, searchQuery, selectedCategory, selectedStatus, selectedDivision, selectedSource]);

  // Selected item
  const selectedFinding = useMemo(() => {
    return allFindings.find((f) => f.id === selectedFindingId) ?? allFindings[0];
  }, [allFindings, selectedFindingId]);

  // KPI calculations
  const kpi = useMemo(() => {
    return {
      kritis: 8,
      tinggi: 14,
      sedang: 11,
      rendah: 6,
      total: 39,
    };
  }, []);

  // Checkbox toggle
  const toggleCheck = (id: string) => {
    setCheckedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleAll = () => {
    const allChecked = filteredFindings.every((f) => checkedIds[f.id]);
    const next: Record<string, boolean> = {};
    if (!allChecked) {
      filteredFindings.forEach((f) => {
        next[f.id] = true;
      });
    }
    setCheckedIds(next);
  };

  // Handle create finding
  const handleSaveFinding = async (data: {
    title: string;
    description: string;
    category: string;
    priority: "Kritis" | "Tinggi" | "Sedang" | "Rendah";
    sourceKind: string;
    dueDate: string;
  }) => {
    const newId = `f-${Date.now()}`;
    const newCode = `TMN-2026-${String(allFindings.length + 1).padStart(3, "0")}`;
    const newItem: FindingItem = {
      id: newId,
      code: newCode,
      title: data.title,
      description: data.description,
      category: data.category,
      priority: data.priority,
      status: "Open",
      owner: {
        initials: "IT",
        name: actor?.user_id ?? "IT Lead",
        division: "IT Operations",
      },
      dueDate: data.dueDate,
      dueText: data.dueDate,
      attachmentCount: 0,
      impactAnalysis: data.description,
      riskLevel: data.priority,
      impactArea: "Operasional, Keamanan",
      sourceKind: data.sourceKind,
      divisionRelated: "IT Operations",
      createdAt: "10 Sep 2026, 15.00 WIB",
      evidences: [],
      actionPlans: [],
      activities: [
        {
          timestamp: "10 Sep 2026, 15.00 WIB",
          actor: actor?.user_id ?? "IT Lead",
          description: "Temuan baru berhasil dicatat ke sistem.",
        },
      ],
    };

    setLocalFindings((prev) => [newItem, ...prev]);
    setSelectedFindingId(newId);
    setIsCreateModalOpen(false);

    if (onCreateFinding) {
      const severityMap: Record<string, string> = {
        Kritis: "CRITICAL",
        Tinggi: "HIGH",
        Sedang: "MEDIUM",
        Rendah: "LOW",
      };
      await onCreateFinding({
        title: data.title,
        description: data.description,
        severity: severityMap[data.priority] ?? "MEDIUM",
        category: data.category,
        dueDate: data.dueDate,
      });
    }
  };

  // Handle update status / action
  const handleUpdateFindingStatus = async (status: "Open" | "In Progress" | "Resolved", note?: string) => {
    if (!selectedFinding) return;
    setLocalFindings((prev) =>
      prev.map((f) =>
        f.id === selectedFinding.id
          ? {
              ...f,
              status,
              activities: [
                ...(f.activities ?? []),
                {
                  timestamp: "10 Sep 2026, 15.05 WIB",
                  actor: actor?.user_id ?? "IT Lead",
                  description: `Status temuan diperbarui menjadi ${status}. ${note ?? ""}`,
                },
              ],
            }
          : f,
      ),
    );
    setIsActionModalOpen(false);

    if (onUpdateStatus) {
      const beStatusMap: Record<string, string> = {
        Open: "OPEN",
        "In Progress": "ACKNOWLEDGED",
        Resolved: "RESOLVED",
      };
      await onUpdateStatus(selectedFinding.id, beStatusMap[status] ?? "ACKNOWLEDGED", note);
    }
  };

  return (
    <div className="alos-find-container">
      {/* Hero Header */}
      <div className="alos-find-hero">
        <div className="alos-find-hero-left">
          <h1 className="alos-find-title">Temuan</h1>
          <p className="alos-find-subtitle">
            Pantau, analisis, dan tindak lanjuti temuan dari audit, review, dan operasional.
          </p>
        </div>
        <button
          className="alos-find-btn-primary"
          id="btn-catat-temuan-baru"
          onClick={() => setIsCreateModalOpen(true)}
          type="button"
        >
          <span className="alos-find-plus-icon">+</span> Catat Temuan Baru
        </button>
      </div>

      {/* KPI Cards Row (5 Severity Cards) */}
      <div className="alos-find-kpi-row">
        {/* Kritis */}
        <div className="alos-find-kpi-card kritis" onClick={() => setSelectedCategory("Semua Kategori")}>
          <div className="alos-find-kpi-top">
            <span className="alos-find-kpi-val">{kpi.kritis}</span>
            <span className="alos-find-kpi-chevron">›</span>
          </div>
          <div className="alos-find-kpi-label">Kritis</div>
          <div className="alos-find-kpi-sub">Perlu segera ditindaklanjuti</div>
        </div>

        {/* Tinggi */}
        <div className="alos-find-kpi-card tinggi" onClick={() => setSelectedCategory("Semua Kategori")}>
          <div className="alos-find-kpi-top">
            <span className="alos-find-kpi-val">{kpi.tinggi}</span>
            <span className="alos-find-kpi-chevron">›</span>
          </div>
          <div className="alos-find-kpi-label">Tinggi</div>
          <div className="alos-find-kpi-sub">Dalam proses penanganan</div>
        </div>

        {/* Sedang */}
        <div className="alos-find-kpi-card sedang" onClick={() => setSelectedCategory("Semua Kategori")}>
          <div className="alos-find-kpi-top">
            <span className="alos-find-kpi-val">{kpi.sedang}</span>
            <span className="alos-find-kpi-chevron">›</span>
          </div>
          <div className="alos-find-kpi-label">Sedang</div>
          <div className="alos-find-kpi-sub">Dalam pemantauan</div>
        </div>

        {/* Rendah */}
        <div className="alos-find-kpi-card rendah" onClick={() => setSelectedCategory("Semua Kategori")}>
          <div className="alos-find-kpi-top">
            <span className="alos-find-kpi-val">{kpi.rendah}</span>
            <span className="alos-find-kpi-chevron">›</span>
          </div>
          <div className="alos-find-kpi-label">Rendah</div>
          <div className="alos-find-kpi-sub">Sudah ditangani</div>
        </div>

        {/* Total Temuan */}
        <div className="alos-find-kpi-card total" onClick={() => setSelectedCategory("Semua Kategori")}>
          <div className="alos-find-kpi-top">
            <span className="alos-find-kpi-val">{kpi.total}</span>
          </div>
          <div className="alos-find-kpi-label">Total Temuan</div>
          <div className="alos-find-kpi-sub">Seluruh periode</div>
        </div>
      </div>

      {/* Split Layout: Master Table (Left) + Detail Panel (Right) */}
      <div className="alos-find-split-layout">
        {/* Left Column: Filter + Table + Pagination */}
        <div className="alos-find-left-col">
          {/* Toolbar Filter */}
          <div className="alos-find-toolbar">
            <div className="alos-find-search-wrap">
              <svg className="alos-find-search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                <circle cx="11" cy="11" r="8" strokeWidth="2" />
                <path d="M21 21l-4.35-4.35" strokeLinecap="round" strokeWidth="2" />
              </svg>
              <input
                className="alos-find-search-input"
                id="search-temuan"
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Cari temuan..."
                type="search"
                value={searchQuery}
              />
            </div>

            <select
              aria-label="Filter Kategori"
              className="alos-find-select"
              onChange={(e) => setSelectedCategory(e.target.value)}
              value={selectedCategory}
            >
              <option>Semua Kategori</option>
              <option>Keamanan</option>
              <option>Proses</option>
              <option>Infrastruktur</option>
              <option>Akses</option>
              <option>Kepatuhan</option>
              <option>SDM</option>
              <option>Monitoring</option>
            </select>

            <select
              aria-label="Filter Status"
              className="alos-find-select"
              onChange={(e) => setSelectedStatus(e.target.value)}
              value={selectedStatus}
            >
              <option>Semua Status</option>
              <option>Open</option>
              <option>In Progress</option>
              <option>Resolved</option>
            </select>

            <select
              aria-label="Filter Divisi"
              className="alos-find-select"
              onChange={(e) => setSelectedDivision(e.target.value)}
              value={selectedDivision}
            >
              <option>Semua Divisi</option>
              <option>IT Operations</option>
              <option>Infrastructure</option>
              <option>Procurement</option>
              <option>Human Capital</option>
            </select>

            <select
              aria-label="Filter Sumber"
              className="alos-find-select"
              onChange={(e) => setSelectedSource(e.target.value)}
              value={selectedSource}
            >
              <option>Semua Sumber</option>
              <option>Internal Audit</option>
              <option>Review Operasional</option>
              <option>Sistem Monitoring</option>
              <option>Internal Review</option>
              <option>Audit Fisik</option>
              <option>HR Audit</option>
              <option>SOC Evaluation</option>
            </select>

            <select
              aria-label="Filter Periode"
              className="alos-find-select"
              onChange={(e) => setSelectedPeriod(e.target.value)}
              value={selectedPeriod}
            >
              <option>Semua Periode</option>
              <option>Bulan Ini</option>
              <option>Kuartal Ini</option>
              <option>Tahun Ini</option>
            </select>
          </div>

          {/* Master Table Card */}
          <div className="alos-find-table-card">
            <div className="alos-find-table-wrap">
              <table className="alos-find-table" id="table-temuan">
                <thead>
                  <tr>
                    <th style={{ width: "36px", paddingLeft: "14px" }}>
                      <input
                        aria-label="Pilih Semua"
                        checked={filteredFindings.length > 0 && filteredFindings.every((f) => checkedIds[f.id])}
                        onChange={toggleAll}
                        type="checkbox"
                      />
                    </th>
                    <th style={{ width: "30%" }}>Temuan</th>
                    <th style={{ width: "13%" }}>Kategori</th>
                    <th style={{ width: "12%" }}>Prioritas</th>
                    <th style={{ width: "12%" }}>Status</th>
                    <th style={{ width: "17%" }}>Pemilik</th>
                    <th style={{ width: "16%" }}>Target Selesai</th>
                    <th style={{ width: "40px", textAlign: "right", paddingRight: "14px" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFindings.map((item) => {
                    const isSelected = item.id === selectedFinding?.id;
                    const isChecked = !!checkedIds[item.id];
                    return (
                      <tr
                        className={`alos-find-tr ${isSelected ? "selected" : ""}`}
                        key={item.id}
                        onClick={() => setSelectedFindingId(item.id)}
                        tabIndex={0}
                      >
                        <td
                          onClick={(e) => e.stopPropagation()}
                          style={{ paddingLeft: "14px" }}
                        >
                          <input
                            aria-label={`Pilih ${item.title}`}
                            checked={isChecked}
                            onChange={() => toggleCheck(item.id)}
                            type="checkbox"
                          />
                        </td>
                        <td>
                          <div className="alos-find-cell-title">{item.title}</div>
                          <div className="alos-find-cell-code">{item.code}</div>
                        </td>
                        <td>
                          <span className="alos-find-cat-badge">{item.category}</span>
                        </td>
                        <td>
                          <span className={`alos-find-badge-prio ${item.priority.toLowerCase()}`}>
                            <span className="alos-find-dot" /> {item.priority}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`alos-find-badge-status ${
                              item.status === "Open"
                                ? "open"
                                : item.status === "In Progress"
                                  ? "progress"
                                  : "resolved"
                            }`}
                          >
                            <span className="alos-find-dot" /> {item.status}
                          </span>
                        </td>
                        <td>
                          <div className="alos-find-owner-wrap">
                            <div className="alos-find-avatar">{item.owner.initials}</div>
                            <div className="alos-find-owner-info">
                              <div className="alos-find-owner-name">{item.owner.name}</div>
                              <div className="alos-find-owner-div">{item.owner.division}</div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`alos-find-target-date ${item.isOverdueOrNear ? "urgent" : ""}`}>
                            {item.dueDate}
                          </span>
                        </td>
                        <td style={{ paddingRight: "14px", textAlign: "right" }}>
                          <div className="alos-find-actions-cell">
                            {item.attachmentCount > 0 && (
                              <span className="alos-find-clip">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="13" height="13">
                                  <path
                                    d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth="2"
                                  />
                                </svg>
                                {item.attachmentCount}
                              </span>
                            )}
                            <span className="alos-find-chevron-cell">›</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {filteredFindings.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "40px", color: "var(--alos-muted)" }}>
                        Tidak ada temuan yang sesuai dengan kriteria filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Footer */}
            <div className="alos-find-pagination-row">
              <span className="alos-find-page-summary">
                Menampilkan 1-{Math.min(8, filteredFindings.length)} dari 39 temuan
              </span>
              <div className="alos-find-page-controls">
                <button className="alos-find-page-btn" disabled type="button">
                  ‹
                </button>
                <button className="alos-find-page-btn active" type="button">
                  1
                </button>
                <button className="alos-find-page-btn" type="button">
                  2
                </button>
                <button className="alos-find-page-btn" type="button">
                  3
                </button>
                <button className="alos-find-page-btn" type="button">
                  4
                </button>
                <button className="alos-find-page-btn" type="button">
                  5
                </button>
                <button className="alos-find-page-btn" type="button">
                  ›
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Finding Detail Panel (~36%) */}
        {selectedFinding ? (
          <aside className="alos-find-detail-panel" id="panel-detail-temuan">
            {/* Header */}
            <div className="alos-find-detail-head">
              <div className="alos-find-detail-head-left">
                <span className={`alos-find-badge-prio ${selectedFinding.priority.toLowerCase()}`}>
                  <span className="alos-find-dot" /> {selectedFinding.priority}
                </span>
                <span className="alos-find-detail-code">{selectedFinding.code}</span>
              </div>
              <button
                aria-label="Tutup panel detail"
                className="alos-find-detail-close"
                onClick={() => setSelectedFindingId("")}
                type="button"
              >
                ✕
              </button>
            </div>

            {/* Title & Description */}
            <h2 className="alos-find-detail-title">{selectedFinding.title}</h2>
            <p className="alos-find-detail-desc">{selectedFinding.description}</p>

            {/* Detail Tabs */}
            <div className="alos-find-detail-tabs">
              <button
                className={`alos-find-tab-link ${activeTab === "analisis" ? "active" : ""}`}
                onClick={() => setActiveTab("analisis")}
                type="button"
              >
                Analisis
              </button>
              <button
                className={`alos-find-tab-link ${activeTab === "rencana" ? "active" : ""}`}
                onClick={() => setActiveTab("rencana")}
                type="button"
              >
                Rencana Tindak Lanjut
              </button>
              <button
                className={`alos-find-tab-link ${activeTab === "aktivitas" ? "active" : ""}`}
                onClick={() => setActiveTab("aktivitas")}
                type="button"
              >
                Aktivitas
              </button>
            </div>

            {/* Tab 1: Analisis */}
            {activeTab === "analisis" && (
              <div className="alos-find-tab-content">
                {/* Analisis & Dampak Card */}
                <div className="alos-find-impact-box">
                  <div className="alos-find-impact-header">
                    <svg className="alos-find-impact-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                      <path
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                      />
                    </svg>
                    <span className="alos-find-impact-title">Analisis &amp; Dampak</span>
                  </div>
                  <p className="alos-find-impact-text">
                    {selectedFinding.impactAnalysis ||
                      "Analisis mendalam mengenai temuan audit dan implikasinya terhadap tata kelola dan keberlangsungan sistem."}
                  </p>
                  <div className="alos-find-impact-subgrid">
                    <div className="alos-find-impact-item">
                      <div className="alos-find-impact-label">Tingkat Risiko</div>
                      <span className={`alos-find-badge-prio ${selectedFinding.priority.toLowerCase()}`}>
                        <span className="alos-find-dot" /> {selectedFinding.priority}
                      </span>
                    </div>
                    <div className="alos-find-impact-item">
                      <div className="alos-find-impact-label">Dampak Area</div>
                      <div className="alos-find-impact-val">{selectedFinding.impactArea || "Keamanan, Data, Operasional"}</div>
                    </div>
                  </div>
                </div>

                {/* 2-Column Metadata Grid */}
                <div className="alos-find-meta-grid">
                  <div className="alos-find-meta-col">
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Sumber Temuan</span>
                      <span className="alos-find-meta-val">{selectedFinding.sourceKind || "Internal Audit"}</span>
                    </div>
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Divisi Terkait</span>
                      <span className="alos-find-meta-val">{selectedFinding.divisionRelated || "IT Operations"}</span>
                    </div>
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Dibuat Pada</span>
                      <span className="alos-find-meta-val">{selectedFinding.createdAt || "5 Sep 2026, 10.24 WIB"}</span>
                    </div>
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Target Selesai</span>
                      <span className="alos-find-meta-val urgent">{selectedFinding.dueText || selectedFinding.dueDate}</span>
                    </div>
                  </div>

                  <div className="alos-find-meta-col">
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Pemilik</span>
                      <div className="alos-find-owner-wrap">
                        <div className="alos-find-avatar small">{selectedFinding.owner.initials}</div>
                        <div>
                          <div className="alos-find-owner-name small">{selectedFinding.owner.name}</div>
                          <div className="alos-find-owner-div small">{selectedFinding.owner.division}</div>
                        </div>
                      </div>
                    </div>
                    <div className="alos-find-meta-row">
                      <span className="alos-find-meta-label">Status</span>
                      <span
                        className={`alos-find-badge-status ${
                          selectedFinding.status === "Open"
                            ? "open"
                            : selectedFinding.status === "In Progress"
                              ? "progress"
                              : "resolved"
                        }`}
                      >
                        <span className="alos-find-dot" /> {selectedFinding.status}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Bukti Terkait Section */}
                <div className="alos-find-evidences-section">
                  <div className="alos-find-evidences-head">
                    <h3 className="alos-find-evidences-title">
                      Bukti Terkait ({selectedFinding.evidences?.length ?? selectedFinding.attachmentCount})
                    </h3>
                    <button className="alos-find-link-btn" type="button">
                      Lihat Semua →
                    </button>
                  </div>
                  <div className="alos-find-evidence-list">
                    {(selectedFinding.evidences && selectedFinding.evidences.length > 0
                      ? selectedFinding.evidences
                      : [
                          { name: "daftar-akun-tanpa-mfa.xlsx", size: "245 KB", date: "5 Sep 2026" },
                          { name: "hasil-audit-akses.pdf", size: "1.2 MB", date: "5 Sep 2026" },
                          { name: "tangkapan-layar.png", size: "980 KB", date: "5 Sep 2026" },
                        ]
                    ).map((doc, idx) => (
                      <div className="alos-find-evidence-item" key={idx}>
                        <div className="alos-find-evidence-left">
                          <span className="alos-find-doc-icon">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                              <path
                                d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                              />
                            </svg>
                          </span>
                          <div className="alos-find-evidence-info">
                            <div className="alos-find-evidence-name">{doc.name}</div>
                            <div className="alos-find-evidence-meta">
                              {doc.size} • {doc.date}
                            </div>
                          </div>
                        </div>
                        <button
                          aria-label={`Unduh ${doc.name}`}
                          className="alos-find-download-icon"
                          onClick={() => alert(`Mengunduh dokumen: ${doc.name}`)}
                          type="button"
                        >
                          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                            <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: Rencana Tindak Lanjut */}
            {activeTab === "rencana" && (
              <div className="alos-find-tab-content">
                <div className="alos-find-plan-list">
                  {(selectedFinding.actionPlans ?? [
                    { title: "Identifikasi akun-akun privileged yang belum mengaktifkan MFA", status: "Selesai", targetDate: "7 Sep 2026" },
                    { title: "Kirimkan instruksi aktivasi dan panduan setup autentikator", status: "Sedang Berjalan", targetDate: "10 Sep 2026" },
                    { title: "Enforce policy MFA wajib pada IdP/SSO untuk seluruh level admin", status: "Menunggu", targetDate: "12 Sep 2026" },
                  ]).map((step, idx) => (
                    <div className="alos-find-plan-item" key={idx}>
                      <div className="alos-find-plan-step-num">{idx + 1}</div>
                      <div className="alos-find-plan-body">
                        <div className="alos-find-plan-title">{step.title}</div>
                        <div className="alos-find-plan-meta">
                          <span
                            className={`alos-find-plan-status ${
                              step.status === "Selesai"
                                ? "done"
                                : step.status === "Sedang Berjalan"
                                  ? "doing"
                                  : "pending"
                            }`}
                          >
                            {step.status}
                          </span>
                          <span>Target: {step.targetDate}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tab 3: Aktivitas */}
            {activeTab === "aktivitas" && (
              <div className="alos-find-tab-content">
                <div className="alos-find-timeline">
                  {(selectedFinding.activities ?? [
                    { timestamp: "5 Sep 2026, 10.24 WIB", actor: "Internal Audit", description: "Temuan dicatat oleh Tim Internal Audit." },
                    { timestamp: "6 Sep 2026, 09.15 WIB", actor: "Adi Wibowo", description: "Temuan diakui dan siap ditindaklanjuti." },
                    { timestamp: "8 Sep 2026, 11.00 WIB", actor: "Adi Wibowo", description: "Dokumen bukti hasil-audit-akses.pdf diunggah." },
                  ]).map((act, idx) => (
                    <div className="alos-find-timeline-item" key={idx}>
                      <div className="alos-find-timeline-dot" />
                      <div className="alos-find-timeline-content">
                        <div className="alos-find-timeline-time">{act.timestamp}</div>
                        <div className="alos-find-timeline-actor">{act.actor}</div>
                        <div className="alos-find-timeline-desc">{act.description}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bottom CTA Button */}
            <button
              className="alos-find-cta-btn"
              id="btn-tindak-lanjut-temuan"
              onClick={() => setIsActionModalOpen(true)}
              type="button"
            >
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                <path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
              </svg>
              Tindak Lanjut Temuan
            </button>
          </aside>
        ) : (
          <aside className="alos-find-detail-panel empty">
            <div className="alos-find-empty-panel">Pilih temuan pada tabel untuk melihat detail analisis.</div>
          </aside>
        )}
      </div>

      {/* Modal Dialog: Catat Temuan Baru */}
      {isCreateModalOpen && (
        <CreateFindingModal
          onClose={() => setIsCreateModalOpen(false)}
          onSave={handleSaveFinding}
        />
      )}

      {/* Modal Dialog: Tindak Lanjut Temuan */}
      {isActionModalOpen && selectedFinding && (
        <ActionFindingModal
          finding={selectedFinding}
          onClose={() => setIsActionModalOpen(false)}
          onUpdateStatus={handleUpdateFindingStatus}
        />
      )}
    </div>
  );
}

function CreateFindingModal({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (data: {
    title: string;
    description: string;
    category: string;
    priority: "Kritis" | "Tinggi" | "Sedang" | "Rendah";
    sourceKind: string;
    dueDate: string;
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("Keamanan");
  const [priority, setPriority] = useState<"Kritis" | "Tinggi" | "Sedang" | "Rendah">("Tinggi");
  const [sourceKind, setSourceKind] = useState("Internal Audit");
  const [dueDate, setDueDate] = useState("2026-09-25");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      await onSave({
        title,
        description,
        category,
        priority,
        sourceKind,
        dueDate,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="alos-find-modal-backdrop" onClick={onClose}>
      <div className="alos-find-modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="alos-find-modal-head">
          <div>
            <p className="alos-find-modal-kicker">MANAJEMEN RISIKO</p>
            <h2 className="alos-find-modal-title">Catat Temuan Baru</h2>
          </div>
          <button className="alos-find-modal-close" onClick={onClose} type="button">
            ✕
          </button>
        </div>

        <form className="alos-find-modal-form" onSubmit={(e) => void handleSubmit(e)}>
          <div className="alos-find-form-group">
            <label htmlFor="f-title">Judul Temuan *</label>
            <input
              id="f-title"
              minLength={3}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Contoh: Akses server database tanpa enkripsi"
              required
              type="text"
              value={title}
            />
          </div>

          <div className="alos-find-form-row">
            <div className="alos-find-form-group">
              <label htmlFor="f-cat">Kategori</label>
              <select id="f-cat" onChange={(e) => setCategory(e.target.value)} value={category}>
                <option>Keamanan</option>
                <option>Proses</option>
                <option>Infrastruktur</option>
                <option>Akses</option>
                <option>Kepatuhan</option>
                <option>SDM</option>
                <option>Monitoring</option>
              </select>
            </div>

            <div className="alos-find-form-group">
              <label htmlFor="f-prio">Prioritas / Severitas</label>
              <select
                id="f-prio"
                onChange={(e) => setPriority(e.target.value as "Kritis" | "Tinggi" | "Sedang" | "Rendah")}
                value={priority}
              >
                <option>Kritis</option>
                <option>Tinggi</option>
                <option>Sedang</option>
                <option>Rendah</option>
              </select>
            </div>
          </div>

          <div className="alos-find-form-row">
            <div className="alos-find-form-group">
              <label htmlFor="f-src">Sumber Temuan</label>
              <select id="f-src" onChange={(e) => setSourceKind(e.target.value)} value={sourceKind}>
                <option>Internal Audit</option>
                <option>External Audit</option>
                <option>Review Operasional</option>
                <option>Sistem Monitoring</option>
                <option>GENESIS / AI</option>
              </select>
            </div>

            <div className="alos-find-form-group">
              <label htmlFor="f-due">Target Selesai</label>
              <input
                id="f-due"
                onChange={(e) => setDueDate(e.target.value)}
                type="date"
                value={dueDate}
              />
            </div>
          </div>

          <div className="alos-find-form-group">
            <label htmlFor="f-desc">Deskripsi &amp; Rekomendasi *</label>
            <textarea
              id="f-desc"
              minLength={5}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Rincikan detail kondisi temuan, dampak potensial, dan rekomendasi perbaikan..."
              required
              rows={4}
              value={description}
            />
          </div>

          <div className="alos-find-modal-footer">
            <button className="alos-find-btn-secondary" onClick={onClose} type="button">
              Batal
            </button>
            <button className="alos-find-btn-primary" disabled={saving} type="submit">
              {saving ? "Menyimpan…" : "Simpan Temuan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ActionFindingModal({
  finding,
  onClose,
  onUpdateStatus,
}: {
  finding: FindingItem;
  onClose: () => void;
  onUpdateStatus: (status: "Open" | "In Progress" | "Resolved", note?: string) => Promise<void>;
}) {
  const [selectedStatus, setSelectedStatus] = useState<"Open" | "In Progress" | "Resolved">(finding.status);
  const [actionNote, setActionNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onUpdateStatus(selectedStatus, actionNote);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="alos-find-modal-backdrop" onClick={onClose}>
      <div className="alos-find-modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="alos-find-modal-head">
          <div>
            <p className="alos-find-modal-kicker">TINDAK LANJUT OPERASIONAL</p>
            <h2 className="alos-find-modal-title">Tindak Lanjut Temuan</h2>
          </div>
          <button className="alos-find-modal-close" onClick={onClose} type="button">
            ✕
          </button>
        </div>

        <form className="alos-find-modal-form" onSubmit={(e) => void handleSubmit(e)}>
          <div className="alos-find-finding-summary-box">
            <div className="alos-find-summary-code">{finding.code}</div>
            <div className="alos-find-summary-title">{finding.title}</div>
            <div className="alos-find-summary-owner">Pemilik: {finding.owner.name} ({finding.owner.division})</div>
          </div>

          <div className="alos-find-form-group">
            <label htmlFor="f-act-status">Perbarui Status Temuan</label>
            <select
              id="f-act-status"
              onChange={(e) => setSelectedStatus(e.target.value as "Open" | "In Progress" | "Resolved")}
              value={selectedStatus}
            >
              <option value="Open">Open (Belum Selesai)</option>
              <option value="In Progress">In Progress (Dalam Penanganan)</option>
              <option value="Resolved">Resolved (Selesai &amp; Ditutup)</option>
            </select>
          </div>

          <div className="alos-find-form-group">
            <label htmlFor="f-act-note">Catatan Penanganan / Resolusi</label>
            <textarea
              id="f-act-note"
              onChange={(e) => setActionNote(e.target.value)}
              placeholder="Jelaskan langkah mitigasi yang telah diambil atau rencana penyelesaian berikutnya..."
              rows={3}
              value={actionNote}
            />
          </div>

          <div className="alos-find-modal-footer">
            <button className="alos-find-btn-secondary" onClick={onClose} type="button">
              Batal
            </button>
            <button className="alos-find-btn-primary" disabled={submitting} type="submit">
              {submitting ? "Memperbarui…" : "Simpan Perubahan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

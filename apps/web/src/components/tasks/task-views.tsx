"use client";

import { useMemo, useState, type FormEvent } from "react";
import { type SessionActor } from "@/lib/governance";
import { apiRequest } from "@/lib/api-client";
import {
  type OperationalDashboard,
  type OperationalTask,
  type TaskStatus,
} from "@/lib/operational";

export type TaskItem = {
  id: string;
  title: string;
  subtitle: string;
  projectOrDivision: string;
  priority: "HIGH" | "MEDIUM" | "LOW" | "CRITICAL";
  dueDate: string;
  dueHighlight?: "today" | "overdue" | "normal";
  assignee: {
    initials: string;
    name: string;
  };
  evidenceCount?: number;
  status: "IN_PROGRESS" | "IN_REVIEW" | "TODO" | "OVERDUE" | "DONE";
  statusLabel: string;
  rawTask?: OperationalTask;
};

const DEFAULT_REFERENCE_TASKS: TaskItem[] = [
  {
    id: "task-ref-1",
    title: "Review arsitektur sistem GENESIS",
    subtitle: "Review dan berikan masukan untuk dokumen arsitektur v2.0",
    projectOrDivision: "IT Operations",
    priority: "HIGH",
    dueDate: "Hari ini\n10 Sep 2026",
    dueHighlight: "today",
    assignee: { initials: "AR", name: "Andi Rahman" },
    evidenceCount: 2,
    status: "IN_PROGRESS",
    statusLabel: "Dalam Proses",
  },
  {
    id: "task-ref-2",
    title: "Finalisasi kebutuhan infrastruktur",
    subtitle: "Lengkapi daftar kebutuhan dan estimasi biaya",
    projectOrDivision: "Proyek GENESIS",
    priority: "HIGH",
    dueDate: "11 Sep 2026",
    dueHighlight: "normal",
    assignee: { initials: "DW", name: "Dewi Lestari" },
    evidenceCount: 1,
    status: "IN_REVIEW",
    statusLabel: "Menunggu Review",
  },
  {
    id: "task-ref-3",
    title: "Koordinasi dengan vendor cloud",
    subtitle: "Diskusi teknis dan timeline implementasi",
    projectOrDivision: "IT Operations",
    priority: "MEDIUM",
    dueDate: "Hari ini\n10 Sep 2026",
    dueHighlight: "today",
    assignee: { initials: "BK", name: "Budi Kurniawan" },
    evidenceCount: 0,
    status: "IN_PROGRESS",
    statusLabel: "Dalam Proses",
  },
  {
    id: "task-ref-4",
    title: "Buat laporan progress mingguan",
    subtitle: "Ringkasan progress proyek minggu ini",
    projectOrDivision: "Proyek ARA",
    priority: "MEDIUM",
    dueDate: "12 Sep 2026",
    dueHighlight: "normal",
    assignee: { initials: "SN", name: "Siti Nurhaliza" },
    evidenceCount: 1,
    status: "TODO",
    statusLabel: "Belum Dimulai",
  },
  {
    id: "task-ref-5",
    title: "Tindak lanjut temuan audit",
    subtitle: "Implementasi perbaikan sesuai rekomendasi",
    projectOrDivision: "Governance",
    priority: "HIGH",
    dueDate: "8 Sep 2026",
    dueHighlight: "overdue",
    assignee: { initials: "HI", name: "Hadi Iskandar" },
    evidenceCount: 3,
    status: "OVERDUE",
    statusLabel: "Terlambat",
  },
  {
    id: "task-ref-6",
    title: "Update dokumentasi user guide",
    subtitle: "Perbarui panduan sesuai fitur terbaru",
    projectOrDivision: "Dokumentasi",
    priority: "LOW",
    dueDate: "15 Sep 2026",
    dueHighlight: "normal",
    assignee: { initials: "MA", name: "Maya Anggraini" },
    evidenceCount: 1,
    status: "IN_PROGRESS",
    statusLabel: "Dalam Proses",
  },
  {
    id: "task-ref-7",
    title: "Persiapan demo ke manajemen",
    subtitle: "Siapkan materi dan skenario demo",
    projectOrDivision: "Proyek GENESIS",
    priority: "MEDIUM",
    dueDate: "10 Sep 2026",
    dueHighlight: "normal",
    assignee: { initials: "RK", name: "Rizky Maulana" },
    evidenceCount: 0,
    status: "TODO",
    statusLabel: "Belum Dimulai",
  },
  {
    id: "task-ref-8",
    title: "Evaluasi kinerja sistem",
    subtitle: "Analisis performa dan buat rekomendasi",
    projectOrDivision: "IT Operations",
    priority: "LOW",
    dueDate: "18 Sep 2026",
    dueHighlight: "normal",
    assignee: { initials: "DW", name: "Dewi Lestari" },
    evidenceCount: 1,
    status: "IN_PROGRESS",
    statusLabel: "Dalam Proses",
  },
];

export type MutationFn = (work: () => Promise<unknown>, success: string) => Promise<void>;

export type TaskViewsProps = {
  actor?: SessionActor;
  operational?: OperationalDashboard | null;
  tasks?: OperationalTask[];
  mutate?: MutationFn;
  onRefresh?: () => void;
  isLoading?: boolean;
};

export function TaskViews({
  actor,
  operational,
  tasks: rawTasksProp,
  mutate,
  onRefresh,
}: TaskViewsProps) {
  const [activeTab, setActiveTab] = useState<"table" | "board" | "calendar" | "myTasks">("table");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedProject, setSelectedProject] = useState("all");
  const [selectedPriority, setSelectedPriority] = useState("all");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [selectedRows, setSelectedRows] = useState<Record<string, boolean>>({});
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [feedbackNotice, setFeedbackNotice] = useState("");

  const rawTasks = useMemo(
    () => rawTasksProp ?? operational?.tasks ?? [],
    [rawTasksProp, operational?.tasks]
  );

  const referenceTimestamp = operational?.generated_at
    ? new Date(operational.generated_at).getTime()
    : new Date("2026-09-10T15:00:00Z").getTime();

  // Map backend tasks or fallback to reference tasks
  const taskItems: TaskItem[] = useMemo(() => {
    if (rawTasks.length === 0) {
      return DEFAULT_REFERENCE_TASKS;
    }

    return rawTasks.map((t) => {
      const isOverdue =
        t.status !== "DONE" &&
        t.status !== "CANCELLED" &&
        t.due_date &&
        new Date(t.due_date).getTime() < referenceTimestamp;

      let mappedStatus: TaskItem["status"] = "TODO";
      let statusLabel = "Belum Dimulai";

      if (isOverdue) {
        mappedStatus = "OVERDUE";
        statusLabel = "Terlambat";
      } else if (t.status === "IN_PROGRESS") {
        mappedStatus = "IN_PROGRESS";
        statusLabel = "Dalam Proses";
      } else if (t.status === "IN_REVIEW") {
        mappedStatus = "IN_REVIEW";
        statusLabel = "Menunggu Review";
      } else if (t.status === "DONE") {
        mappedStatus = "DONE";
        statusLabel = "Selesai";
      }

      const formattedDueDate = t.due_date
        ? new Intl.DateTimeFormat("id-ID", {
            day: "numeric",
            month: "short",
            year: "numeric",
          }).format(new Date(t.due_date))
        : "Tanpa batas";

      const initials = (t.assignee_user_id || t.owner_user_id || "AL")
        .slice(0, 2)
        .toUpperCase();

      return {
        id: t.task_id,
        title: t.title,
        subtitle: t.description || "Tanpa rincian tambahan",
        projectOrDivision: t.project_name || t.division_code || "IT Operations",
        priority: t.priority,
        dueDate: formattedDueDate,
        dueHighlight: isOverdue ? "overdue" : "normal",
        assignee: {
          initials,
          name: t.assignee_user_id || "Pengguna ALOS",
        },
        evidenceCount: t.evidence_required ? 1 : 0,
        status: mappedStatus,
        statusLabel,
        rawTask: t,
      };
    });
  }, [rawTasks, referenceTimestamp]);

  // Filtering
  const filteredTasks = useMemo(() => {
    return taskItems.filter((item) => {
      if (activeTab === "myTasks" && actor?.user_id) {
        if (item.rawTask && item.rawTask.assignee_user_id !== actor.user_id) {
          return false;
        }
      }

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const match =
          item.title.toLowerCase().includes(query) ||
          item.subtitle.toLowerCase().includes(query) ||
          item.projectOrDivision.toLowerCase().includes(query) ||
          item.assignee.name.toLowerCase().includes(query);
        if (!match) return false;
      }

      if (selectedProject !== "all") {
        if (!item.projectOrDivision.toLowerCase().includes(selectedProject.toLowerCase())) {
          return false;
        }
      }

      if (selectedPriority !== "all") {
        if (item.priority !== selectedPriority) return false;
      }

      if (selectedStatus !== "all") {
        if (item.status !== selectedStatus) return false;
      }

      return true;
    });
  }, [taskItems, activeTab, actor, searchQuery, selectedProject, selectedPriority, selectedStatus]);

  // Summary Metrics calculations
  const metrics = useMemo(() => {
    const total = operational?.metrics.tasks ?? (rawTasks.length > 0 ? rawTasks.length : 24);
    const myTasksCount = actor?.user_id
      ? rawTasks.filter((t) => t.assignee_user_id === actor.user_id).length || 8
      : 8;
    const overdueCount = operational?.metrics.overdue_tasks ?? (rawTasks.filter((t) => {
      return (
        t.status !== "DONE" &&
        t.status !== "CANCELLED" &&
        t.due_date &&
        new Date(t.due_date).getTime() < referenceTimestamp
      );
    }).length || 3);
    const completedCount = rawTasks.filter((t) => t.status === "DONE").length || 16;
    const dueTodayCount = 5;

    return {
      total,
      myTasksCount,
      overdueCount,
      dueTodayCount,
      completedCount,
    };
  }, [operational, rawTasks, actor, referenceTimestamp]);

  const handleSelectAll = (checked: boolean) => {
    const next: Record<string, boolean> = {};
    if (checked) {
      filteredTasks.forEach((t) => {
        next[t.id] = true;
      });
    }
    setSelectedRows(next);
  };

  const handleToggleRow = (id: string) => {
    setSelectedRows((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const handleCreateSuccess = (msg: string) => {
    setFeedbackNotice(msg);
    setIsCreateModalOpen(false);
    if (onRefresh) onRefresh();
    setTimeout(() => setFeedbackNotice(""), 4000);
  };

  return (
    <div className="alos-task-container">
      {feedbackNotice && (
        <div className="alos-proj-toast-alert" role="status">
          ✓ {feedbackNotice}
        </div>
      )}

      {/* Hero Header */}
      <TaskHero />

      {/* 5 Summary Metric Cards + 1 CTA Button Row */}
      <TaskMetricsRow
        metrics={metrics}
        onOpenCreateModal={() => setIsCreateModalOpen(true)}
      />

      {/* Controls & Filter Toolbar */}
      <TaskControlBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onPriorityChange={setSelectedPriority}
        onProjectChange={setSelectedProject}
        onSearchChange={setSearchQuery}
        onStatusChange={setSelectedStatus}
        searchQuery={searchQuery}
        selectedPriority={selectedPriority}
        selectedProject={selectedProject}
        selectedStatus={selectedStatus}
      />

      {/* Main Content: Table View vs Board View */}
      {activeTab === "board" ? (
        <TaskBoardView
          mutate={mutate}
          onRefresh={onRefresh}
          tasks={rawTasks}
        />
      ) : activeTab === "calendar" ? (
        <div className="alos-task-calendar-placeholder">
          <div className="alos-task-empty-card">
            <svg fill="none" height="32" stroke="currentColor" strokeWidth="1.7" viewBox="0 0 24 24" width="32">
              <rect height="18" rx="2" width="18" x="3" y="4" />
              <line x1="16" x2="16" y1="2" y2="6" />
              <line x1="8" x2="8" y1="2" y2="6" />
              <line x1="3" x2="21" y1="10" y2="10" />
            </svg>
            <h4>Tampilan Kalender Operasional</h4>
            <p>Jadwal tugas tersinkronisasi otomatis dengan tenggat waktu proyek dan sprint.</p>
          </div>
        </div>
      ) : (
        <>
          <TaskTableView
            allSelected={
              filteredTasks.length > 0 &&
              filteredTasks.every((t) => selectedRows[t.id])
            }
            mutate={mutate}
            onRefresh={onRefresh}
            onSelectAll={handleSelectAll}
            onToggleRow={handleToggleRow}
            selectedRows={selectedRows}
            tasks={filteredTasks}
          />

          <TaskPaginationBar
            currentPage={1}
            totalItems={metrics.total}
            visibleCount={filteredTasks.length}
          />
        </>
      )}

      {/* Modal Dialog Tambah Tugas Baru */}
      {isCreateModalOpen && (
        <CreateTaskModal
          actor={actor}
          mutate={mutate}
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------
// Subcomponents
// ----------------------------------------------------------------------

export function TaskHero() {
  return (
    <header className="alos-task-hero">
      <div className="alos-task-hero-left">
        <p className="alos-task-kicker">TUGAS</p>
        <h1 className="alos-task-title">Kelola Tugas, Capai Hasil Lebih Baik</h1>
        <p className="alos-task-subtitle">
          Pantau, kelola, dan selesaikan tugas Anda dengan lebih terarah dan kolaboratif.
        </p>
      </div>

      <div className="alos-task-hero-right">
        <div className="alos-task-script-accent">
          Dari Tugas<br />Menuju Dampak
        </div>
        <div className="alos-task-quote-box">
          “Setiap tugas yang selesai membawa kita lebih dekat pada tujuan besar.”
        </div>
      </div>
    </header>
  );
}

export type TaskMetricsData = {
  total: number;
  myTasksCount: number;
  overdueCount: number;
  dueTodayCount: number;
  completedCount: number;
};

export function TaskMetricsRow({
  metrics,
  onOpenCreateModal,
}: {
  metrics: TaskMetricsData;
  onOpenCreateModal: () => void;
}) {
  return (
    <section aria-label="Ringkasan Metrik Tugas" className="alos-task-metrics-row">
      {/* 1. Semua Tugas */}
      <article className="alos-task-metric-card">
        <div className="alos-task-metric-icon mint">
          <svg fill="none" height="20" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div className="alos-task-metric-info">
          <span className="alos-task-metric-label">Semua Tugas</span>
          <strong className="alos-task-metric-value">{metrics.total}</strong>
          <span className="alos-task-metric-subtext">+3 minggu ini</span>
        </div>
      </article>

      {/* 2. Tugas Saya */}
      <article className="alos-task-metric-card">
        <div className="alos-task-metric-icon blue">
          <svg fill="none" height="20" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <div className="alos-task-metric-info">
          <span className="alos-task-metric-label">Tugas Saya</span>
          <strong className="alos-task-metric-value">{metrics.myTasksCount}</strong>
          <span className="alos-task-metric-subtext">+2 dari minggu lalu</span>
        </div>
      </article>

      {/* 3. Terlambat */}
      <article className="alos-task-metric-card">
        <div className="alos-task-metric-icon red">
          <svg fill="none" height="20" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div className="alos-task-metric-info">
          <span className="alos-task-metric-label">Terlambat</span>
          <strong className="alos-task-metric-value alert-red">{metrics.overdueCount}</strong>
          <span className="alos-task-metric-subtext">Perlu segera ditindaklanjuti</span>
        </div>
      </article>

      {/* 4. Jatuh Tempo Hari Ini */}
      <article className="alos-task-metric-card">
        <div className="alos-task-metric-icon amber">
          <svg fill="none" height="20" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20">
            <rect height="18" rx="2" width="18" x="3" y="4" />
            <line x1="16" x2="16" y1="2" y2="6" />
            <line x1="8" x2="8" y1="2" y2="6" />
            <line x1="3" x2="21" y1="10" y2="10" />
          </svg>
        </div>
        <div className="alos-task-metric-info">
          <span className="alos-task-metric-label">Jatuh Tempo Hari Ini</span>
          <strong className="alos-task-metric-value">{metrics.dueTodayCount}</strong>
          <span className="alos-task-metric-subtext">Termasuk prioritas tinggi</span>
        </div>
      </article>

      {/* 5. Selesai */}
      <article className="alos-task-metric-card">
        <div className="alos-task-metric-icon green">
          <svg fill="none" height="20" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>
        <div className="alos-task-metric-info">
          <span className="alos-task-metric-label">Selesai</span>
          <strong className="alos-task-metric-value">{metrics.completedCount}</strong>
          <span className="alos-task-metric-subtext">67% dari total</span>
        </div>
      </article>

      {/* CTA Button */}
      <div className="alos-task-metric-cta">
        <button
          className="alos-task-btn-primary"
          onClick={onOpenCreateModal}
          type="button"
        >
          <svg fill="none" height="16" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="16">
            <line x1="12" x2="12" y1="5" y2="19" />
            <line x1="5" x2="19" y1="12" y2="12" />
          </svg>
          <span>Tugas Baru</span>
        </button>
      </div>
    </section>
  );
}

export function TaskControlBar({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  selectedProject,
  onProjectChange,
  selectedPriority,
  onPriorityChange,
  selectedStatus,
  onStatusChange,
}: {
  activeTab: "table" | "board" | "calendar" | "myTasks";
  onTabChange: (tab: "table" | "board" | "calendar" | "myTasks") => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  selectedProject: string;
  onProjectChange: (p: string) => void;
  selectedPriority: string;
  onPriorityChange: (pr: string) => void;
  selectedStatus: string;
  onStatusChange: (st: string) => void;
}) {
  return (
    <div className="alos-task-control-bar">
      {/* Left Tabs */}
      <nav aria-label="Navigasi Tampilan Tugas" className="alos-task-view-tabs">
        <button
          className={`alos-task-tab-btn ${activeTab === "table" ? "active" : ""}`}
          onClick={() => onTabChange("table")}
          type="button"
        >
          Daftar Tugas
        </button>
        <button
          className={`alos-task-tab-btn ${activeTab === "board" ? "active" : ""}`}
          onClick={() => onTabChange("board")}
          type="button"
        >
          Board
        </button>
        <button
          className={`alos-task-tab-btn ${activeTab === "calendar" ? "active" : ""}`}
          onClick={() => onTabChange("calendar")}
          type="button"
        >
          Kalender
        </button>
        <button
          className={`alos-task-tab-btn ${activeTab === "myTasks" ? "active" : ""}`}
          onClick={() => onTabChange("myTasks")}
          type="button"
        >
          Tugas Saya
        </button>
      </nav>

      {/* Right Search & Filter Bar */}
      <div className="alos-task-filters">
        <div className="alos-task-search-wrap">
          <svg fill="none" height="15" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="15">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" x2="16.65" y1="21" y2="16.65" />
          </svg>
          <input
            aria-label="Cari tugas"
            className="alos-task-search-input"
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Cari tugas..."
            type="search"
            value={searchQuery}
          />
        </div>

        <select
          aria-label="Filter berdasarkan proyek"
          className="alos-task-select"
          onChange={(e) => onProjectChange(e.target.value)}
          value={selectedProject}
        >
          <option value="all">Semua Proyek</option>
          <option value="GENESIS">Proyek GENESIS</option>
          <option value="ARA">Proyek ARA</option>
          <option value="IT Operations">IT Operations</option>
          <option value="Governance">Governance</option>
        </select>

        <select
          aria-label="Filter berdasarkan prioritas"
          className="alos-task-select"
          onChange={(e) => onPriorityChange(e.target.value)}
          value={selectedPriority}
        >
          <option value="all">Semua Prioritas</option>
          <option value="HIGH">Tinggi</option>
          <option value="MEDIUM">Sedang</option>
          <option value="LOW">Rendah</option>
        </select>

        <select
          aria-label="Filter berdasarkan status"
          className="alos-task-select"
          onChange={(e) => onStatusChange(e.target.value)}
          value={selectedStatus}
        >
          <option value="all">Semua Status</option>
          <option value="IN_PROGRESS">Dalam Proses</option>
          <option value="IN_REVIEW">Menunggu Review</option>
          <option value="TODO">Belum Dimulai</option>
          <option value="OVERDUE">Terlambat</option>
          <option value="DONE">Selesai</option>
        </select>

        <button className="alos-task-filter-btn" type="button">
          <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          <span>Filter</span>
        </button>
      </div>
    </div>
  );
}

export function TaskTableView({
  tasks,
  selectedRows,
  allSelected,
  onSelectAll,
  onToggleRow,
  mutate,
  onRefresh,
}: {
  tasks: TaskItem[];
  selectedRows: Record<string, boolean>;
  allSelected: boolean;
  onSelectAll: (checked: boolean) => void;
  onToggleRow: (id: string) => void;
  mutate?: MutationFn;
  onRefresh?: () => void;
}) {
  const handleDeleteTask = async (task: TaskItem) => {
    if (!task.rawTask) return;
    if (!window.confirm(`Hapus tugas "${task.title}"?`)) return;

    if (mutate) {
      await mutate(
        () => apiRequest(`/api/v1/tasks/${task.rawTask?.task_id}`, { method: "DELETE" }),
        `Tugas "${task.title}" berhasil dihapus.`
      );
    } else {
      await apiRequest(`/api/v1/tasks/${task.rawTask.task_id}`, { method: "DELETE" });
      if (onRefresh) onRefresh();
    }
  };

  return (
    <div className="alos-task-table-wrap">
      <table className="alos-task-table">
        <thead>
          <tr>
            <th style={{ width: "42px" }}>
              <input
                aria-label="Pilih semua tugas"
                checked={allSelected}
                className="alos-task-checkbox"
                onChange={(e) => onSelectAll(e.target.checked)}
                type="checkbox"
              />
            </th>
            <th>Tugas</th>
            <th>Proyek / Divisi</th>
            <th>Prioritas</th>
            <th>
              <span className="alos-task-sortable-header">
                Jatuh Tempo
                <svg fill="none" height="13" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="13">
                  <line x1="12" x2="12" y1="5" y2="19" />
                  <polyline points="19 12 12 19 5 12" />
                </svg>
              </span>
            </th>
            <th>Penanggung Jawab</th>
            <th>Bukti / Evidence</th>
            <th>Status</th>
            <th style={{ width: "38px" }}>
              <span className="sr-only">Aksi</span>
              <span className="alos-task-th-dots">···</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => {
            const isSelected = !!selectedRows[task.id];
            return (
              <tr className={isSelected ? "selected" : ""} key={task.id}>
                <td>
                  <input
                    aria-label={`Pilih tugas ${task.title}`}
                    checked={isSelected}
                    className="alos-task-checkbox"
                    onChange={() => onToggleRow(task.id)}
                    type="checkbox"
                  />
                </td>
                <td>
                  <div className="alos-task-name-cell">
                    <strong className="alos-task-name-title">{task.title}</strong>
                    <span className="alos-task-name-subtitle">{task.subtitle}</span>
                  </div>
                </td>
                <td>
                  <span className="alos-task-project-label">{task.projectOrDivision}</span>
                </td>
                <td>
                  <PriorityBadge priority={task.priority} />
                </td>
                <td>
                  <DueDateBadge
                    dueDate={task.dueDate}
                    highlight={task.dueHighlight}
                  />
                </td>
                <td>
                  <div className="alos-task-assignee-cell">
                    <div className="alos-task-avatar">{task.assignee.initials}</div>
                    <span className="alos-task-assignee-name">{task.assignee.name}</span>
                  </div>
                </td>
                <td>
                  <EvidenceBadge count={task.evidenceCount} />
                </td>
                <td>
                  <StatusBadge status={task.status} statusLabel={task.statusLabel} />
                </td>
                <td>
                  <div className="alos-task-row-actions">
                    <button
                      aria-label={`Aksi tugas ${task.title}`}
                      className="alos-task-btn-action"
                      onClick={() => void handleDeleteTask(task)}
                      title={task.rawTask ? "Hapus tugas" : "Detail tugas"}
                      type="button"
                    >
                      ···
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
          {tasks.length === 0 && (
            <tr>
              <td colSpan={9} style={{ textAlign: "center", padding: "32px", color: "var(--alos-slate-500)" }}>
                Tidak ada tugas yang sesuai dengan kriteria filter Anda.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function PriorityBadge({ priority }: { priority: TaskItem["priority"] }) {
  if (priority === "HIGH" || priority === "CRITICAL") {
    return (
      <span className="alos-task-badge priority-high">
        <svg fill="none" height="12" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="12">
          <line x1="12" x2="12" y1="19" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
        <span>Tinggi</span>
      </span>
    );
  }
  if (priority === "MEDIUM") {
    return (
      <span className="alos-task-badge priority-medium">
        <svg fill="none" height="12" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="12">
          <line x1="12" x2="12" y1="19" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
        <span>Sedang</span>
      </span>
    );
  }
  return (
    <span className="alos-task-badge priority-low">
      <svg fill="none" height="12" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="12">
        <line x1="12" x2="12" y1="5" y2="19" />
        <polyline points="19 12 12 19 5 12" />
      </svg>
      <span>Rendah</span>
    </span>
  );
}

export function DueDateBadge({
  dueDate,
  highlight,
}: {
  dueDate: string;
  highlight?: "today" | "overdue" | "normal";
}) {
  const parts = dueDate.split("\n");

  if (highlight === "today") {
    return (
      <div className="alos-task-duedate today">
        <span className="alos-task-duedate-alert">Hari ini</span>
        <span className="alos-task-duedate-date">{parts[1] || parts[0]}</span>
      </div>
    );
  }

  if (highlight === "overdue") {
    return (
      <div className="alos-task-duedate overdue">
        <span className="alos-task-duedate-date alert">{parts[0]}</span>
      </div>
    );
  }

  return (
    <div className="alos-task-duedate normal">
      <span className="alos-task-duedate-date">{parts[0]}</span>
    </div>
  );
}

export function EvidenceBadge({ count }: { count?: number }) {
  if (!count || count === 0) {
    return <span className="alos-task-evidence empty">— Belum ada</span>;
  }
  return (
    <span className="alos-task-evidence present">
      <svg fill="none" height="13" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="13">
        <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l7.88-7.88" />
      </svg>
      <span>{count} dokumen</span>
    </span>
  );
}

export function StatusBadge({
  status,
  statusLabel,
}: {
  status: TaskItem["status"];
  statusLabel: string;
}) {
  let toneClass = "in-progress";
  if (status === "IN_REVIEW") toneClass = "in-review";
  if (status === "TODO") toneClass = "todo";
  if (status === "OVERDUE") toneClass = "overdue";
  if (status === "DONE") toneClass = "done";

  return (
    <span className={`alos-task-status-pill ${toneClass}`}>
      <span className="alos-task-status-dot" />
      <span>{statusLabel}</span>
    </span>
  );
}

export function TaskPaginationBar({
  visibleCount,
  totalItems,
  currentPage,
}: {
  visibleCount: number;
  totalItems: number;
  currentPage: number;
}) {
  return (
    <footer className="alos-task-pagination">
      <span className="alos-task-pagination-summary">
        Menampilkan {visibleCount} dari {totalItems} tugas
      </span>
      <div className="alos-task-pagination-nav">
        <button
          aria-label="Halaman sebelumnya"
          className="alos-task-page-btn arrow"
          disabled={currentPage <= 1}
          type="button"
        >
          ‹
        </button>
        <button className="alos-task-page-btn active" type="button">
          1
        </button>
        <button className="alos-task-page-btn" type="button">
          2
        </button>
        <button className="alos-task-page-btn" type="button">
          3
        </button>
        <button
          aria-label="Halaman selanjutnya"
          className="alos-task-page-btn arrow"
          type="button"
        >
          ›
        </button>
      </div>
    </footer>
  );
}

// ----------------------------------------------------------------------
// Kanban Board View (Retained & Polished)
// ----------------------------------------------------------------------

export function TaskBoardView({
  tasks,
  mutate,
  onRefresh,
}: {
  tasks: OperationalTask[];
  mutate?: MutationFn;
  onRefresh?: () => void;
}) {
  const nextStatusMap: Partial<Record<TaskStatus, TaskStatus>> = {
    DRAFT: "TODO",
    TODO: "IN_PROGRESS",
    IN_PROGRESS: "IN_REVIEW",
    IN_REVIEW: "DONE",
  };

  const columns: Array<{ label: string; statuses: TaskStatus[] }> = [
    { label: "To do", statuses: ["DRAFT", "TODO"] },
    { label: "In progress", statuses: ["IN_PROGRESS"] },
    { label: "In review", statuses: ["IN_REVIEW"] },
    { label: "Selesai", statuses: ["DONE", "CANCELLED"] },
  ];

  const handleAdvanceStatus = async (task: OperationalTask) => {
    const next = nextStatusMap[task.status];
    if (!next) return;

    if (mutate) {
      await mutate(
        () =>
          apiRequest(`/api/v1/tasks/${task.task_id}/status`, {
            method: "PATCH",
            body: JSON.stringify({ status: next }),
          }),
        `Status tugas diubah menjadi ${next}.`
      );
    } else {
      await apiRequest(`/api/v1/tasks/${task.task_id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
      if (onRefresh) onRefresh();
    }
  };

  return (
    <div className="alos-task-kanban-board">
      {columns.map((col) => {
        const colTasks = tasks.filter((t) => col.statuses.includes(t.status));
        return (
          <div className="alos-task-kanban-col" key={col.label}>
            <div className="alos-task-kanban-col-header">
              <strong>{col.label}</strong>
              <span className="alos-task-kanban-col-count">{colTasks.length}</span>
            </div>

            <div className="alos-task-kanban-col-body">
              {colTasks.map((t) => (
                <article className="alos-task-kanban-card" key={t.task_id}>
                  <div className="alos-task-kanban-card-top">
                    <span className={`alos-task-badge priority-${t.priority.toLowerCase()}`}>
                      {t.priority}
                    </span>
                    <span className="alos-task-kanban-due">
                      {t.due_date ? t.due_date.slice(0, 10) : "No due date"}
                    </span>
                  </div>
                  <strong className="alos-task-kanban-title">{t.title}</strong>
                  <p className="alos-task-kanban-desc">{t.description || "Tanpa rincian"}</p>
                  <div className="alos-task-kanban-actions">
                    {nextStatusMap[t.status] && (
                      <button
                        className="alos-task-btn-advance"
                        onClick={() => void handleAdvanceStatus(t)}
                        type="button"
                      >
                        Lanjut ke {nextStatusMap[t.status]} →
                      </button>
                    )}
                  </div>
                </article>
              ))}

              {colTasks.length === 0 && (
                <div className="alos-task-kanban-empty">Belum ada tugas pada tahap ini.</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ----------------------------------------------------------------------
// Create Task Modal Dialog
// ----------------------------------------------------------------------

export function CreateTaskModal({
  actor,
  onClose,
  mutate,
  onSuccess,
}: {
  actor?: SessionActor;
  onClose: () => void;
  mutate?: MutationFn;
  onSuccess: (msg: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [divisionCode, setDivisionCode] = useState(actor?.division_codes[0] || "IT");
  const [priority, setPriority] = useState<"LOW" | "MEDIUM" | "HIGH" | "CRITICAL">("MEDIUM");
  const [dueDate, setDueDate] = useState("");
  const [evidenceRequired, setEvidenceRequired] = useState(false);
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const workspaceId = actor?.workspace_ids[0] || "ws-it-ops";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMsg("Judul tugas wajib diisi.");
      return;
    }
    setErrorMsg("");
    setIsSubmitting(true);

    const payload = {
      workspace_id: workspaceId,
      division_code: divisionCode,
      title: title.trim(),
      description: description.trim(),
      priority,
      due_date: dueDate ? dueDate : null,
      evidence_required: evidenceRequired,
      idempotency_key: crypto.randomUUID(),
    };

    try {
      if (mutate) {
        await mutate(
          () =>
            apiRequest("/api/v1/tasks", {
              method: "POST",
              body: JSON.stringify(payload),
            }),
          "Tugas baru berhasil disimpan dan dicatat dalam audit trail."
        );
      } else {
        await apiRequest("/api/v1/tasks", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      onSuccess(`Tugas "${title.trim()}" berhasil dibuat.`);
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Gagal membuat tugas baru.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      aria-labelledby="modal-task-title"
      aria-modal="true"
      className="alos-modal-backdrop"
      onClick={onClose}
      role="dialog"
    >
      <div
        className="alos-modal-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="alos-modal-header">
          <div>
            <p className="alos-dash-kicker">MANAJEMEN TUGAS</p>
            <h2 className="alos-modal-title" id="modal-task-title">Tambah Tugas Baru</h2>
          </div>
          <button
            aria-label="Tutup dialog"
            className="alos-modal-close-btn"
            onClick={onClose}
            type="button"
          >
            ✕
          </button>
        </header>

        {errorMsg && <div className="alos-operation-banner error">{errorMsg}</div>}

        <form className="alos-modal-form" onSubmit={(e) => void handleSubmit(e)}>
          <div className="alos-form-group">
            <label htmlFor="task-title">Nama / Judul Tugas *</label>
            <input
              id="task-title"
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Contoh: Review arsitektur sistem GENESIS"
              required
              type="text"
              value={title}
            />
          </div>

          <div className="alos-form-row-2">
            <div className="alos-form-group">
              <label htmlFor="task-division">Divisi</label>
              <select
                id="task-division"
                onChange={(e) => setDivisionCode(e.target.value)}
                value={divisionCode}
              >
                <option value="IT">IT Operations</option>
                <option value="BD">Business Development</option>
                <option value="OP">Operations</option>
                <option value="FN">Finance</option>
                <option value="HR">Human Resources</option>
                <option value="MK">Marketing</option>
                <option value="GA">General Affairs</option>
              </select>
            </div>

            <div className="alos-form-group">
              <label htmlFor="task-priority">Prioritas</label>
              <select
                id="task-priority"
                onChange={(e) =>
                  setPriority(e.target.value as "LOW" | "MEDIUM" | "HIGH" | "CRITICAL")
                }
                value={priority}
              >
                <option value="HIGH">Tinggi (High)</option>
                <option value="MEDIUM">Sedang (Medium)</option>
                <option value="LOW">Rendah (Low)</option>
                <option value="CRITICAL">Kritis (Critical)</option>
              </select>
            </div>
          </div>

          <div className="alos-form-row-2">
            <div className="alos-form-group">
              <label htmlFor="task-due-date">Tenggat Waktu (Jatuh Tempo)</label>
              <input
                id="task-due-date"
                onChange={(e) => setDueDate(e.target.value)}
                type="date"
                value={dueDate}
              />
            </div>

            <div className="alos-form-group" style={{ justifyContent: "center" }}>
              <label className="alos-task-checkbox-label">
                <input
                  checked={evidenceRequired}
                  onChange={(e) => setEvidenceRequired(e.target.checked)}
                  type="checkbox"
                />
                <span>Wajib unggah bukti dokumen</span>
              </label>
            </div>
          </div>

          <div className="alos-form-group">
            <label htmlFor="task-desc">Deskripsi Tugas</label>
            <textarea
              id="task-desc"
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Rincian instruksi atau kriteria penyelesaian tugas..."
              rows={3}
              value={description}
            />
          </div>

          <footer className="alos-modal-footer">
            <button
              className="alos-btn-secondary"
              disabled={isSubmitting}
              onClick={onClose}
              type="button"
            >
              Batal
            </button>
            <button
              className="alos-btn-primary"
              disabled={isSubmitting}
              type="submit"
            >
              {isSubmitting ? "Menyimpan..." : "Simpan Tugas"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

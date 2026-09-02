"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  DataTable,
  FormField,
  Modal,
  SelectInput,
  StatsCard,
  StatusPill,
  TextAreaInput,
  TextInput,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  generateExecutiveBrief,
  getExecutiveBriefs,
  reviewExecutiveBrief,
} from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/format";
import type { ExecutiveBriefRecord } from "@/lib/types";

function localDate(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function initialPeriod() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 7);
  return { start: localDate(start), end: localDate(end) };
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Executive Brief belum dapat diproses.";
}

export default function ExecutivePage() {
  const { activeProjectId, principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const period = useMemo(() => initialPeriod(), []);
  const [briefs, setBriefs] = useState<ExecutiveBriefRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"history" | "inspector">("history");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [showGenerateModal, setShowGenerateModal] = useState(false);

  // Forms
  const [briefForm, setBriefForm] = useState({
    title: "Brief Eksekutif ALOS",
    periodStart: period.start,
    periodEnd: period.end,
  });

  const [review, setReview] = useState({
    decision: "PUBLISHED" as "PUBLISHED" | "REVISION_REQUESTED",
    notes: "",
  });

  const selected = useMemo(
    () => briefs.find((b) => b.executive_brief_id === selectedId) || null,
    [briefs, selectedId],
  );

  const canGenerate = Boolean(
    principal?.roles.some((r) => r === "DIRECTOR" || r === "AI_EXECUTIVE"),
  );

  const canReview = Boolean(principal?.roles.includes("DIRECTOR"));

  const loadData = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const page = await getExecutiveBriefs(token, activeProjectId);
      setBriefs(page.items);
      if (page.items.length > 0 && !selectedId) {
        setSelectedId(page.items[0].executive_brief_id);
      }
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, selectedId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  // Generate Executive Brief
  const handleGenerateBrief = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !canGenerate) return;
    setBusy(true);
    try {
      const result = await generateExecutiveBrief(token, {
        title: briefForm.title.trim(),
        period_start: briefForm.periodStart,
        period_end: briefForm.periodEnd,
        project_id: activeProjectId,
      });
      setShowGenerateModal(false);
      toastSuccess("Brief Eksekutif berhasil di-generate oleh AI Executive Layer.");
      await loadData();
      setSelectedId(result.executive_brief_id);
      setActiveTab("inspector");
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Review Executive Brief
  const handleReviewBrief = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canReview) return;
    setBusy(true);
    try {
      await reviewExecutiveBrief(token, selected.executive_brief_id, {
        decision: review.decision,
        notes: review.notes.trim(),
      });
      toastSuccess(`Keputusan brief (${review.decision}) berhasil dicatat.`);
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul AI Executive Brief..." />;
  }

  const publishedCount = briefs.filter((b) => b.status === "PUBLISHED").length;
  const draftCount = briefs.filter((b) => b.status === "DRAFT" || b.status === "PENDING_REVIEW").length;

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner" style={{ background: "linear-gradient(135deg, #1e1338 0%, #2f1c54 65%, #432b75 100%)" }}>
        <div>
          <span className="workspaceBannerTag" style={{ color: "#d1aff7" }}>
            AI Executive Layer · Core Brief & Synthesis
          </span>
          <h1 className="workspaceBannerTitle">
            Executive Brief, Analisis Risiko & Eskalasi Lintas Divisi
          </h1>
          <p className="workspaceBannerSubtitle">
            Sintesis data operasional 6 divisi, rekomendasi keputusan direksi, dan pelacakan blocker.
          </p>
        </div>

        {canGenerate && (
          <div className="workspaceActionGroup">
            <button
              className="button primary"
              onClick={() => setShowGenerateModal(true)}
              style={{ background: "#703cb5" }}
              type="button"
            >
              🤖 Generate Brief Eksekutif Baru
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${briefs.length} Edisi`, variant: "info" }}
          subtitle="Total executive brief yang telah dihasilkan"
          title="Total Brief Eksekutif"
          value={briefs.length}
        />
        <StatsCard
          badge={{ text: `${publishedCount} Terbit`, variant: "success" }}
          subtitle="Brief yang telah dipublikasikan ke jajaran direksi"
          title="Brief Dipublikasikan"
          value={publishedCount}
        />
        <StatsCard
          badge={{ text: `${draftCount} Draf`, variant: draftCount > 0 ? "warning" : "success" }}
          subtitle="Brief dalam reviu sebelum publikasi resmi"
          title="Menunggu Reviu"
          value={draftCount}
        />
        <StatsCard
          badge={{ text: "6 Divisi", variant: "info" }}
          subtitle="Finance, Sales, Property, HR, Legal, IT"
          title="Cakupan Data Sintesis"
          value="100% Terhubung"
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
          type="button"
        >
          📋 Riwayat Brief Eksekutif ({briefs.length})
        </button>
        <button
          className={`tabButton ${activeTab === "inspector" ? "active" : ""}`}
          onClick={() => setActiveTab("inspector")}
          type="button"
        >
          🔍 Inspeksi Konten & Keputusan {selected ? `(${selected.title})` : ""}
        </button>
      </div>

      {/* Tab 1: Briefs History DataTable */}
      {activeTab === "history" && (
        <DataTable
          columns={[
            {
              header: "Judul Brief Eksekutif",
              cell: (b: ExecutiveBriefRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{b.title}</strong>
                  <span style={{ color: "var(--green-700)", fontFamily: "monospace", fontSize: "11px" }}>
                    ID: {shortId(b.executive_brief_id)}
                  </span>
                </div>
              ),
            },
            {
              header: "Periode Analisis",
              cell: (b: ExecutiveBriefRecord) => (
                <span style={{ fontFamily: "monospace", fontSize: "12px" }}>
                  {b.period_start} s.d. {b.period_end}
                </span>
              ),
            },
            {
              header: "Status Brief",
              cell: (b: ExecutiveBriefRecord) => <StatusPill status={b.status} />,
            },
            {
              header: "Waktu Generate",
              cell: (b: ExecutiveBriefRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>{formatDateTime(b.created_at)}</span>
              ),
            },
          ]}
          data={briefs}
          keyExtractor={(b) => b.executive_brief_id}
          onRowClick={(b) => {
            setSelectedId(b.executive_brief_id);
            setActiveTab("inspector");
          }}
          searchFilter={(b, q) =>
            b.title.toLowerCase().includes(q) || b.status.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari judul brief atau status..."
        />
      )}

      {/* Tab 2: Inspeksi Konten & Reviu Direktur */}
      {activeTab === "inspector" && (
        <div className="grid12">
          <div className="colSpan8">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu brief dari tabel riwayat untuk melihat analisis strategis."
                title="Pilih Brief Eksekutif"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>{selected.title}</h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      Periode: {selected.period_start} s.d. {selected.period_end}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                {/* Summary Box */}
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "11px", color: "var(--green-700)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                    Executive Narrative & Ringkasan Lintas Divisi:
                  </h3>
                  <div style={{ padding: "16px", background: "var(--paper)", borderRadius: "10px", border: "1px solid var(--line)", lineHeight: "1.7", fontSize: "13px", whiteSpace: "pre-wrap" }}>
                    {selected.narrative || "Tidak ada ringkasan teks."}
                  </div>
                </div>

                {/* Summary Counts */}
                {selected.summary_counts && (
                  <div>
                    <h3 style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                      Ringkasan Metrik Data:
                    </h3>
                    <div className="gridCols3">
                      {Object.entries(selected.summary_counts).map(([key, val]) => (
                        <div
                          key={key}
                          style={{ padding: "12px", background: "var(--white)", border: "1px solid var(--line)", borderRadius: "8px" }}
                        >
                          <span style={{ display: "block", color: "var(--muted)", fontSize: "11px", textTransform: "capitalize" }}>
                            {key.replace(/_/g, " ")}
                          </span>
                          <strong style={{ fontSize: "18px", fontFamily: "monospace", color: "var(--green-800)" }}>
                            {val}
                          </strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="colSpan4 spaceY4">
            {selected && canReview && (
              <form
                className="panel"
                onSubmit={handleReviewBrief}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Reviu & Keputusan Direktur
                </h3>

                <FormField label="Keputusan Publikasi:">
                  <SelectInput
                    onChange={(e) =>
                      setReview({
                        ...review,
                        decision: e.target.value as "PUBLISHED" | "REVISION_REQUESTED",
                      })
                    }
                    value={review.decision}
                  >
                    <option value="PUBLISHED">Publikasikan Resmi (PUBLISHED)</option>
                    <option value="REVISION_REQUESTED">Minta Revisi Analisis (REVISION_REQUESTED)</option>
                  </SelectInput>
                </FormField>

                <FormField label="Catatan Tambahan Direktur:">
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setReview({ ...review, notes: e.target.value })}
                    placeholder="Masukkan arahan strategis atau instruksi tindak lanjut..."
                    value={review.notes}
                  />
                </FormField>

                <button
                  className="button primary"
                  disabled={busy}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : `Simpan Keputusan (${review.decision})`}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Generate Brief Eksekutif Baru */}
      <Modal
        onClose={() => setShowGenerateModal(false)}
        open={showGenerateModal}
        subtitle="Analisis otomatis data 6 divisi untuk sintesis laporan direksi"
        title="Generate Brief Eksekutif Baru"
      >
        <form className="spaceY4" onSubmit={handleGenerateBrief}>
          <FormField label="Judul Brief Eksekutif:" required>
            <TextInput
              onChange={(e) => setBriefForm({ ...briefForm, title: e.target.value })}
              placeholder="Contoh: Laporan Kinerja Operasional & Risiko Mingguan"
              required
              value={briefForm.title}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Awal Periode Data:" required>
              <TextInput
                onChange={(e) => setBriefForm({ ...briefForm, periodStart: e.target.value })}
                required
                type="date"
                value={briefForm.periodStart}
              />
            </FormField>

            <FormField label="Akhir Periode Data:" required>
              <TextInput
                onChange={(e) => setBriefForm({ ...briefForm, periodEnd: e.target.value })}
                required
                type="date"
                value={briefForm.periodEnd}
              />
            </FormField>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowGenerateModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !briefForm.title.trim()}
              type="submit"
            >
              {busy ? "Menganalisis..." : "Generate Brief"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

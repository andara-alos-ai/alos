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
  getDocuments,
  getSiteEvidence,
  reviewSiteEvidence,
  submitSiteEvidence,
} from "@/lib/api";
import { shortId } from "@/lib/format";
import type { DocumentRecord, SiteEvidenceRecord } from "@/lib/types";

function today(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi Property belum dapat diproses.";
}

export default function PropertyPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [records, setRecords] = useState<SiteEvidenceRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"evidence" | "review">("evidence");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [showEvidenceModal, setShowEvidenceModal] = useState(false);

  // Form State
  const [submission, setSubmission] = useState({
    documentVersionId: "",
    workPackageCode: "",
    claimDate: today(),
    claimedProgress: "0.00",
    measuredProgress: "0.00",
    measurementNote: "",
  });

  const [review, setReview] = useState({
    decision: "ACCEPTED" as "ACCEPTED" | "VARIANCE",
    verifiedProgress: "0.00",
    notes: "",
  });

  const selected = useMemo(
    () => records.find((r) => r.site_evidence_id === selectedId) || null,
    [records, selectedId],
  );

  const canOperate = Boolean(
    principal &&
      principal.division_codes.includes("PROPERTY") &&
      principal.roles.some((r) => r === "PROPERTY" || r === "DIVISION_HEAD"),
  );

  const isOwnSubmission = Boolean(
    principal && selected && principal.user_id === selected.submitted_by_user_id,
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [evidencePage, docPage] = await Promise.all([
        getSiteEvidence(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setRecords(evidencePage.items);
      setDocuments(docPage.items);
      if (evidencePage.items.length > 0 && !selectedId) {
        setSelectedId(evidencePage.items[0].site_evidence_id);
      }
      if (docPage.items.length > 0 && !submission.documentVersionId) {
        setSubmission((prev) => ({ ...prev, documentVersionId: docPage.items[0].document_version_id }));
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, selectedId, submission.documentVersionId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  // Submit Site Evidence
  const handleSubmitEvidence = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    const docId = submission.documentVersionId || documents[0]?.document_version_id || "DOC-DEFAULT";
    try {
      const created = await submitSiteEvidence(token, {
        project_id: activeProjectId,
        document_version_id: docId,
        work_package_code: submission.workPackageCode.trim().toUpperCase(),
        claim_date: submission.claimDate,
        claimed_progress: submission.claimedProgress.trim(),
        measured_progress: submission.measuredProgress.trim(),
        measurement_note: submission.measurementNote.trim(),
      });
      setShowEvidenceModal(false);
      toastSuccess("Bukti opname lapangan berhasil disubmit.");
      await loadData();
      setSelectedId(created.site_evidence_id);
      setActiveTab("review");
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Review Site Evidence
  const handleReviewEvidence = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canOperate) return;
    setBusy(true);
    try {
      await reviewSiteEvidence(token, selected.site_evidence_id, {
        decision: review.decision,
        verified_progress: review.verifiedProgress.trim() || selected.measured_progress,
        notes: review.notes.trim(),
      });
      toastSuccess(`Hasil verifikasi (${review.decision}) berhasil dicatat.`);
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul Property & Konstruksi..." />;
  }

  const acceptedCount = records.filter((r) => r.status === "ACCEPTED").length;
  const varianceCount = records.filter((r) => r.status === "VARIANCE").length;
  const pendingCount = records.filter((r) => r.status === "SUBMITTED" || r.status === "PENDING").length;

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner">
        <div>
          <span className="workspaceBannerTag">
            Workspace Property & Konstruksi · Core PRA
          </span>
          <h1 className="workspaceBannerTitle">
            Progres Proyek, Bukti Opname & Pengawasan Lapangan
          </h1>
          <p className="workspaceBannerSubtitle">
            Pencatatan progres fisik kurva S, verifikasi evidence foto lapangan, dan eskalasi deviasi (variance).
          </p>
        </div>

        {canOperate && (
          <div className="workspaceActionGroup">
            <button
              className="button primary"
              onClick={() => setShowEvidenceModal(true)}
              type="button"
            >
              + Catat Bukti Opname Lapangan
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${records.length} Item`, variant: "info" }}
          subtitle="Total paket pekerjaan dengan bukti opname"
          title="Total Opname Tercatat"
          value={records.length}
        />
        <StatsCard
          badge={{ text: `${acceptedCount} Sesuai`, variant: "success" }}
          subtitle="Progres opname yang telah disetujui tanpa deviasi"
          title="Terverifikasi (Accepted)"
          value={acceptedCount}
        />
        <StatsCard
          badge={{ text: `${varianceCount} Deviasi`, variant: varianceCount > 0 ? "danger" : "neutral" }}
          subtitle="Terdapat selisih klaim kontraktor vs fisik"
          title="Deviasi (Variance)"
          value={varianceCount}
        />
        <StatsCard
          badge={{ text: `${pendingCount} Menunggu`, variant: pendingCount > 0 ? "warning" : "success" }}
          subtitle="Menunggu verifikasi pengawas proyek"
          title="Menunggu Reviu"
          value={pendingCount}
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "evidence" ? "active" : ""}`}
          onClick={() => setActiveTab("evidence")}
          type="button"
        >
          📋 Daftar Bukti Opname ({records.length})
        </button>
        <button
          className={`tabButton ${activeTab === "review" ? "active" : ""}`}
          onClick={() => setActiveTab("review")}
          type="button"
        >
          🔍 Verifikasi & Keputusan Opname {selected ? `(${selected.work_package_code})` : ""}
        </button>
      </div>

      {/* Tab 1: Evidence DataTable */}
      {activeTab === "evidence" && (
        <DataTable
          columns={[
            {
              header: "Paket Pekerjaan",
              cell: (r: SiteEvidenceRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{r.work_package_code}</strong>
                  <span style={{ color: "var(--muted)", fontFamily: "monospace", fontSize: "11px" }}>
                    ID: {shortId(r.site_evidence_id)}
                  </span>
                </div>
              ),
            },
            {
              header: "Klaim Kontraktor",
              cell: (r: SiteEvidenceRecord) => (
                <span style={{ fontFamily: "monospace", fontWeight: 700 }}>
                  {r.claimed_progress}%
                </span>
              ),
            },
            {
              header: "Hasil Ukur Fisik",
              cell: (r: SiteEvidenceRecord) => (
                <span style={{ fontFamily: "monospace", color: "var(--green-700)", fontWeight: 700 }}>
                  {r.measured_progress}%
                </span>
              ),
            },
            {
              header: "Status Verifikasi",
              cell: (r: SiteEvidenceRecord) => <StatusPill status={r.status} />,
            },
            {
              header: "Tanggal Klaim",
              cell: (r: SiteEvidenceRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>{r.claim_date}</span>
              ),
            },
          ]}
          data={records}
          keyExtractor={(r) => r.site_evidence_id}
          onRowClick={(r) => {
            setSelectedId(r.site_evidence_id);
            setActiveTab("review");
          }}
          searchFilter={(r, q) =>
            r.work_package_code.toLowerCase().includes(q) ||
            r.status.toLowerCase().includes(q) ||
            r.measurement_note.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari paket pekerjaan, status, atau catatan opname..."
        />
      )}

      {/* Tab 2: Verifikasi & Keputusan Opname */}
      {activeTab === "review" && (
        <div className="grid12">
          <div className="colSpan7">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu bukti opname dari tabel untuk melakukan verifikasi lapangan."
                title="Pilih Bukti Opname"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
                      Paket: {selected.work_package_code}
                    </h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      ID: {selected.site_evidence_id}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                <div className="gridCols2" style={{ marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Klaim Kontraktor:</span>
                    <strong style={{ fontSize: "16px", fontFamily: "monospace" }}>{selected.claimed_progress}%</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Hasil Pengukuran Fisik:</span>
                    <strong style={{ fontSize: "16px", fontFamily: "monospace", color: "var(--green-700)" }}>{selected.measured_progress}%</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Tanggal Opname:</span>
                    <span>{selected.claim_date}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Petugas Pengaju:</span>
                    <span style={{ fontFamily: "monospace" }}>{selected.submitted_by_user_id}</span>
                  </div>
                </div>

                <div style={{ marginBottom: "14px" }}>
                  <span style={{ color: "var(--muted)", fontSize: "11px", display: "block", marginBottom: "4px" }}>Catatan & Bukti Lapangan:</span>
                  <p style={{ margin: 0, padding: "12px", background: "var(--paper)", borderRadius: "8px", border: "1px solid var(--line)", fontSize: "12px", lineHeight: "1.5" }}>
                    {selected.measurement_note}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="colSpan5 spaceY4">
            {selected && canOperate && (
              <form
                className="panel"
                onSubmit={handleReviewEvidence}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Formulir Verifikasi Progres Fisik
                </h3>

                {isOwnSubmission && (
                  <div style={{ padding: "10px", background: "#fff8e8", border: "1px solid #f7dba1", borderRadius: "8px", color: "#8c5b06", fontSize: "11px", marginBottom: "12px" }}>
                    ⚠️ Peringatan SoD: Anda adalah penginput data ini. Verifikasi mandiri sebaiknya dilakukan oleh Pengawas/Project Manager independen.
                  </div>
                )}

                <FormField label="Keputusan Verifikasi:">
                  <SelectInput
                    onChange={(e) =>
                      setReview({
                        ...review,
                        decision: e.target.value as "ACCEPTED" | "VARIANCE",
                      })
                    }
                    value={review.decision}
                  >
                    <option value="ACCEPTED">Disetujui Sesuai (ACCEPTED)</option>
                    <option value="VARIANCE">Terdapat Deviasi / Selisih (VARIANCE)</option>
                  </SelectInput>
                </FormField>

                <FormField label="Progres Terverifikasi (%):" required>
                  <TextInput
                    onChange={(e) =>
                      setReview({ ...review, verifiedProgress: e.target.value })
                    }
                    placeholder={selected.measured_progress}
                    required
                    value={review.verifiedProgress}
                  />
                </FormField>

                <FormField label="Catatan Pengawasan / Hasil Uji:" required={review.decision === "VARIANCE"}>
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setReview({ ...review, notes: e.target.value })}
                    placeholder="Wajib diisi jika terdapat selisih atau catatan perbaikan..."
                    required={review.decision === "VARIANCE"}
                    value={review.notes}
                  />
                </FormField>

                <button
                  className="button primary"
                  disabled={busy}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : "Simpan Hasil Verifikasi"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Catat Bukti Opname Baru */}
      <Modal
        onClose={() => setShowEvidenceModal(false)}
        open={showEvidenceModal}
        subtitle="Form input bukti fisik & opname pengukuran lapangan"
        title="Catat Bukti Opname Lapangan"
      >
        <form className="spaceY4" onSubmit={handleSubmitEvidence}>
          <FormField label="Kode Paket Pekerjaan:" required>
            <TextInput
              onChange={(e) =>
                setSubmission({ ...submission, workPackageCode: e.target.value })
              }
              placeholder="Contoh: PKG-STRUKTUR-01"
              required
              value={submission.workPackageCode}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Klaim Kontraktor (%):" required>
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, claimedProgress: e.target.value })
                }
                placeholder="Contoh: 15.50"
                required
                value={submission.claimedProgress}
              />
            </FormField>

            <FormField label="Hasil Ukur Fisik Pengawas (%):" required>
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, measuredProgress: e.target.value })
                }
                placeholder="Contoh: 14.80"
                required
                value={submission.measuredProgress}
              />
            </FormField>
          </div>

          <FormField label="Catatan Opname & Bukti Foto:" required>
            <TextAreaInput
              onChange={(e) =>
                setSubmission({ ...submission, measurementNote: e.target.value })
              }
              placeholder="Jelaskan kondisi fisik lapangan, cuaca, dan nomor arsip foto bukti..."
              required
              value={submission.measurementNote}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowEvidenceModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !submission.workPackageCode.trim()}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Simpan Bukti Opname"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

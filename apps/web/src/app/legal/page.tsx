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
  getLegalCases,
  reviewLegalDocument,
  submitLegalDocument,
} from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/format";
import type { DocumentRecord, LegalCaseRecord } from "@/lib/types";

type LegalDecision = "APPROVED" | "REVISION_REQUESTED" | "REJECTED";

const decisionStatus: Record<LegalDecision, "VERIFIED" | "CONDITIONAL" | "NOT_APPROVED"> = {
  APPROVED: "VERIFIED",
  REVISION_REQUESTED: "CONDITIONAL",
  REJECTED: "NOT_APPROVED",
};

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi Legal belum dapat diproses.";
}

export default function LegalPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [cases, setCases] = useState<LegalCaseRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"register" | "review">("register");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [showLegalModal, setShowLegalModal] = useState(false);

  // Form State
  const [submission, setSubmission] = useState({
    documentVersionId: "",
    documentType: "PERMIT" as "PERMIT" | "CONTRACT",
    referenceCode: "",
    title: "",
    counterparty: "",
    sourceAuthority: "",
    effectiveDate: "",
    expiryDate: "",
  });

  const [review, setReview] = useState({
    decision: "APPROVED" as LegalDecision,
    officialSourceVerified: true,
    notes: "",
  });

  const selected = useMemo(
    () => cases.find((c) => c.legal_case_id === selectedId) || null,
    [cases, selectedId],
  );

  const canOperate = Boolean(
    principal &&
      principal.division_codes.includes("LEGAL") &&
      principal.roles.some((r) => r === "LEGAL" || r === "DIVISION_HEAD"),
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
      const [casePage, docPage] = await Promise.all([
        getLegalCases(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setCases(casePage.items);
      setDocuments(docPage.items);
      if (casePage.items.length > 0 && !selectedId) {
        setSelectedId(casePage.items[0].legal_case_id);
      }
      if (docPage.items.length > 0 && !submission.documentVersionId) {
        setSubmission((prev) => ({ ...prev, documentVersionId: docPage.items[0].document_version_id }));
      }
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, selectedId, submission.documentVersionId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  // Submit Legal Document
  const handleSubmitDocument = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    const docId = submission.documentVersionId || documents[0]?.document_version_id || "DOC-DEFAULT";
    try {
      const created = await submitLegalDocument(token, {
        project_id: activeProjectId,
        document_version_id: docId,
        document_type: submission.documentType,
        reference_code: submission.referenceCode.trim(),
        title: submission.title.trim(),
        counterparty: submission.counterparty.trim() || null,
        source_authority: submission.sourceAuthority.trim() || null,
        effective_date: submission.effectiveDate || null,
        expiry_date: submission.expiryDate || null,
      });
      setShowLegalModal(false);
      toastSuccess("Dokumen legal / izin baru berhasil didaftarkan.");
      await loadData();
      setSelectedId(created.legal_case_id);
      setActiveTab("review");
    } catch (submitError) {
      toastError(message(submitError));
    } finally {
      setBusy(false);
    }
  };

  // Review Legal Document
  const handleReviewDocument = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canOperate) return;
    setBusy(true);
    try {
      await reviewLegalDocument(token, selected.legal_case_id, {
        decision: review.decision,
        legal_status: decisionStatus[review.decision],
        official_source_verified: review.officialSourceVerified,
        notes: review.notes.trim(),
      });
      toastSuccess(`Hasil reviu legal (${review.decision}) berhasil dicatat.`);
      await loadData();
    } catch (reviewError) {
      toastError(message(reviewError));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul Legal & Kepatuhan..." />;
  }

  const permitCount = cases.filter((c) => c.document_type === "PERMIT").length;
  const contractCount = cases.filter((c) => c.document_type === "CONTRACT").length;
  const verifiedCount = cases.filter((c) => c.status === "VERIFIED").length;
  const pendingCount = cases.filter((c) => c.status === "PENDING" || c.status === "SUBMITTED").length;

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner">
        <div>
          <span className="workspaceBannerTag">
            Workspace Legal & Kepatuhan · Core LRA
          </span>
          <h1 className="workspaceBannerTitle">
            Register Perizinan, Klausul Kontrak & Kepatuhan Regulasi
          </h1>
          <p className="workspaceBannerSubtitle">
            Pemantauan masa berlaku izin proyek, ekstraksi kewajiban kontrak, dan verifikasi otoritas resmi.
          </p>
        </div>

        {canOperate && (
          <div className="workspaceActionGroup">
            <button
              className="button primary"
              onClick={() => setShowLegalModal(true)}
              type="button"
            >
              + Daftarkan Dokumen / Izin Baru
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${permitCount} Izin Proyek`, variant: "info" }}
          subtitle="PBG, AMDAL, Sertifikat Tanah, Izin Lingkungan"
          title="Register Perizinan"
          value={permitCount}
        />
        <StatsCard
          badge={{ text: `${contractCount} Perjanjian`, variant: "info" }}
          subtitle="Kontrak vendor, SPK, dan perjanjian kerja sama"
          title="Kontrak & PKS"
          value={contractCount}
        />
        <StatsCard
          badge={{ text: `${verifiedCount} Sah`, variant: "success" }}
          subtitle="Dokumen yang telah diverifikasi keabsahannya"
          title="Terverifikasi Legal"
          value={verifiedCount}
        />
        <StatsCard
          badge={{ text: `${pendingCount} Menunggu`, variant: pendingCount > 0 ? "warning" : "success" }}
          subtitle="Dokumen yang sedang dalam proses reviu"
          title="Menunggu Reviu"
          value={pendingCount}
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "register" ? "active" : ""}`}
          onClick={() => setActiveTab("register")}
          type="button"
        >
          📋 Register Dokumen & Perizinan ({cases.length})
        </button>
        <button
          className={`tabButton ${activeTab === "review" ? "active" : ""}`}
          onClick={() => setActiveTab("review")}
          type="button"
        >
          ⚖️ Pemeriksaan & Reviu Legal {selected ? `(${selected.title})` : ""}
        </button>
      </div>

      {/* Tab 1: DataTable Register */}
      {activeTab === "register" && (
        <DataTable
          columns={[
            {
              header: "Judul Dokumen / Izin",
              cell: (c: LegalCaseRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{c.title}</strong>
                  <span style={{ color: "var(--green-700)", fontFamily: "monospace", fontSize: "11px" }}>
                    Ref: {c.reference_code || shortId(c.legal_case_id)}
                  </span>
                </div>
              ),
            },
            {
              header: "Tipe Dokumen",
              cell: (c: LegalCaseRecord) => (
                <span className="badge" style={{ background: "var(--paper)", border: "1px solid var(--line)", padding: "2px 8px", borderRadius: "6px" }}>
                  {c.document_type}
                </span>
              ),
            },
            {
              header: "Pihak Lawan / Otoritas",
              cell: (c: LegalCaseRecord) => (
                <span>{c.counterparty || c.source_authority || "-"}</span>
              ),
            },
            {
              header: "Status Reviu",
              cell: (c: LegalCaseRecord) => <StatusPill status={c.status} />,
            },
            {
              header: "Masa Berlaku (Expiry)",
              cell: (c: LegalCaseRecord) => (
                <span
                  style={{
                    fontFamily: "monospace",
                    fontSize: "11px",
                    color: c.expiry_date ? "var(--amber)" : "var(--muted)",
                    fontWeight: c.expiry_date ? 700 : 400,
                  }}
                >
                  {c.expiry_date || "Tidak Ada Expiry"}
                </span>
              ),
            },
            {
              header: "Waktu Daftar",
              cell: (c: LegalCaseRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>{formatDateTime(c.created_at)}</span>
              ),
            },
          ]}
          data={cases}
          keyExtractor={(c) => c.legal_case_id}
          onRowClick={(c) => {
            setSelectedId(c.legal_case_id);
            setActiveTab("review");
          }}
          searchFilter={(c, q) =>
            Boolean(
              c.title.toLowerCase().includes(q) ||
              c.document_type.toLowerCase().includes(q) ||
              c.status.toLowerCase().includes(q) ||
              (c.counterparty && c.counterparty.toLowerCase().includes(q)),
            )
          }
          searchPlaceholder="Cari judul izin, nomor referensi, pihak lawan, status..."
        />
      )}

      {/* Tab 2: Pemeriksaan & Reviu Legal */}
      {activeTab === "review" && (
        <div className="grid12">
          <div className="colSpan7">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu dokumen legal dari tabel register untuk melakukan reviu klausul."
                title="Pilih Dokumen Legal"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>{selected.title}</h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      ID: {selected.legal_case_id}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                <div className="gridCols2" style={{ marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Tipe Dokumen:</span>
                    <strong>{selected.document_type}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Nomor Referensi:</span>
                    <strong style={{ color: "var(--green-700)", fontFamily: "monospace" }}>
                      {selected.reference_code || "-"}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Pihak Terkait:</span>
                    <span>{selected.counterparty || "Internal Perusahaan"}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Otoritas Penerbit:</span>
                    <span>{selected.source_authority || "Instansi Pemerintah"}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Tanggal Efektif:</span>
                    <span style={{ fontFamily: "monospace" }}>{selected.effective_date || "-"}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Masa Berlaku Habis (Expiry):</span>
                    <span style={{ color: "var(--amber)", fontFamily: "monospace", fontWeight: 700 }}>
                      {selected.expiry_date || "Permanen"}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="colSpan5 spaceY4">
            {selected && canOperate && (
              <form
                className="panel"
                onSubmit={handleReviewDocument}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Formulir Reviu Legal & Kepatuhan
                </h3>

                {isOwnSubmission && (
                  <div style={{ padding: "10px", background: "#fff8e8", border: "1px solid #f7dba1", borderRadius: "8px", color: "#8c5b06", fontSize: "11px", marginBottom: "12px" }}>
                    ⚠️ Peringatan SoD: Anda adalah pengunggah dokumen ini. Reviu keabsahan sebaiknya diverifikasi oleh Legal Counsel independen.
                  </div>
                )}

                <FormField label="Keputusan Legal:">
                  <SelectInput
                    onChange={(e) =>
                      setReview({ ...review, decision: e.target.value as LegalDecision })
                    }
                    value={review.decision}
                  >
                    <option value="APPROVED">Disetujui & Sah (APPROVED)</option>
                    <option value="REVISION_REQUESTED">Perlu Revisi Klausul (REVISION_REQUESTED)</option>
                    <option value="REJECTED">Tolak Dokumen (REJECTED)</option>
                  </SelectInput>
                </FormField>

                <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px", background: "var(--paper)", borderRadius: "8px", border: "1px solid var(--line)", marginBottom: "12px" }}>
                  <input
                    checked={review.officialSourceVerified}
                    id="chk-official"
                    onChange={(e) =>
                      setReview({ ...review, officialSourceVerified: e.target.checked })
                    }
                    type="checkbox"
                  />
                  <label htmlFor="chk-official" style={{ fontSize: "11px", cursor: "pointer" }}>
                    Keabsahan sumber resmi & stempel basah terverifikasi
                  </label>
                </div>

                <FormField label="Catatan Reviu Hukum & Rekomendasi:">
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setReview({ ...review, notes: e.target.value })}
                    placeholder="Masukkan catatan evaluasi pasal, risiko liabilitas, atau alasan penolakan..."
                    required={review.decision !== "APPROVED"}
                    value={review.notes}
                  />
                </FormField>

                <button
                  className="button primary"
                  disabled={busy}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : `Simpan Reviu (${review.decision})`}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Daftarkan Dokumen Legal Baru */}
      <Modal
        onClose={() => setShowLegalModal(false)}
        open={showLegalModal}
        subtitle="Registrasi perizinan atau kontrak kerja sama baru"
        title="Daftarkan Dokumen / Izin Baru"
      >
        <form className="spaceY4" onSubmit={handleSubmitDocument}>
          <FormField label="Judul Dokumen / Perizinan:" required>
            <TextInput
              onChange={(e) => setSubmission({ ...submission, title: e.target.value })}
              placeholder="Contoh: Persetujuan Bangunan Gedung (PBG) Tower A"
              required
              value={submission.title}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Tipe Dokumen:">
              <SelectInput
                onChange={(e) =>
                  setSubmission({
                    ...submission,
                    documentType: e.target.value as "PERMIT" | "CONTRACT",
                  })
                }
                value={submission.documentType}
              >
                <option value="PERMIT">Izin Resmi (PERMIT)</option>
                <option value="CONTRACT">Kontrak / PKS (CONTRACT)</option>
              </SelectInput>
            </FormField>

            <FormField label="Nomor Registrasi Resmi:">
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, referenceCode: e.target.value })
                }
                placeholder="Contoh: PBG-2026-DPMPTSP-0012"
                value={submission.referenceCode}
              />
            </FormField>
          </div>

          <div className="gridCols2">
            <FormField label="Pihak Lawan / Rekanan:">
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, counterparty: e.target.value })
                }
                placeholder="Contoh: PT Bangun Persada"
                value={submission.counterparty}
              />
            </FormField>

            <FormField label="Instansi Penerbit / Otoritas:">
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, sourceAuthority: e.target.value })
                }
                placeholder="Contoh: Dinas DPMPTSP"
                value={submission.sourceAuthority}
              />
            </FormField>
          </div>

          <div className="gridCols2">
            <FormField label="Tanggal Berlaku:">
              <TextInput
                onChange={(e) =>
                  setSubmission({ ...submission, effectiveDate: e.target.value })
                }
                type="date"
                value={submission.effectiveDate}
              />
            </FormField>

            <FormField label="Tanggal Jatuh Tempo (Expiry):">
              <TextInput
                onChange={(e) => setSubmission({ ...submission, expiryDate: e.target.value })}
                type="date"
                value={submission.expiryDate}
              />
            </FormField>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowLegalModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !submission.title.trim()}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Daftarkan Dokumen"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

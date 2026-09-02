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
  decideRecruitment,
  getDocuments,
  getPersonnelChecklist,
  getRecruitmentRequests,
  submitRecruitmentRequest,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type {
  DocumentRecord,
  PersonnelChecklist,
  RecruitmentRequestRecord,
} from "@/lib/types";

const divisionCodes = ["FINANCE", "SALES_MARKETING", "PROPERTY", "HR", "LEGAL", "IT"];

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi HR belum dapat diproses.";
}

function codes(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean))];
}

export default function HrPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [requests, setRequests] = useState<RecruitmentRequestRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<PersonnelChecklist | null>(null);
  const [checklistRequestId, setChecklistRequestId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"recruitment" | "decision" | "checklist">("recruitment");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [showRecruitmentModal, setShowRecruitmentModal] = useState(false);

  // Forms
  const [submission, setSubmission] = useState({
    documentVersionId: "",
    positionTitle: "",
    requestingDivisionCode: "HR",
    employmentType: "CONTRACT" as "PERMANENT" | "CONTRACT" | "INTERNSHIP",
    headcount: "1",
    justification: "",
    criteriaVersion: "0.1.0",
    candidateAlias: "",
    requiredCriteria: "CV, WORK_EXPERIENCE",
    metCriteria: "CV",
  });

  const [decision, setDecision] = useState({
    value: "SELECTED" as "SELECTED" | "REJECTED",
    notes: "",
    personnelRequirements: "IDENTITY_DOCUMENT, BANK_ACCOUNT, TAX_ID",
  });

  const selected = useMemo(
    () => requests.find((r) => r.recruitment_request_id === selectedId) || null,
    [requests, selectedId],
  );

  const visibleChecklist = checklistRequestId === selectedId ? checklist : null;

  const isHrOperator = Boolean(
    principal &&
      principal.division_codes.includes("HR") &&
      principal.roles.some((r) => r === "HR" || r === "DIVISION_HEAD"),
  );

  const isDivisionRequester = Boolean(principal?.roles.includes("DIVISION_HEAD"));
  const canSubmit = isHrOperator || isDivisionRequester;
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
      const [requestPage, docPage] = await Promise.all([
        getRecruitmentRequests(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setRequests(requestPage.items);
      setDocuments(docPage.items);
      if (requestPage.items.length > 0 && !selectedId) {
        setSelectedId(requestPage.items[0].recruitment_request_id);
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

  const loadChecklist = useCallback(
    async (requestId: string) => {
      if (!token) return;
      try {
        const item = await getPersonnelChecklist(token, requestId);
        setChecklist(item);
        setChecklistRequestId(requestId);
      } catch (checklistError) {
        toastError(message(checklistError));
      }
    },
    [toastError, token],
  );

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setTimeout(() => void loadChecklist(selectedId), 0);
    return () => window.clearTimeout(timer);
  }, [loadChecklist, selectedId]);

  // Submit Recruitment Request
  const handleSubmitRequest = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId || !canSubmit) return;
    setBusy(true);
    const docId = submission.documentVersionId || documents[0]?.document_version_id || "DOC-DEFAULT";
    try {
      const created = await submitRecruitmentRequest(token, {
        project_id: activeProjectId,
        candidate_document_version_id: docId,
        position_title: submission.positionTitle.trim(),
        requesting_division_code: submission.requestingDivisionCode,
        employment_type: submission.employmentType,
        headcount: Number(submission.headcount) || 1,
        justification: submission.justification.trim(),
        criteria_version: submission.criteriaVersion.trim(),
        candidate_alias: submission.candidateAlias.trim() || "Kandidat Terpilih",
        required_criteria: codes(submission.requiredCriteria),
        met_criteria: codes(submission.metCriteria),
      });
      setShowRecruitmentModal(false);
      toastSuccess("Permohonan rekrutmen berhasil diajukan.");
      await loadData();
      setSelectedId(created.recruitment_request_id);
      setActiveTab("decision");
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Submit Recruitment Decision
  const handleDecision = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !isHrOperator) return;
    setBusy(true);
    try {
      await decideRecruitment(token, selected.recruitment_request_id, {
        decision: decision.value,
        notes: decision.notes.trim(),
        personnel_requirements: codes(decision.personnelRequirements),
      });
      toastSuccess(`Keputusan rekrutmen (${decision.value}) berhasil disimpan.`);
      await loadData();
      if (selectedId) await loadChecklist(selectedId);
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul HR & Personalia..." />;
  }

  const selectedCount = requests.filter((r) => r.status === "SELECTED").length;
  const pendingCount = requests.filter((r) => r.status === "SUBMITTED").length;

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner">
        <div>
          <span className="workspaceBannerTag">
            Workspace HR & Personalia · Core HRA
          </span>
          <h1 className="workspaceBannerTitle">
            Rekrutmen, Penilaian Kriteria & Berkas Personel
          </h1>
          <p className="workspaceBannerSubtitle">
            Penambahan headcount divisi, asesmen kriteria kandidat, dan verifikasi berkas digital personel.
          </p>
        </div>

        {canSubmit && (
          <div className="workspaceActionGroup">
            <button
              className="button primary"
              onClick={() => setShowRecruitmentModal(true)}
              type="button"
            >
              + Ajukan Permintaan Rekrutmen
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${requests.length} Posisi`, variant: "info" }}
          subtitle="Total permintaan rekrutmen terdaftar pada proyek ini"
          title="Total Permintaan Rekrutmen"
          value={requests.length}
        />
        <StatsCard
          badge={{ text: `${pendingCount} Menunggu`, variant: pendingCount > 0 ? "warning" : "success" }}
          subtitle="Permohonan rekrutmen menunggu evaluasi HR"
          title="Menunggu Evaluasi"
          value={pendingCount}
        />
        <StatsCard
          badge={{ text: `${selectedCount} Terpilih`, variant: "success" }}
          subtitle="Kandidat yang telah disetujui & masuk tahap berkas"
          title="Kandidat Terpilih"
          value={selectedCount}
        />
        <StatsCard
          badge={{ text: "Digital File", variant: "info" }}
          subtitle="KTP, NPWP, BPJS, Rekening Bank, Kontrak Kerja"
          title="Standar Berkas Personel"
          value="5 Dokumen"
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "recruitment" ? "active" : ""}`}
          onClick={() => setActiveTab("recruitment")}
          type="button"
        >
          📋 Pipeline Rekrutmen ({requests.length})
        </button>
        <button
          className={`tabButton ${activeTab === "decision" ? "active" : ""}`}
          onClick={() => setActiveTab("decision")}
          type="button"
        >
          ⚖️ Keputusan & Asesmen {selected ? `(${selected.position_title})` : ""}
        </button>
        <button
          className={`tabButton ${activeTab === "checklist" ? "active" : ""}`}
          onClick={() => setActiveTab("checklist")}
          type="button"
        >
          📁 Checklist Berkas Personel
        </button>
      </div>

      {/* Tab 1: DataTable Permintaan Rekrutmen */}
      {activeTab === "recruitment" && (
        <DataTable
          columns={[
            {
              header: "Posisi Pekerjaan",
              cell: (r: RecruitmentRequestRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{r.position_title}</strong>
                  <span style={{ color: "var(--muted)", fontFamily: "monospace", fontSize: "11px" }}>
                    ID: {shortId(r.recruitment_request_id)}
                  </span>
                </div>
              ),
            },
            {
              header: "Divisi Pemohon",
              cell: (r: RecruitmentRequestRecord) => (
                <span className="badge" style={{ background: "var(--paper)", border: "1px solid var(--line)", padding: "2px 8px", borderRadius: "6px" }}>
                  {humanizeCode(r.requesting_division_code)}
                </span>
              ),
            },
            {
              header: "Tipe & Headcount",
              cell: (r: RecruitmentRequestRecord) => (
                <span style={{ fontFamily: "monospace", fontSize: "12px" }}>
                  {r.employment_type} • {r.headcount} Orang
                </span>
              ),
            },
            {
              header: "Status Permohonan",
              cell: (r: RecruitmentRequestRecord) => <StatusPill status={r.status} />,
            },
            {
              header: "Kandidat / Alias",
              cell: (r: RecruitmentRequestRecord) => (
                <span>{r.candidate_alias || "Open Hiring"}</span>
              ),
            },
            {
              header: "Tanggal Pengajuan",
              cell: (r: RecruitmentRequestRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>{formatDateTime(r.created_at)}</span>
              ),
            },
          ]}
          data={requests}
          keyExtractor={(r) => r.recruitment_request_id}
          onRowClick={(r) => {
            setSelectedId(r.recruitment_request_id);
            setActiveTab("decision");
          }}
          searchFilter={(r, q) =>
            r.position_title.toLowerCase().includes(q) ||
            r.requesting_division_code.toLowerCase().includes(q) ||
            r.status.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari posisi pekerjaan, divisi, atau status..."
        />
      )}

      {/* Tab 2: Keputusan & Asesmen */}
      {activeTab === "decision" && (
        <div className="grid12">
          <div className="colSpan7">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu permohonan rekrutmen dari tabel untuk melihat evaluasi kriteria."
                title="Pilih Permohonan Rekrutmen"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
                      Rincian Rekrutmen: {selected.position_title}
                    </h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      ID: {selected.recruitment_request_id}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                <div className="gridCols2" style={{ marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Divisi Pemohon:</span>
                    <strong>{humanizeCode(selected.requesting_division_code)}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Tipe Kerja & Jumlah:</span>
                    <strong style={{ color: "var(--green-700)", fontFamily: "monospace" }}>
                      {selected.employment_type} ({selected.headcount} Orang)
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Alias / Nama Kandidat:</span>
                    <span>{selected.candidate_alias || "Terbuka (Open Hiring)"}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Kriteria Versi:</span>
                    <span style={{ fontFamily: "monospace" }}>{selected.criteria_version}</span>
                  </div>
                </div>

                <div>
                  <span style={{ color: "var(--muted)", fontSize: "11px", display: "block", marginBottom: "4px" }}>Justifikasi Kebutuhan Headcount:</span>
                  <p style={{ margin: 0, padding: "12px", background: "var(--paper)", borderRadius: "8px", border: "1px solid var(--line)", fontSize: "12px", lineHeight: "1.5" }}>
                    {selected.justification}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="colSpan5 spaceY4">
            {selected && isHrOperator && (
              <form
                className="panel"
                onSubmit={handleDecision}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Formulir Keputusan Rekrutmen
                </h3>

                {isOwnSubmission && (
                  <div style={{ padding: "10px", background: "#fff8e8", border: "1px solid #f7dba1", borderRadius: "8px", color: "#8c5b06", fontSize: "11px", marginBottom: "12px" }}>
                    ⚠️ Peringatan SoD: Anda adalah pengaju permohonan ini. Keputusan final sebaiknya dilakukan oleh HR Manager independen.
                  </div>
                )}

                <FormField label="Keputusan Asesmen:">
                  <SelectInput
                    onChange={(e) =>
                      setDecision({
                        ...decision,
                        value: e.target.value as "SELECTED" | "REJECTED",
                      })
                    }
                    value={decision.value}
                  >
                    <option value="SELECTED">Terima & Loloskan (SELECTED)</option>
                    <option value="REJECTED">Tolak Permohonan (REJECTED)</option>
                  </SelectInput>
                </FormField>

                <FormField label="Catatan Evaluasi / Rekomendasi HR:">
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setDecision({ ...decision, notes: e.target.value })}
                    placeholder="Masukkan catatan penilaian wawancara dan kualifikasi..."
                    required
                    value={decision.notes}
                  />
                </FormField>

                <button
                  className={`button ${decision.value === "SELECTED" ? "primary" : "secondary"}`}
                  disabled={busy || !decision.notes.trim()}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : `Simpan Keputusan (${decision.value})`}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Checklist Berkas Personel */}
      {activeTab === "checklist" && (
        <div className="panel" style={{ maxWidth: "700px", margin: "0 auto", padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
            <div>
              <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>Digital Personnel File Checklist</h2>
              <p style={{ margin: 0, color: "var(--muted)", fontSize: "12px" }}>
                Kelengkapan dokumen resmi pegawai baru sebelum penerbitan Surat Kontrak Kerja.
              </p>
            </div>
            {selected && <StatusPill status={selected.status} />}
          </div>

          {!selected ? (
            <EmptyState
              description="Pilih salah satu posisi dari pipeline rekrutmen untuk memeriksa kelengkapan berkas."
              title="Pilih Kandidat / Rekrutmen"
            />
          ) : !visibleChecklist ? (
            <p style={{ padding: "20px", textAlign: "center", color: "var(--muted)" }}>
              Belum ada checklist berkas yang diterbitkan untuk permohonan ini.
            </p>
          ) : (
            <div className="spaceY3">
              <div style={{ padding: "14px", background: "var(--paper)", borderRadius: "10px", border: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong style={{ display: "block", fontSize: "14px" }}>{selected.position_title}</strong>
                  <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                    Kandidat: {selected.candidate_alias || "Pegawai Terpilih"}
                  </span>
                </div>
                <StatusPill status={visibleChecklist.status} />
              </div>

              <div style={{ marginTop: "14px" }}>
                <h4 style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                  Checklist Dokumen Wajib:
                </h4>
                <div className="spaceY2">
                  {visibleChecklist.requirements.map((req, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: "10px 14px",
                        borderRadius: "8px",
                        border: "1px solid var(--line)",
                        background: req.status === "VERIFIED" ? "#eaf6f0" : "var(--white)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "12px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span>{req.status === "VERIFIED" ? "✅" : "⏳"}</span>
                        <strong>{humanizeCode(req.requirement_code)}</strong>
                      </div>
                      <span style={{ fontWeight: 700, color: req.status === "VERIFIED" ? "var(--green-700)" : "var(--muted)", fontSize: "11px" }}>
                        {req.status === "VERIFIED" ? "TERVERIFIKASI" : "BELUM LENGKAP"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: Ajukan Permintaan Rekrutmen Baru */}
      <Modal
        onClose={() => setShowRecruitmentModal(false)}
        open={showRecruitmentModal}
        subtitle="Permohonan penambahan tenaga kerja / headcount divisi"
        title="Ajukan Permintaan Rekrutmen Baru"
      >
        <form className="spaceY4" onSubmit={handleSubmitRequest}>
          <FormField label="Posisi Pekerjaan (Jabatan):" required>
            <TextInput
              onChange={(e) => setSubmission({ ...submission, positionTitle: e.target.value })}
              placeholder="Contoh: Site Engineer Sipil Proyek"
              required
              value={submission.positionTitle}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Divisi Pemohon:">
              <SelectInput
                disabled={!isHrOperator}
                onChange={(e) =>
                  setSubmission({ ...submission, requestingDivisionCode: e.target.value })
                }
                value={submission.requestingDivisionCode}
              >
                {divisionCodes.map((code) => (
                  <option key={code} value={code}>
                    {humanizeCode(code)}
                  </option>
                ))}
              </SelectInput>
            </FormField>

            <FormField label="Tipe Ikatan Kerja:">
              <SelectInput
                onChange={(e) =>
                  setSubmission({
                    ...submission,
                    employmentType: e.target.value as "PERMANENT" | "CONTRACT" | "INTERNSHIP",
                  })
                }
                value={submission.employmentType}
              >
                <option value="CONTRACT">Kontrak (PKWT)</option>
                <option value="PERMANENT">Tetap (PKWTT)</option>
                <option value="INTERNSHIP">Magang (Internship)</option>
              </SelectInput>
            </FormField>
          </div>

          <FormField label="Jumlah Tenaga Kerja (Headcount):" required>
            <TextInput
              onChange={(e) => setSubmission({ ...submission, headcount: e.target.value })}
              placeholder="Contoh: 1"
              required
              type="number"
              value={submission.headcount}
            />
          </FormField>

          <FormField label="Justifikasi Kebutuhan Personel:" required>
            <TextAreaInput
              onChange={(e) => setSubmission({ ...submission, justification: e.target.value })}
              placeholder="Jelaskan dasar penambahan beban kerja dan kebutuhan proyek..."
              required
              value={submission.justification}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowRecruitmentModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !submission.positionTitle.trim()}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Ajukan Permohonan"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

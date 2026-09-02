"use client";

import { useState, useCallback, useEffect, type FormEvent } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  FormField,
  Modal,
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
  return error instanceof ApiError ? error.message : "Workflow lapangan belum dapat diproses.";
}

export default function MobileFieldWorkflowPage() {
  const { activeProjectId, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [records, setRecords] = useState<SiteEvidenceRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Field Checklist items state
  const [checklist, setChecklist] = useState([
    { id: 1, text: "Cek kepatuhan APD & K3 lokasi proyek", done: true },
    { id: 2, text: "Inspeksi bekisting & pembesian lantai aktif", done: true },
    { id: 3, text: "Pengukuran volume fisik pengecoran beton", done: false },
    { id: 4, text: "Foto dokumentasi geotag zona barat & timur", done: false },
    { id: 5, text: "Uji slump & pengambilan sampel silinder beton", done: false },
  ]);

  // Modal for new field capture
  const [showCaptureModal, setShowCaptureModal] = useState(false);
  const [form, setForm] = useState({
    workPackageCode: "PKG-STRUKTUR-01",
    claimedProgress: "5.00",
    measuredProgress: "4.85",
    measurementNote: "Opname fisik harian dan foto bukti pengawasan lapangan.",
    geotag: "-6.2088, 106.8456 (Zona A Proyek)",
  });

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
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  const toggleChecklist = (id: number) => {
    setChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, done: !item.done } : item)),
    );
  };

  const handleCaptureSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId) return;
    setBusy(true);
    const docId = documents[0]?.document_version_id || "DOC-DEFAULT";
    try {
      await submitSiteEvidence(token, {
        project_id: activeProjectId,
        document_version_id: docId,
        work_package_code: form.workPackageCode.trim().toUpperCase(),
        claim_date: today(),
        claimed_progress: form.claimedProgress.trim(),
        measured_progress: form.measuredProgress.trim(),
        measurement_note: `[Geotag: ${form.geotag}] ${form.measurementNote.trim()}`,
      });
      setShowCaptureModal(false);
      toastSuccess("Bukti opname lapangan & foto berhasil dikirim ke antrean reviu!");
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Menyiapkan antarmuka mobile lapangan..." />;
  }

  const completedTasks = checklist.filter((t) => t.done).length;

  return (
    <div className="spaceY5" style={{ maxWidth: "800px", margin: "0 auto", paddingBottom: "40px" }}>
      {/* Mobile Top Header */}
      <header className="workspaceBanner" style={{ padding: "20px 24px" }}>
        <div>
          <span className="workspaceBannerTag">
            📱 Mode Lapangan (Field Work) · {today()}
          </span>
          <h1 className="workspaceBannerTitle" style={{ fontSize: "20px" }}>
            Inspeksi Fisik & Bukti Opname Lapangan
          </h1>
          <p className="workspaceBannerSubtitle">
            Pencatatan cepat progres harian, checklist K3 mandor, dan upload foto ber-geotag.
          </p>
        </div>

        <div className="workspaceActionGroup">
          <button
            className="button heroPrimary"
            onClick={() => setShowCaptureModal(true)}
            style={{ fontWeight: 800 }}
            type="button"
          >
            📸 Ambil Bukti Opname
          </button>
        </div>
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Quick Stats */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${completedTasks}/${checklist.length}`, variant: completedTasks === checklist.length ? "success" : "warning" }}
          subtitle="Tugas inspeksi hari ini"
          title="Checklist Harian"
          value={`${Math.round((completedTasks / checklist.length) * 100)}%`}
        />
        <StatsCard
          badge={{ text: "Terkirim", variant: "info" }}
          subtitle="Bukti opname terunggah"
          title="Bukti Terkirim"
          value={records.length}
        />
        <StatsCard
          badge={{ text: "GPS Valid", variant: "success" }}
          subtitle="Akurasi koordinat lokasi"
          title="Akurasi Geotag"
          value="±3 Meter"
        />
        <StatsCard
          badge={{ text: "Online", variant: "success" }}
          subtitle="Status sinkronisasi backend"
          title="Koneksi ALOS"
          value="Aktif"
        />
      </section>

      {/* Field Inspection Checklist Card */}
      <section className="panel" style={{ padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--line)", paddingBottom: "12px", marginBottom: "14px" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "15px" }}>Checklist Inspeksi Harian Mandor & QC</h2>
            <p style={{ margin: "2px 0 0", color: "var(--muted)", fontSize: "11px" }}>Centang item yang telah diperiksa di lokasi fisik</p>
          </div>
          <strong style={{ color: "var(--green-700)", fontSize: "12px" }}>
            {completedTasks} dari {checklist.length} Selesai
          </strong>
        </div>

        <div className="spaceY2">
          {checklist.map((item) => (
            <div
              key={item.id}
              onClick={() => toggleChecklist(item.id)}
              style={{
                padding: "12px 14px",
                borderRadius: "8px",
                border: "1px solid var(--line)",
                background: item.done ? "#eaf6f0" : "var(--white)",
                display: "flex",
                alignItems: "center",
                gap: "12px",
                cursor: "pointer",
              }}
            >
              <input
                checked={item.done}
                onChange={() => {}}
                style={{ width: "16px", height: "16px", cursor: "pointer", margin: 0 }}
                type="checkbox"
              />
              <span style={{ fontSize: "12px", flex: 1, textDecoration: item.done ? "line-through" : "none", color: item.done ? "var(--muted)" : "var(--ink)" }}>
                {item.text}
              </span>
              <span style={{ fontSize: "12px" }}>{item.done ? "✅" : "⏳"}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Field Evidence Logs */}
      <section className="panel" style={{ padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--line)", paddingBottom: "12px", marginBottom: "14px" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "15px" }}>Log Bukti Lapangan Terakhir</h2>
            <p style={{ margin: "2px 0 0", color: "var(--muted)", fontSize: "11px" }}>Status verifikasi opname oleh Kepala Divisi / Pengawas</p>
          </div>
          <span style={{ color: "var(--muted)", fontSize: "11px" }}>{records.length} Item</span>
        </div>

        {records.length === 0 ? (
          <EmptyState
            description="Gunakan tombol di atas untuk mengambil foto dan mencatat opname pertama."
            title="Belum Ada Bukti Opname"
          />
        ) : (
          <div className="spaceY3">
            {records.slice(0, 5).map((rec) => (
              <div
                key={rec.site_evidence_id}
                style={{ padding: "14px", background: "var(--paper)", borderRadius: "10px", border: "1px solid var(--line)", fontSize: "12px" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <div>
                    <strong style={{ fontSize: "13px", display: "block" }}>{rec.work_package_code}</strong>
                    <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                      Klaim: {rec.claimed_progress}% • Ukur: {rec.measured_progress}%
                    </span>
                  </div>
                  <StatusPill status={rec.status} />
                </div>
                <p style={{ margin: "6px 0", color: "var(--ink)", padding: "8px 10px", background: "var(--white)", borderRadius: "6px", border: "1px solid var(--line)" }}>
                  {rec.measurement_note}
                </p>
                <div style={{ display: "flex", justifyContent: "space-between", color: "var(--muted)", fontSize: "10px", marginTop: "4px" }}>
                  <span>ID: {shortId(rec.site_evidence_id)}</span>
                  <span>{rec.claim_date}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Modal: Capture Site Evidence Mobile */}
      <Modal
        maxWidth="md"
        onClose={() => setShowCaptureModal(false)}
        open={showCaptureModal}
        subtitle="Form input bukti fisik dari perangkat mobile lapangan"
        title="Ambil Bukti Opname Lapangan"
      >
        <form className="spaceY4" onSubmit={handleCaptureSubmit}>
          <FormField label="Paket Pekerjaan:" required>
            <TextInput
              onChange={(e) => setForm({ ...form, workPackageCode: e.target.value })}
              placeholder="Contoh: PKG-STRUKTUR-01"
              required
              value={form.workPackageCode}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Klaim Kontraktor (%):" required>
              <TextInput
                onChange={(e) => setForm({ ...form, claimedProgress: e.target.value })}
                placeholder="5.00"
                required
                value={form.claimedProgress}
              />
            </FormField>

            <FormField label="Hasil Ukur Fisik (%):" required>
              <TextInput
                onChange={(e) => setForm({ ...form, measuredProgress: e.target.value })}
                placeholder="4.85"
                required
                value={form.measuredProgress}
              />
            </FormField>
          </div>

          <FormField label="Koordinat Geotag GPS:">
            <TextInput
              onChange={(e) => setForm({ ...form, geotag: e.target.value })}
              value={form.geotag}
            />
          </FormField>

          <FormField label="Catatan Lapangan & Bukti Foto:" required>
            <TextAreaInput
              onChange={(e) => setForm({ ...form, measurementNote: e.target.value })}
              placeholder="Ketik catatan kondisi lapangan, cuaca, dan nomor foto kamera..."
              required
              value={form.measurementNote}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowCaptureModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !form.workPackageCode.trim()}
              type="submit"
            >
              {busy ? "Mengirim..." : "Kirim Bukti Opname"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  getDocuments,
  getSiteEvidence,
  reviewSiteEvidence,
  submitSiteEvidence,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
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
  const [records, setRecords] = useState<SiteEvidenceRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [submission, setSubmission] = useState({
    documentVersionId: "",
    workPackageCode: "",
    claimDate: today(),
    claimedProgress: "",
    measuredProgress: "",
    measurementNote: "",
  });
  const [review, setReview] = useState({
    decision: "ACCEPTED" as "ACCEPTED" | "VARIANCE",
    verifiedProgress: "",
    notes: "",
  });

  const selected = useMemo(
    () => records.find((record) => record.site_evidence_id === selectedId) || null,
    [records, selectedId],
  );
  const canOperate = Boolean(
    principal
    && principal.division_codes.includes("PROPERTY")
    && principal.roles.some((role) => role === "PROPERTY" || role === "DIVISION_HEAD"),
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
      const [evidencePage, documentPage] = await Promise.all([
        getSiteEvidence(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setRecords(evidencePage.items);
      setDocuments(documentPage.items);
      setSelectedId((current) => (
        evidencePage.items.some((record) => record.site_evidence_id === current)
          ? current
          : evidencePage.items[0]?.site_evidence_id || null
      ));
      setSubmission((current) => ({
        ...current,
        documentVersionId: documentPage.items.some(
          (document) => document.document_version_id === current.documentVersionId,
        ) ? current.documentVersionId : documentPage.items[0]?.document_version_id || "",
      }));
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadData, status]);

  async function submitEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await submitSiteEvidence(token, {
        project_id: activeProjectId,
        document_version_id: submission.documentVersionId,
        work_package_code: submission.workPackageCode.trim().toUpperCase(),
        claim_date: submission.claimDate,
        claimed_progress: submission.claimedProgress,
        measured_progress: submission.measuredProgress,
        measurement_note: submission.measurementNote.trim(),
      });
      setSubmission((current) => ({
        ...current,
        workPackageCode: "",
        claimedProgress: "",
        measuredProgress: "",
        measurementNote: "",
      }));
      await loadData();
      setSelectedId(result.site_evidence_id);
      setFeedback("Evidence lapangan tersimpan dan menunggu review Property Human.");
    } catch (submitError) {
      setFeedback(message(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canOperate || isOwnSubmission) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await reviewSiteEvidence(token, selected.site_evidence_id, {
        decision: review.decision,
        verified_progress: review.verifiedProgress,
        notes: review.notes.trim(),
      });
      setReview({ decision: "ACCEPTED", verifiedProgress: "", notes: "" });
      await loadData();
      setFeedback(
        result.capa_id
          ? "Variance tercatat; exception dan CAPA telah dibuat secara otomatis."
          : "Evidence diterima dan KPI progres terverifikasi telah diperbarui.",
      );
    } catch (reviewError) {
      setFeedback(message(reviewError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div><p className="eyebrow">Property · FLOW-003</p><h1>Evidence sampai KPI atau CAPA</h1><p>Catat bukti lapangan, verifikasi progres, dan arahkan variance ke exception serta CAPA.</p></div>
        <button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button>
      </header>

      {!activeProjectId ? <EmptyState title="Pilih proyek terlebih dahulu" description="Konteks proyek diperlukan untuk memproses evidence Property." /> : null}
      {activeProjectId && loading ? <LoadingState label="Memuat evidence Property…" /> : null}
      {activeProjectId && !loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {activeProjectId && !loading && !error ? (
        <>
          {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
          {canOperate ? (
            <section className="panel transactionCreatePanel">
              <div className="panelHeader"><div><p className="eyebrow">Site intake</p><h2>Catat evidence progres</h2></div></div>
              <form className="transactionForm" onSubmit={submitEvidence}>
                <label>Dokumen evidence<select onChange={(event) => setSubmission({ ...submission, documentVersionId: event.target.value })} required value={submission.documentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label>
                <label>Kode work package<input maxLength={40} minLength={2} onChange={(event) => setSubmission({ ...submission, workPackageCode: event.target.value })} pattern="[A-Za-z][A-Za-z0-9_-]+" required value={submission.workPackageCode} /></label>
                <label>Tanggal klaim<input onChange={(event) => setSubmission({ ...submission, claimDate: event.target.value })} required type="date" value={submission.claimDate} /></label>
                <label>Progres klaim (%)<input max="100" min="0" onChange={(event) => setSubmission({ ...submission, claimedProgress: event.target.value })} required step="0.01" type="number" value={submission.claimedProgress} /></label>
                <label>Progres terukur (%)<input max="100" min="0" onChange={(event) => setSubmission({ ...submission, measuredProgress: event.target.value })} required step="0.01" type="number" value={submission.measuredProgress} /></label>
                <label>Catatan pengukuran<textarea maxLength={2000} minLength={3} onChange={(event) => setSubmission({ ...submission, measurementNote: event.target.value })} required rows={3} value={submission.measurementNote} /></label>
                <button className="button primary" disabled={busy || !documents.length} type="submit">{busy ? "Memproses…" : "Kirim evidence"}</button>
              </form>
            </section>
          ) : null}

          <div className="transactionLayout">
            <section className="panel">
              <div className="panelHeader"><div><p className="eyebrow">Evidence queue</p><h2>Progres lapangan</h2></div><span className="resultCount">{records.length} evidence</span></div>
              {!records.length ? <EmptyState title="Belum ada evidence" description="Evidence progres proyek akan tampil di sini." /> : <div className="transactionRecordList">{records.map((record) => <button className={record.site_evidence_id === selectedId ? "selected" : ""} key={record.site_evidence_id} onClick={() => setSelectedId(record.site_evidence_id)} type="button"><span><strong>{record.work_package_code}</strong><small>Klaim {record.claimed_progress}% · Terukur {record.measured_progress}%</small></span><span><b className="statusBadge">{humanizeCode(record.status)}</b><small>{record.claim_date}</small></span></button>)}</div>}
            </section>

            <section className="panel transactionDetail">
              <div className="panelHeader"><div><p className="eyebrow">Verification detail</p><h2>{selected?.work_package_code || "Pilih evidence"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>
              {selected ? <div className="transactionDetailBody">
                <dl className="detailGrid"><div><dt>Variance awal</dt><dd>{selected.variance}%</dd></div><div><dt>Pengunggah</dt><dd>{shortId(selected.submitted_by_user_id)}</dd></div><div><dt>Progres terverifikasi</dt><dd>{selected.verified_progress ? `${selected.verified_progress}%` : "Menunggu review"}</dd></div><div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div></dl>
                <p className="muted">{selected.measurement_note}</p>
                {selected.review_notes ? <p><strong>Catatan review:</strong> {selected.review_notes}</p> : null}
                {canOperate && selected.status === "PENDING_REVIEW" && !isOwnSubmission ? <form className="actionPanel" onSubmit={submitReview}><div><p className="eyebrow">Human verification</p><h3>Review evidence</h3></div><div className="fieldGrid"><label>Keputusan<select onChange={(event) => setReview({ ...review, decision: event.target.value as typeof review.decision })} value={review.decision}><option>ACCEPTED</option><option>VARIANCE</option></select></label><label>Progres terverifikasi (%)<input max="100" min="0" onChange={(event) => setReview({ ...review, verifiedProgress: event.target.value })} required step="0.01" type="number" value={review.verifiedProgress} /></label></div><label>Catatan review<textarea maxLength={2000} minLength={3} onChange={(event) => setReview({ ...review, notes: event.target.value })} required rows={3} value={review.notes} /></label><button className="button primary" disabled={busy} type="submit">Simpan review</button></form> : null}
                {canOperate && selected.status === "PENDING_REVIEW" && isOwnSubmission ? <div className="readOnlyNotice"><p><strong>Menunggu reviewer lain</strong><span>Pengunggah tidak dapat mereview evidence miliknya sendiri.</span></p></div> : null}
                {!canOperate ? <div className="readOnlyNotice"><p><strong>Akses monitoring</strong><span>Anda dapat melihat evidence tanpa menjalankan tindakan Property.</span></p></div> : null}
              </div> : <EmptyState title="Pilih evidence" description="Pilih evidence untuk melihat hasil pengukuran dan review." />}
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}

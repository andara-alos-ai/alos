"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  getDocuments,
  getLegalCases,
  reviewLegalDocument,
  submitLegalDocument,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
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
  const [cases, setCases] = useState<LegalCaseRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
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
    officialSourceVerified: false,
    notes: "",
  });

  const selected = useMemo(
    () => cases.find((item) => item.legal_case_id === selectedId) || null,
    [cases, selectedId],
  );
  const canOperate = Boolean(
    principal
    && principal.division_codes.includes("LEGAL")
    && principal.roles.some((role) => role === "LEGAL" || role === "DIVISION_HEAD"),
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
      const [casePage, documentPage] = await Promise.all([
        getLegalCases(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setCases(casePage.items);
      setDocuments(documentPage.items);
      setSelectedId((current) => (
        casePage.items.some((item) => item.legal_case_id === current)
          ? current
          : casePage.items[0]?.legal_case_id || null
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

  async function submitDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await submitLegalDocument(token, {
        project_id: activeProjectId,
        document_version_id: submission.documentVersionId,
        document_type: submission.documentType,
        reference_code: submission.referenceCode.trim(),
        title: submission.title.trim(),
        counterparty: submission.documentType === "CONTRACT" ? submission.counterparty.trim() : null,
        source_authority: submission.documentType === "PERMIT" ? submission.sourceAuthority.trim() : null,
        effective_date: submission.effectiveDate || null,
        expiry_date: submission.expiryDate || null,
      });
      setSubmission((current) => ({
        ...current,
        referenceCode: "",
        title: "",
        counterparty: "",
        sourceAuthority: "",
        effectiveDate: "",
        expiryDate: "",
      }));
      await loadData();
      setSelectedId(result.legal_case_id);
      setFeedback("Dokumen telah dianalisis dan menunggu keputusan Legal Human.");
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
      const result = await reviewLegalDocument(token, selected.legal_case_id, {
        decision: review.decision,
        legal_status: decisionStatus[review.decision],
        official_source_verified: review.officialSourceVerified,
        notes: review.notes.trim(),
      });
      setReview({ decision: "APPROVED", officialSourceVerified: false, notes: "" });
      await loadData();
      setFeedback(
        result.exception_id
          ? "Keputusan tersimpan dan exception Legal telah dibuka."
          : "Dokumen telah disetujui dan sumber resminya tercatat.",
      );
    } catch (reviewError) {
      setFeedback(message(reviewError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Legal · FLOW-004</p><h1>Izin dan Kontrak</h1><p>Kelola intake dokumen, analisis agent, evidence, verifikasi sumber resmi, dan keputusan Legal Human.</p></div><button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button></header>
      {!activeProjectId ? <EmptyState title="Pilih proyek terlebih dahulu" description="Dokumen Legal selalu diproses dalam konteks proyek." /> : null}
      {activeProjectId && loading ? <LoadingState label="Memuat kasus Legal…" /> : null}
      {activeProjectId && !loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {activeProjectId && !loading && !error ? <>
        {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
        {canOperate ? <section className="panel transactionCreatePanel"><div className="panelHeader"><div><p className="eyebrow">Document intake</p><h2>Ajukan izin atau kontrak</h2></div></div><form className="transactionForm" onSubmit={submitDocument}>
          <label>Jenis dokumen<select onChange={(event) => setSubmission({ ...submission, documentType: event.target.value as typeof submission.documentType })} value={submission.documentType}><option>PERMIT</option><option>CONTRACT</option></select></label>
          <label>Dokumen evidence<select onChange={(event) => setSubmission({ ...submission, documentVersionId: event.target.value })} required value={submission.documentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label>
          <label>Kode referensi<input maxLength={120} minLength={2} onChange={(event) => setSubmission({ ...submission, referenceCode: event.target.value })} required value={submission.referenceCode} /></label>
          <label>Judul<input maxLength={240} minLength={3} onChange={(event) => setSubmission({ ...submission, title: event.target.value })} required value={submission.title} /></label>
          {submission.documentType === "PERMIT" ? <label>Instansi penerbit<input maxLength={240} minLength={2} onChange={(event) => setSubmission({ ...submission, sourceAuthority: event.target.value })} required value={submission.sourceAuthority} /></label> : <label>Pihak lawan<input maxLength={240} minLength={2} onChange={(event) => setSubmission({ ...submission, counterparty: event.target.value })} required value={submission.counterparty} /></label>}
          <label>Tanggal efektif<input onChange={(event) => setSubmission({ ...submission, effectiveDate: event.target.value })} type="date" value={submission.effectiveDate} /></label>
          <label>Tanggal berakhir<input min={submission.effectiveDate || undefined} onChange={(event) => setSubmission({ ...submission, expiryDate: event.target.value })} type="date" value={submission.expiryDate} /></label>
          <button className="button primary" disabled={busy || !documents.length} type="submit">{busy ? "Memproses…" : "Kirim ke Legal"}</button>
        </form></section> : null}

        <div className="transactionLayout">
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Legal queue</p><h2>Kasus izin dan kontrak</h2></div><span className="resultCount">{cases.length} kasus</span></div>{!cases.length ? <EmptyState title="Belum ada kasus" description="Izin dan kontrak proyek akan tampil di sini." /> : <div className="transactionRecordList">{cases.map((item) => <button className={item.legal_case_id === selectedId ? "selected" : ""} key={item.legal_case_id} onClick={() => setSelectedId(item.legal_case_id)} type="button"><span><strong>{item.title}</strong><small>{item.document_type} · {item.reference_code}</small></span><span><b className="statusBadge">{humanizeCode(item.status)}</b><small>{formatDateTime(item.created_at)}</small></span></button>)}</div>}</section>
          <section className="panel transactionDetail"><div className="panelHeader"><div><p className="eyebrow">Legal detail</p><h2>{selected?.title || "Pilih kasus"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>{selected ? <div className="transactionDetailBody">
            <dl className="detailGrid"><div><dt>Jenis</dt><dd>{humanizeCode(selected.document_type)}</dd></div><div><dt>Referensi</dt><dd>{selected.reference_code}</dd></div><div><dt>Penerbit/Pihak</dt><dd>{selected.source_authority || selected.counterparty || "—"}</dd></div><div><dt>Pengaju</dt><dd>{shortId(selected.submitted_by_user_id)}</dd></div><div><dt>Status Legal</dt><dd>{selected.legal_status ? humanizeCode(selected.legal_status) : "Menunggu"}</dd></div><div><dt>Sumber resmi</dt><dd>{selected.official_source_verified ? "Terverifikasi" : "Belum"}</dd></div></dl>
            {canOperate && selected.status === "PENDING_REVIEW" && !isOwnSubmission ? <form className="actionPanel" onSubmit={submitReview}><div><p className="eyebrow">Human decision</p><h3>Review Legal</h3></div><label>Keputusan<select onChange={(event) => setReview({ ...review, decision: event.target.value as LegalDecision })} value={review.decision}><option>APPROVED</option><option>REVISION_REQUESTED</option><option>REJECTED</option></select></label><label className="checkField"><input checked={review.officialSourceVerified} onChange={(event) => setReview({ ...review, officialSourceVerified: event.target.checked })} type="checkbox" /><span>Sumber resmi telah diverifikasi</span></label><label>Catatan<textarea maxLength={3000} minLength={3} onChange={(event) => setReview({ ...review, notes: event.target.value })} required rows={4} value={review.notes} /></label><button className="button primary" disabled={busy} type="submit">Simpan keputusan</button></form> : null}
            {canOperate && selected.status === "PENDING_REVIEW" && isOwnSubmission ? <div className="readOnlyNotice"><p><strong>Menunggu reviewer lain</strong><span>Pengaju tidak dapat mereview dokumen Legal miliknya sendiri.</span></p></div> : null}
            {!canOperate ? <div className="readOnlyNotice"><p><strong>Akses monitoring</strong><span>Anda dapat melihat status tanpa mengambil keputusan Legal.</span></p></div> : null}
          </div> : <EmptyState title="Pilih kasus" description="Pilih izin atau kontrak untuk melihat metadata dan tindakan review." />}</section>
        </div>
      </> : null}
    </>
  );
}

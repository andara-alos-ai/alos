"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  generateExecutiveBrief,
  getExecutiveBriefs,
  reviewExecutiveBrief,
} from "@/lib/api";
import { formatDateTime, humanizeCode } from "@/lib/format";
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
  const period = useMemo(() => initialPeriod(), []);
  const [briefs, setBriefs] = useState<ExecutiveBriefRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
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
    () => briefs.find((brief) => brief.executive_brief_id === selectedId) || null,
    [briefs, selectedId],
  );
  const canGenerate = Boolean(
    principal?.roles.some((role) => role === "DIRECTOR" || role === "AI_EXECUTIVE"),
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
      setSelectedId((current) => (
        page.items.some((brief) => brief.executive_brief_id === current)
          ? current
          : page.items[0]?.executive_brief_id || null
      ));
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

  async function generateBrief(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !canGenerate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await generateExecutiveBrief(token, {
        title: briefForm.title.trim(),
        period_start: briefForm.periodStart,
        period_end: briefForm.periodEnd,
        project_id: activeProjectId,
      });
      await loadData();
      setSelectedId(result.executive_brief_id);
      setFeedback("Brief dibuat dari snapshot data sistem dan menunggu review Direktur Utama.");
    } catch (generateError) {
      setFeedback(message(generateError));
    } finally {
      setBusy(false);
    }
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canReview) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await reviewExecutiveBrief(token, selected.executive_brief_id, {
        decision: review.decision,
        notes: review.notes.trim(),
      });
      setReview({ decision: "PUBLISHED", notes: "" });
      await loadData();
      setFeedback(
        result.exception_id
          ? "Revisi diminta dan exception Executive Brief telah dibuka."
          : "Executive Brief telah diterbitkan oleh Direktur Utama.",
      );
    } catch (reviewError) {
      setFeedback(message(reviewError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">AI Executive · FLOW-006</p><h1>Executive Brief</h1><p>Agregasikan KPI, approval, exception, CAPA, dan transaksi menjadi brief bersumber untuk Direktur Utama.</p></div><button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button></header>
      {loading ? <LoadingState label="Memuat Executive Brief…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {!loading && !error ? <>
        {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
        {canGenerate ? <section className="panel transactionCreatePanel"><div className="panelHeader"><div><p className="eyebrow">System snapshot</p><h2>Buat brief baru</h2></div><span className="statusBadge">{activeProjectId ? "Project scope" : "Organization scope"}</span></div><form className="transactionForm" onSubmit={generateBrief}>
          <label>Judul<input maxLength={200} minLength={3} onChange={(event) => setBriefForm({ ...briefForm, title: event.target.value })} required value={briefForm.title} /></label>
          <label>Awal periode<input max={briefForm.periodEnd} onChange={(event) => setBriefForm({ ...briefForm, periodStart: event.target.value })} required type="date" value={briefForm.periodStart} /></label>
          <label>Akhir periode<input min={briefForm.periodStart} onChange={(event) => setBriefForm({ ...briefForm, periodEnd: event.target.value })} required type="date" value={briefForm.periodEnd} /></label>
          <button className="button primary" disabled={busy} type="submit">{busy ? "Menyusun snapshot…" : "Buat Executive Brief"}</button>
        </form></section> : null}

        <div className="transactionLayout">
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Brief archive</p><h2>Daftar brief</h2></div><span className="resultCount">{briefs.length} brief</span></div>{!briefs.length ? <EmptyState title="Belum ada brief" description="Buat brief dari data sistem pada periode yang dipilih." /> : <div className="transactionRecordList">{briefs.map((brief) => <button className={brief.executive_brief_id === selectedId ? "selected" : ""} key={brief.executive_brief_id} onClick={() => setSelectedId(brief.executive_brief_id)} type="button"><span><strong>{brief.title}</strong><small>{brief.period_start} — {brief.period_end}</small></span><span><b className="statusBadge">{humanizeCode(brief.status)}</b><small>{formatDateTime(brief.created_at)}</small></span></button>)}</div>}</section>
          <section className="panel transactionDetail"><div className="panelHeader"><div><p className="eyebrow">Director brief</p><h2>{selected?.title || "Pilih brief"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>{selected ? <div className="transactionDetailBody">
            <div className="metricGrid compact">{Object.entries(selected.summary_counts).map(([name, value]) => <article className="metricCard" key={name}><div><small>{humanizeCode(name)}</small><strong>{value}</strong></div></article>)}</div>
            <section className="briefNarrative"><h3>Ringkasan</h3><p>{selected.narrative}</p></section>
            <dl className="detailGrid"><div><dt>Decision item</dt><dd>{selected.decision_item_count}</dd></div><div><dt>Sumber data</dt><dd>{selected.source_references.length} referensi</dd></div><div><dt>Reviewer</dt><dd>{selected.reviewer_user_id ? "Direktur Utama" : "Menunggu"}</dd></div><div><dt>Diperbarui</dt><dd>{formatDateTime(selected.updated_at)}</dd></div></dl>
            <details className="sourceReferences"><summary>Lihat lineage sumber</summary><ul>{selected.source_references.map((reference) => <li key={reference}><code>{reference}</code></li>)}</ul></details>
            {canReview && selected.status === "PENDING_REVIEW" ? <form className="actionPanel" onSubmit={submitReview}><div><p className="eyebrow">Director review</p><h3>Keputusan brief</h3></div><label>Keputusan<select onChange={(event) => setReview({ ...review, decision: event.target.value as typeof review.decision })} value={review.decision}><option>PUBLISHED</option><option>REVISION_REQUESTED</option></select></label><label>Catatan<textarea maxLength={3000} minLength={3} onChange={(event) => setReview({ ...review, notes: event.target.value })} required rows={3} value={review.notes} /></label><button className="button primary" disabled={busy} type="submit">Simpan keputusan</button></form> : null}
            {!canReview && selected.status === "PENDING_REVIEW" ? <div className="readOnlyNotice"><p><strong>Menunggu Direktur Utama</strong><span>AI Executive menyiapkan brief; keputusan penerbitan tetap dilakukan Direktur.</span></p></div> : null}
          </div> : <EmptyState title="Pilih brief" description="Pilih brief untuk membaca snapshot, lineage, dan keputusan Direktur." />}</section>
        </div>
      </> : null}
    </>
  );
}

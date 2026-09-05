"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  canApproveDocument,
  canCheckDocument,
  formatDocumentDate,
  isChecklistComplete,
  type DocumentDetail,
  type DocumentRecord,
  type DocumentWorkspace,
} from "@/lib/documents";
import type { SessionActor } from "@/lib/governance";

type DocumentCenterProps = {
  actor: SessionActor;
  mode: "documents" | "genesis";
};

type ApiFailure = { detail?: string };

const emptyWorkspace: DocumentWorkspace[] = [];

export function DocumentCenter({ actor, mode }: DocumentCenterProps) {
  const [workspaces, setWorkspaces] = useState<DocumentWorkspace[]>(emptyWorkspace);
  const [workspaceId, setWorkspaceId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [requirement, setRequirement] = useState("");
  const [checkNotes, setCheckNotes] = useState("Evidence dan scope telah diperiksa oleh checker independen.");
  const [reviewNotes, setReviewNotes] = useState("Review independen telah selesai.");
  const [submitting, setSubmitting] = useState(false);

  const visibleDocuments = useMemo(
    () => mode === "genesis" ? documents.filter((document) => document.origin === "GENESIS") : documents,
    [documents, mode],
  );
  const pendingChecks = selected?.checklist.filter((item) => item.required && item.status !== "PASSED").length ?? 0;
  const titleText = mode === "genesis" ? "Draft Dokumen dari GENESIS" : "Document Center";
  const description = mode === "genesis"
    ? "Genesis membuat kerangka DRAFT terhubung ke requirement. Dokumen resmi tetap berada di Document Center."
    : "Satu repositori resmi untuk dokumen manual dan hasil Genesis, lengkap dengan versi, checklist, dan review.";

  const refreshDocuments = useCallback(async (nextWorkspaceId: string) => {
    setError(null);
    try {
      const response = await fetch(`/api/v1/documents?workspace_id=${encodeURIComponent(nextWorkspaceId)}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const items = (await response.json()) as DocumentRecord[];
      setDocuments(items);
      setSelected((current) => (
        current && !items.some((item) => item.document_id === current.document.document_id)
          ? null
          : current
      ));
    } catch (failure) {
      setError(messageFrom(failure));
    }
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const response = await fetch("/api/v1/workspaces", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error(await errorDetail(response));
        const items = (await response.json()) as DocumentWorkspace[];
        setWorkspaces(items);
        const firstWorkspaceId = items[0]?.workspace_id ?? "";
        setWorkspaceId(firstWorkspaceId);
        if (firstWorkspaceId) {
          const documentResponse = await fetch(
            `/api/v1/documents?workspace_id=${encodeURIComponent(firstWorkspaceId)}`,
            { credentials: "same-origin", cache: "no-store" },
          );
          if (!documentResponse.ok) throw new Error(await errorDetail(documentResponse));
          setDocuments((await documentResponse.json()) as DocumentRecord[]);
        }
      } catch (failure) {
        setError(messageFrom(failure));
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, []);

  async function selectDocument(documentId: string) {
    setError(null);
    try {
      const response = await fetch(`/api/v1/documents/${documentId}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error(await errorDetail(response));
      setSelected((await response.json()) as DocumentDetail);
    } catch (failure) {
      setError(messageFrom(failure));
    }
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const payload = mode === "genesis"
      ? { workspace_id: workspaceId, title, requirement, category: "GENERAL", classification: "INTERNAL" }
      : { workspace_id: workspaceId, title, content, category: "GENERAL", classification: "INTERNAL" };
    const endpoint = mode === "genesis" ? "/api/v1/genesis/document-drafts" : "/api/v1/documents/drafts";
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const document = (await response.json()) as DocumentRecord;
      setTitle("");
      setContent("");
      setRequirement("");
      setNotice(mode === "genesis" ? "Genesis membuat kerangka DRAFT. Lengkapi dan kirimkan untuk pemeriksaan." : "Dokumen DRAFT dibuat di repositori resmi.");
      await refreshDocuments(workspaceId);
      await selectDocument(document.document_id);
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setSubmitting(false);
    }
  }

  async function completeCheck(checkKey: string) {
    if (!selected) return;
    await perform(`/api/v1/documents/${selected.document.document_id}/checklist/${checkKey}/complete`, {
      notes: checkNotes,
    }, "Checklist diperbarui oleh checker independen.");
  }

  async function submitForReview() {
    if (!selected) return;
    await perform(`/api/v1/documents/${selected.document.document_id}/submit-review`, undefined, "Dokumen dikirim untuk review.");
  }

  async function decide(approved: boolean) {
    if (!selected) return;
    await perform(
      `/api/v1/documents/${selected.document.document_id}/${approved ? "approve" : "reject"}`,
      { notes: reviewNotes },
      approved ? "Dokumen disetujui. Aktivasi/publikasi tetap tahap terpisah." : "Dokumen dikembalikan sebagai REJECTED.",
    );
  }

  async function perform(endpoint: string, body: object | undefined, success: string) {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const detail = (await response.json()) as DocumentDetail;
      setSelected(detail);
      setNotice(success);
      await refreshDocuments(workspaceId);
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <section className="alos-content"><p>Memuat Document Center…</p></section>;

  return (
    <section className="alos-content alos-document-center" aria-label={titleText}>
      <div className="alos-section-heading">
        <div><p className="alos-kicker">ALOS / {mode === "genesis" ? "GENESIS ARTIFACTS" : "DOCUMENT CENTER"}</p><h2>{titleText}</h2><p>{description}</p></div>
        {mode === "genesis" ? <Link className="alos-outline-link" href="/documents">Buka Document Center →</Link> : <span>Repositori kanonis</span>}
      </div>

      {error ? <p className="alos-inline-error">{error}</p> : null}
      {notice ? <p className="alos-inline-success">{notice}</p> : null}

      <article className="alos-panel alos-document-create-panel">
        <div className="alos-panel-heading-row"><div><p className="alos-kicker">{mode === "genesis" ? "GENESIS WORKSPACE" : "DOKUMEN BARU"}</p><h3>{mode === "genesis" ? "Buat kerangka DRAFT" : "Buat DRAFT resmi"}</h3></div>
          <select aria-label="Workspace dokumen" onChange={(event) => { const nextWorkspaceId = event.target.value; setWorkspaceId(nextWorkspaceId); void refreshDocuments(nextWorkspaceId); }} value={workspaceId}>
            {workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}
          </select>
        </div>
        {!workspaceId ? <p className="alos-empty-copy">Akun ini belum memiliki workspace aktif untuk membuat dokumen.</p> : <form className="alos-document-form" onSubmit={createDraft}>
          <label>Judul dokumen<input maxLength={200} minLength={3} onChange={(event) => setTitle(event.target.value)} placeholder="Contoh: SOP Brief Operasional" required value={title} /></label>
          {mode === "genesis" ? <label className="alos-document-full">Kebutuhan untuk Genesis<textarea maxLength={10000} minLength={20} onChange={(event) => setRequirement(event.target.value)} placeholder="Jelaskan kebutuhan, tujuan, dan kekurangan yang ingin dilengkapi…" required value={requirement} /></label> : <label className="alos-document-full">Isi draft<textarea maxLength={50000} minLength={1} onChange={(event) => setContent(event.target.value)} placeholder="Masukkan isi awal dokumen…" required value={content} /></label>}
          <p className="alos-document-full alos-document-note">{mode === "genesis" ? "Genesis menyimpan kerangka dengan requirement yang diaudit. Evidence, owner, dan risiko tetap harus diperiksa manusia." : "Dokumen dibuat sebagai DRAFT dan tidak dapat langsung dipublikasikan."}</p>
          <button disabled={submitting} type="submit">{submitting ? "Memproses…" : mode === "genesis" ? "Buat DRAFT dari Genesis" : "Buat DRAFT dokumen"}</button>
        </form>}
      </article>

      <div className="alos-document-layout">
        <article className="alos-panel alos-document-list-panel">
          <div className="alos-panel-heading-row"><div><p className="alos-kicker">{mode === "genesis" ? "ARTIFAK GENESIS" : "DOKUMEN TERDAFTAR"}</p><h3>{visibleDocuments.length} Dokumen</h3></div><button className="alos-text-button" onClick={() => void refreshDocuments(workspaceId)} type="button">Muat ulang</button></div>
          {visibleDocuments.length === 0 ? <p className="alos-empty-copy">{mode === "genesis" ? "Belum ada draft dari Genesis pada workspace ini." : "Belum ada dokumen terdaftar pada workspace ini."}</p> : <ul className="alos-document-list">{visibleDocuments.map((document) => <li key={document.document_id}><button className={selected?.document.document_id === document.document_id ? "selected" : ""} onClick={() => void selectDocument(document.document_id)} type="button"><span><strong>{document.title}</strong><small>v{document.version_number} · {document.origin === "GENESIS" ? "Genesis" : "Manual"}</small></span><em className={`alos-document-status ${document.status.toLowerCase()}`}>{document.status.replace("_", " ")}</em></button></li>)}</ul>}
        </article>

        <DocumentDetailPanel actor={actor} detail={selected} pendingChecks={pendingChecks} checkNotes={checkNotes} reviewNotes={reviewNotes} submitting={submitting} onCheckNotes={setCheckNotes} onReviewNotes={setReviewNotes} onCompleteCheck={completeCheck} onSubmit={submitForReview} onDecide={decide} />
      </div>
    </section>
  );
}

type DocumentDetailPanelProps = {
  actor: SessionActor;
  detail: DocumentDetail | null;
  pendingChecks: number;
  checkNotes: string;
  reviewNotes: string;
  submitting: boolean;
  onCheckNotes: (value: string) => void;
  onReviewNotes: (value: string) => void;
  onCompleteCheck: (key: string) => void;
  onSubmit: () => void;
  onDecide: (approved: boolean) => void;
};

function DocumentDetailPanel({ actor, detail, pendingChecks, checkNotes, reviewNotes, submitting, onCheckNotes, onReviewNotes, onCompleteCheck, onSubmit, onDecide }: DocumentDetailPanelProps) {
  if (!detail) return <article className="alos-panel alos-document-detail-panel"><p className="alos-empty-copy">Pilih dokumen untuk melihat versi, isi draft, checklist, dan status review.</p></article>;
  const isMaker = detail.document.created_by_user_id === actor.user_id;
  const canCheck = canCheckDocument(actor, detail);
  const canApprove = canApproveDocument(actor, detail);
  const canSubmit = detail.document.status === "DRAFT" && isMaker && isChecklistComplete(detail);
  return <article className="alos-panel alos-document-detail-panel">
    <div className="alos-panel-heading-row"><div><p className="alos-kicker">{detail.document.origin === "GENESIS" ? "DRAFT DARI GENESIS" : "DOKUMEN KANONIS"}</p><h3>{detail.document.title}</h3><p className="alos-document-meta">v{detail.document.version_number} · {detail.document.category} · {detail.document.classification} · dibuat {formatDocumentDate(detail.document.created_at)}</p></div><em className={`alos-document-status ${detail.document.status.toLowerCase()}`}>{detail.document.status.replace("_", " ")}</em></div>
    <pre className="alos-document-content">{detail.content}</pre>
    <div className="alos-document-checklist-heading"><div><p className="alos-kicker">CHECKLIST WAJIB</p><h4>{pendingChecks === 0 ? "Checklist lengkap" : `${pendingChecks} item masih memblokir review`}</h4></div><span>{detail.checklist.filter((item) => item.status === "PASSED").length}/{detail.checklist.length} selesai</span></div>
    {canCheck ? <label className="alos-document-note-input">Catatan checker<input minLength={3} onChange={(event) => onCheckNotes(event.target.value)} value={checkNotes} /></label> : null}
    <ul className="alos-document-checklist">{detail.checklist.map((item) => <li key={item.document_checklist_item_id}><span className={item.status === "PASSED" ? "passed" : "pending"}>{item.status === "PASSED" ? "✓" : "○"}</span><div><strong>{item.label}</strong><small>{item.check_type === "AUTOMATED" ? "Pemeriksaan otomatis" : item.notes ?? "Memerlukan checker independen"}</small></div>{canCheck && item.check_type === "HUMAN" && item.status !== "PASSED" ? <button disabled={submitting || checkNotes.trim().length < 3} onClick={() => onCompleteCheck(item.check_key)} type="button">Tandai selesai</button> : null}</li>)}</ul>
    {canSubmit ? <button className="alos-document-primary" disabled={submitting} onClick={onSubmit} type="button">Kirim untuk review</button> : null}
    {detail.document.status === "DRAFT" && isMaker && !canSubmit ? <p className="alos-document-note">Dokumen dapat dikirim oleh pembuatnya setelah seluruh checklist wajib diselesaikan checker independen.</p> : null}
    {canApprove ? <div className="alos-document-decision"><label>Catatan approver<input minLength={3} onChange={(event) => onReviewNotes(event.target.value)} value={reviewNotes} /></label><div><button className="alos-document-primary" disabled={submitting || reviewNotes.trim().length < 3} onClick={() => onDecide(true)} type="button">Setujui dokumen</button><button className="alos-document-reject" disabled={submitting || reviewNotes.trim().length < 3} onClick={() => onDecide(false)} type="button">Tolak dokumen</button></div></div> : null}
    {detail.reviews.length > 0 ? <div className="alos-document-review-history"><p className="alos-kicker">RIWAYAT REVIEW</p>{detail.reviews.map((review) => <p key={review.document_review_request_id}><strong>{review.status}</strong> · {formatDocumentDate(review.submitted_at)}{review.notes ? ` — ${review.notes}` : ""}</p>)}</div> : null}
  </article>;
}

async function errorDetail(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as ApiFailure | null;
  return payload?.detail ?? "Permintaan tidak dapat diproses.";
}

function messageFrom(failure: unknown): string {
  return failure instanceof Error ? failure.message : "Terjadi kesalahan yang tidak diketahui.";
}

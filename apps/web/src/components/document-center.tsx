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
  const [composerOpen, setComposerOpen] = useState(false);
  const [documentQuery, setDocumentQuery] = useState("");

  const visibleDocuments = useMemo(
    () => mode === "genesis" ? documents.filter((document) => document.origin === "GENESIS") : documents,
    [documents, mode],
  );
  const filteredDocuments = useMemo(() => {
    const query = documentQuery.trim().toLocaleLowerCase("id-ID");
    if (!query) return visibleDocuments;
    return visibleDocuments.filter((document) => (
      document.title.toLocaleLowerCase("id-ID").includes(query)
      || document.category.toLocaleLowerCase("id-ID").includes(query)
      || document.origin.toLocaleLowerCase("id-ID").includes(query)
    ));
  }, [documentQuery, visibleDocuments]);
  const documentStats = useMemo(() => ({
    approved: documents.filter((document) => document.status === "APPROVED" || document.status === "ACTIVE").length,
    genesis: documents.filter((document) => document.origin === "GENESIS").length,
    review: documents.filter((document) => document.status === "IN_REVIEW").length,
    total: documents.length,
  }), [documents]);
  const pendingChecks = selected?.checklist.filter((item) => item.required && item.status !== "PASSED").length ?? 0;

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
    const generatedTitle = `Draft Genesis — ${requirement.trim().replace(/\s+/g, " ").slice(0, 80)}`;
    const payload = mode === "genesis"
      ? { workspace_id: workspaceId, title: title.trim() || generatedTitle, requirement, category: "GENERAL", classification: "INTERNAL" }
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
      setComposerOpen(false);
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

  if (mode === "documents") {
    return (
      <section className="alos-content alos-document-library" aria-label="Document Center">
        <header className="alos-workspace-heading">
          <div><p className="alos-kicker">ALOS / DOCUMENT CENTER</p><h2>Documents</h2><p>Kelola, temukan, dan tindak lanjuti dokumen perusahaan dari satu repositori resmi.</p></div>
          <div className="alos-workspace-actions"><select aria-label="Workspace dokumen" onChange={(event) => { const nextWorkspaceId = event.target.value; setWorkspaceId(nextWorkspaceId); void refreshDocuments(nextWorkspaceId); }} value={workspaceId}>{workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}</select><button className="alos-workspace-primary" onClick={() => setComposerOpen((open) => !open)} type="button">{composerOpen ? "Tutup form" : "+ Buat dokumen"}</button></div>
        </header>

        {error ? <p className="alos-inline-error">{error}</p> : null}
        {notice ? <p className="alos-inline-success">{notice}</p> : null}

        {composerOpen ? <article className="alos-panel alos-document-compose-panel"><div className="alos-panel-heading-row"><div><p className="alos-kicker">DOKUMEN BARU</p><h3>Buat DRAFT resmi</h3></div><span>Belum dipublikasikan</span></div>{!workspaceId ? <p className="alos-empty-copy">Akun ini belum memiliki workspace aktif untuk membuat dokumen.</p> : <form className="alos-document-form" onSubmit={createDraft}><label>Judul dokumen<input maxLength={200} minLength={3} onChange={(event) => setTitle(event.target.value)} placeholder="Contoh: SOP Brief Operasional" required value={title} /></label><label className="alos-document-full">Isi draft<textarea maxLength={50000} minLength={1} onChange={(event) => setContent(event.target.value)} placeholder="Masukkan isi awal dokumen…" required value={content} /></label><p className="alos-document-full alos-document-note">DRAFT disimpan pada repositori resmi dan tetap memerlukan checklist serta review independen.</p><button disabled={submitting} type="submit">{submitting ? "Menyimpan…" : "Simpan DRAFT"}</button></form>}</article> : null}

        <div className="alos-document-metrics" aria-label="Ringkasan dokumen">
          <DocumentMetric label="Total dokumen" value={documentStats.total} tone="success" />
          <DocumentMetric label="Butuh review" value={documentStats.review} tone="warning" />
          <DocumentMetric label="Draft dari Genesis" value={documentStats.genesis} tone="info" />
          <DocumentMetric label="Disetujui" value={documentStats.approved} tone="danger" />
        </div>

        <div className="alos-document-overview">
          <article className="alos-panel alos-document-distribution"><div className="alos-panel-heading-row"><div><p className="alos-kicker">DISTRIBUSI</p><h3>Kategori dokumen</h3></div><button className="alos-text-button" onClick={() => void refreshDocuments(workspaceId)} type="button">Muat ulang</button></div><DocumentDistribution documents={documents} /></article>
          <article className="alos-panel alos-document-summary"><p className="alos-kicker">RINGKASAN DOKUMEN</p><h3>Repositori kanonis</h3><dl><div><dt>Workspace aktif</dt><dd>{workspaces.find((workspace) => workspace.workspace_id === workspaceId)?.name ?? "—"}</dd></div><div><dt>Dokumen manual</dt><dd>{documents.filter((document) => document.origin === "MANUAL").length || "—"}</dd></div><div><dt>Versi aktif</dt><dd>{documentStats.approved || "—"}</dd></div><div><dt>Status sumber</dt><dd>Governed</dd></div></dl></article>
          <article className="alos-panel alos-document-important"><div className="alos-panel-heading-row"><div><p className="alos-kicker">DOKUMEN PENTING</p><h3>Terakhir diperbarui</h3></div></div><DocumentHighlights documents={documents} onSelect={selectDocument} /></article>
        </div>

        <article className="alos-panel alos-document-table-panel"><div className="alos-panel-heading-row"><div><p className="alos-kicker">DAFTAR DOKUMEN</p><h3>Repositori dokumen</h3></div><label className="alos-document-search"><span>⌕</span><input aria-label="Cari dokumen" onChange={(event) => setDocumentQuery(event.target.value)} placeholder="Cari dokumen…" value={documentQuery} /></label></div><DocumentTable documents={filteredDocuments} onSelect={selectDocument} selectedId={selected?.document.document_id ?? null} /></article>

        {selected ? <section className="alos-document-detail-drawer" aria-label={`Rincian ${selected.document.title}`}><DocumentDetailPanel actor={actor} detail={selected} pendingChecks={pendingChecks} checkNotes={checkNotes} reviewNotes={reviewNotes} submitting={submitting} onCheckNotes={setCheckNotes} onReviewNotes={setReviewNotes} onCompleteCheck={completeCheck} onSubmit={submitForReview} onDecide={decide} /></section> : null}
      </section>
    );
  }

  return (
    <section className="alos-content alos-genesis-workspace" aria-label="GENESIS">
      <header className="alos-genesis-workspace-heading"><span className="alos-genesis-workspace-star">✦</span><div><p className="alos-kicker">ALOS / AI EXECUTIVE</p><h2>GENESIS</h2><p>Your AI Executive Assistant</p></div><Link className="alos-outline-link" href="/documents">Buka Document Center →</Link></header>
      {error ? <p className="alos-inline-error">{error}</p> : null}
      {notice ? <p className="alos-inline-success">{notice}</p> : null}

      <div className="alos-genesis-workspace-grid">
        <article className="alos-panel alos-genesis-conversation">
          <div className="alos-genesis-intro"><span>✦</span><div><strong>Mulai dari kebutuhan bisnis Anda</strong><p>Genesis akan menyusun kerangka DRAFT yang dapat ditelusuri. Pemeriksaan evidence, checker, dan approval tetap dilakukan manusia.</p></div></div>
          {!workspaceId ? <p className="alos-empty-copy">Akun ini belum memiliki workspace aktif untuk membuat DRAFT.</p> : <form className="alos-genesis-draft-form" onSubmit={createDraft}><label><span>Tujuan atau kebutuhan</span><textarea aria-label="Tujuan atau kebutuhan untuk Genesis" maxLength={10000} minLength={20} onChange={(event) => setRequirement(event.target.value)} placeholder="Contoh: Buat kerangka SOP untuk menutup kekurangan bukti operasional…" required value={requirement} /></label><div><small>Hasil awal selalu DRAFT. Tidak ada publikasi, aktivasi, atau perubahan sumber otomatis.</small><button disabled={submitting} type="submit">{submitting ? "Menyusun…" : "Buat DRAFT"} <span>→</span></button></div></form>}
          <p className="alos-genesis-disclaimer">GENESIS dapat membuat kesalahan. Verifikasi informasi penting sebelum membuat keputusan.</p>
        </article>

        <aside className="alos-genesis-workspace-side">
          <article className="alos-panel"><div className="alos-panel-heading-row"><div><p className="alos-kicker">PERCAKAPAN TERBARU</p><h3>Ruang kerja</h3></div></div><p className="alos-empty-copy">Percakapan akan muncul saat histori GENESIS disimpan sebagai capability terpisah.</p></article>
          <article className="alos-panel alos-genesis-module-links"><div className="alos-panel-heading-row"><div><p className="alos-kicker">OPERASI TERKENDALI</p><h3>Modul terkait</h3></div></div><Link href="/agents"><span>Agent Registry</span><small>Kontrak dan hierarki</small><b>›</b></Link><Link href="/releases"><span>Release Governance</span><small>UAT dan approval rilis</small><b>›</b></Link><Link href="/h5"><span>Evidence &amp; Sources</span><small>Sumber terverifikasi</small><b>›</b></Link></article>
          <article className="alos-panel alos-genesis-quick-prompts"><p className="alos-kicker">QUICK PROMPTS</p><h3>Mulai dengan cepat</h3>{["Ringkas kekurangan evidence dari dokumen operasional", "Susun draft SOP untuk proses yang belum terdokumentasi", "Daftarkan kebutuhan data untuk target divisi", "Buat brief untuk agent read-only"].map((prompt) => <button key={prompt} onClick={() => setRequirement(prompt)} type="button"><span>{prompt}</span><b>›</b></button>)}</article>
        </aside>
      </div>

      <section className="alos-genesis-artifacts"><div className="alos-section-heading"><div><p className="alos-kicker">DRAFT &amp; EVIDENCE</p><h2>Artefak GENESIS</h2></div><span>{visibleDocuments.length ? `${visibleDocuments.length} DRAFT tercatat` : "Belum ada DRAFT"}</span></div>{visibleDocuments.length === 0 ? <article className="alos-panel"><div className="alos-empty-message"><span>○</span><p>Belum ada DRAFT dari GENESIS pada workspace ini. Kirimkan kebutuhan di atas untuk membuat kerangka pertama.</p></div></article> : <article className="alos-panel"><DocumentTable documents={visibleDocuments} onSelect={selectDocument} selectedId={selected?.document.document_id ?? null} /></article>}{selected ? <div className="alos-document-detail-drawer"><DocumentDetailPanel actor={actor} detail={selected} pendingChecks={pendingChecks} checkNotes={checkNotes} reviewNotes={reviewNotes} submitting={submitting} onCheckNotes={setCheckNotes} onReviewNotes={setReviewNotes} onCompleteCheck={completeCheck} onSubmit={submitForReview} onDecide={decide} /></div> : null}</section>
    </section>
  );
}

function DocumentMetric({ label, tone, value }: { label: string; tone: "success" | "warning" | "info" | "danger"; value: number }) {
  return <article className={`alos-document-metric ${tone}`}><span aria-hidden="true">{tone === "success" ? "▣" : tone === "warning" ? "!" : tone === "info" ? "◫" : "✓"}</span><div><strong>{value || "—"}</strong><p>{label}</p><small>{value ? "Data dari repositori aktif" : "Belum ada data"}</small></div></article>;
}

function DocumentDistribution({ documents }: { documents: DocumentRecord[] }) {
  const categories = Array.from(new Set(documents.map((document) => document.category))).slice(0, 4);
  return <div className="alos-document-distribution-body"><div className="alos-document-donut"><strong>{documents.length || "—"}</strong><span>Dokumen</span></div><div>{categories.length === 0 ? <p>Belum ada kategori terdaftar.</p> : categories.map((category) => <p key={category}><i />{category}<strong>{documents.filter((document) => document.category === category).length}</strong></p>)}</div></div>;
}

function DocumentHighlights({ documents, onSelect }: { documents: DocumentRecord[]; onSelect: (documentId: string) => void }) {
  if (documents.length === 0) return <p className="alos-empty-copy">Belum ada dokumen yang dapat ditampilkan.</p>;
  return <ul className="alos-document-highlights">{documents.slice(0, 5).map((document) => <li key={document.document_id}><button onClick={() => void onSelect(document.document_id)} type="button"><span><strong>{document.title}</strong><small>{document.category} · v{document.version_number}</small></span><em className={`alos-document-status ${document.status.toLowerCase()}`}>{document.status.replace("_", " ")}</em></button></li>)}</ul>;
}

function DocumentTable({ documents, onSelect, selectedId }: { documents: DocumentRecord[]; onSelect: (documentId: string) => void; selectedId: string | null }) {
  if (documents.length === 0) return <div className="alos-empty-message compact"><span>○</span><p>Belum ada dokumen yang sesuai pada workspace ini.</p></div>;
  return <div className="alos-document-table-wrap"><table><thead><tr><th>Nama dokumen</th><th>Sumber</th><th>Versi</th><th>Terakhir diperbarui</th><th>Status</th></tr></thead><tbody>{documents.map((document) => <tr className={selectedId === document.document_id ? "selected" : ""} key={document.document_id}><td><button onClick={() => void onSelect(document.document_id)} type="button">{document.title}</button><small>{document.category} · {document.classification}</small></td><td>{document.origin === "GENESIS" ? "GENESIS" : "Manual"}</td><td>v{document.version_number}</td><td>{formatDocumentDate(document.updated_at)}</td><td><em className={`alos-document-status ${document.status.toLowerCase()}`}>{document.status.replace("_", " ")}</em></td></tr>)}</tbody></table></div>;
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

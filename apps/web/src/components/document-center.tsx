"use client";

import Link from "next/link";
import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  canApproveDocument,
  canCheckDocument,
  formatDocumentDate,
  isChecklistComplete,
  type DocumentDetail,
  type DocumentRecord,
  type DocumentWorkspace,
} from "@/lib/documents";
import {
  formatUploadSize,
  supportsGenesisUpload,
  uploadExtractionLabel,
  type GenesisUploadRecord,
} from "@/lib/genesis-uploads";
import type { SessionActor } from "@/lib/governance";

type DocumentCenterProps = {
  actor: SessionActor;
  mode: "documents" | "genesis";
};

type ApiFailure = { detail?: string };

type GenesisMessage = {
  message_id: string;
  conversation_id: string;
  actor_kind: "HUMAN" | "SYSTEM";
  content: string;
  created_at: string;
};

type GenesisStats = {
  approved: number;
  genesis: number;
  review: number;
  total: number;
};

const genesisStarterActions = [
  {
    description: "Pahami isi dokumen dan soroti bagian yang perlu diperiksa.",
    icon: "▤",
    prompt: "Analisis dokumen ini dan jelaskan bagian yang perlu diperiksa lebih lanjut.",
    title: "Analisis Dokumen",
  },
  {
    description: "Ubah laporan panjang menjadi poin eksekutif yang ringkas.",
    icon: "▥",
    prompt: "Ringkas laporan ini menjadi insight eksekutif, risiko, dan langkah berikutnya.",
    title: "Ringkas Laporan",
  },
  {
    description: "Susun kerangka awal yang tetap membutuhkan review manusia.",
    icon: "✎",
    prompt: "Susun kerangka DRAFT SOP untuk proses yang belum terdokumentasi.",
    title: "Susun DRAFT SOP",
  },
  {
    description: "Petakan pertanyaan riset dan evidence yang diperlukan.",
    icon: "◉",
    prompt: "Susun kebutuhan riset strategis, evidence, dan pertanyaan pemeriksaan awal.",
    title: "Riset Strategis",
  },
] as const;

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
  const [uploads, setUploads] = useState<GenesisUploadRecord[]>([]);
  const [uploading, setUploading] = useState(false);
  const [promotingUpload, setPromotingUpload] = useState(false);
  const [withdrawingUpload, setWithdrawingUpload] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [documentQuery, setDocumentQuery] = useState("");
  const [activeGenesisConversationId, setActiveGenesisConversationId] = useState<string | null>(null);
  const [genesisMessages, setGenesisMessages] = useState<GenesisMessage[]>([]);
  const [genesisConversationLoading, setGenesisConversationLoading] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);

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
  const latestUpload = uploads[0] ?? null;
  const canUploadToGenesis = actor.roles.includes("DIRECTOR");
  const genesisDrafts = useMemo(() => documents
    .filter((document) => document.origin === "GENESIS")
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)), [documents]);
  const recentGenesisConversations = useMemo(
    () => genesisDrafts.filter((document) => document.genesis_conversation_id !== null).slice(0, 5),
    [genesisDrafts],
  );
  const activeGenesisDraft = useMemo(
    () => genesisDrafts.find((document) => document.genesis_conversation_id === activeGenesisConversationId) ?? null,
    [activeGenesisConversationId, genesisDrafts],
  );

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

  const refreshGenesisUploads = useCallback(async (nextWorkspaceId: string) => {
    if (!nextWorkspaceId) {
      setUploads([]);
      return;
    }
    try {
      const response = await fetch(`/api/v1/genesis/uploads?workspace_id=${encodeURIComponent(nextWorkspaceId)}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      setUploads((await response.json()) as GenesisUploadRecord[]);
    } catch (failure) {
      setError(messageFrom(failure));
    }
  }, []);

  const loadGenesisMessages = useCallback(async (conversationId: string) => {
    setGenesisConversationLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/genesis/conversations/${encodeURIComponent(conversationId)}/messages`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      setGenesisMessages((await response.json()) as GenesisMessage[]);
    } catch (failure) {
      setGenesisMessages([]);
      setError(messageFrom(failure));
    } finally {
      setGenesisConversationLoading(false);
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
          if (mode === "genesis" && canUploadToGenesis) {
            const uploadResponse = await fetch(
              `/api/v1/genesis/uploads?workspace_id=${encodeURIComponent(firstWorkspaceId)}`,
              { credentials: "same-origin", cache: "no-store" },
            );
            if (!uploadResponse.ok) throw new Error(await errorDetail(uploadResponse));
            setUploads((await uploadResponse.json()) as GenesisUploadRecord[]);
          }
        }
      } catch (failure) {
        setError(messageFrom(failure));
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [canUploadToGenesis, mode]);

  function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setActiveGenesisConversationId(null);
    setGenesisMessages([]);
    void refreshDocuments(nextWorkspaceId);
    if (mode === "genesis" && canUploadToGenesis) {
      void refreshGenesisUploads(nextWorkspaceId);
      return;
    }
    setUploads([]);
  }

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
    const submittedRequirement = requirement.trim();
    if (mode === "genesis" && !submittedRequirement) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const generatedTitle = `Draft Genesis — ${submittedRequirement.replace(/\s+/g, " ").slice(0, 80)}`;
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
      if (mode === "genesis" && document.genesis_conversation_id) {
        setActiveGenesisConversationId(document.genesis_conversation_id);
        await loadGenesisMessages(document.genesis_conversation_id);
      } else {
        await selectDocument(document.document_id);
      }
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setSubmitting(false);
    }
  }

  async function addGenesisMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeGenesisConversationId) {
      await createDraft(event);
      return;
    }
    const message = requirement.trim();
    if (!message) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/v1/genesis/conversations/${encodeURIComponent(activeGenesisConversationId)}/messages`,
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: message }),
        },
      );
      if (!response.ok) throw new Error(await errorDetail(response));
      const createdMessage = (await response.json()) as GenesisMessage;
      setGenesisMessages((current) => [...current, createdMessage]);
      setRequirement("");
      setNotice("Pesan lanjutan tercatat pada percakapan ini. DRAFT dan keputusan tetap memerlukan proses review.");
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setSubmitting(false);
    }
  }

  function openGenesisConversation(document: DocumentRecord) {
    if (!document.genesis_conversation_id) return;
    setActiveGenesisConversationId(document.genesis_conversation_id);
    setRequirement("");
    void loadGenesisMessages(document.genesis_conversation_id);
  }

  function startGenesisConversation(prompt = "") {
    setActiveGenesisConversationId(null);
    setGenesisMessages([]);
    setRequirement(prompt);
  }

  function openUploadPicker() {
    uploadInputRef.current?.click();
  }

  async function uploadGenesisFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !workspaceId) return;
    if (!supportsGenesisUpload(file.name)) {
      setError("Format belum didukung. Gunakan PDF, DOCX, XLS/XLSX, CSV, JSON, MD, atau TXT.");
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);
    const payload = new FormData();
    payload.set("workspace_id", workspaceId);
    payload.set("file", file);
    try {
      const response = await fetch("/api/v1/genesis/uploads", {
        method: "POST",
        credentials: "same-origin",
        body: payload,
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const uploaded = (await response.json()) as GenesisUploadRecord;
      setUploads((current) => [uploaded, ...current.filter((item) => item.genesis_upload_id !== uploaded.genesis_upload_id)]);
      setNotice(
        uploaded.extraction_complete
          ? "Dokumen diterima. Periksa preview sebelum menjadikannya DRAFT resmi."
          : "Dokumen diterima, tetapi teksnya belum lengkap. Tinjau status ekstraksi sebelum melanjutkan.",
      );
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setUploading(false);
    }
  }

  async function createDraftFromUpload(upload: GenesisUploadRecord) {
    if (!workspaceId) return;
    setPromotingUpload(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/v1/genesis/uploads/${upload.genesis_upload_id}/document-draft`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const document = (await response.json()) as DocumentRecord;
      setNotice("DRAFT resmi dibuat. Selanjutnya, checker independen melengkapi checklist sebelum review.");
      await refreshDocuments(workspaceId);
      await refreshGenesisUploads(workspaceId);
      await selectDocument(document.document_id);
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setPromotingUpload(false);
    }
  }

  async function withdrawGenesisUpload(upload: GenesisUploadRecord) {
    if (!window.confirm(`Batalkan unggahan “${upload.original_filename}”? Berkas asli dan preview teks akan dihapus.`)) {
      return;
    }
    setWithdrawingUpload(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/v1/genesis/uploads/${upload.genesis_upload_id}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      setUploads((current) => current.filter((item) => item.genesis_upload_id !== upload.genesis_upload_id));
      setNotice("Unggahan dibatalkan. Berkas asli dan preview teks telah dihapus.");
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setWithdrawingUpload(false);
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
          <div className="alos-workspace-actions"><select aria-label="Workspace dokumen" onChange={(event) => selectWorkspace(event.target.value)} value={workspaceId}>{workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}</select><button className="alos-workspace-primary" onClick={() => setComposerOpen((open) => !open)} type="button">{composerOpen ? "Tutup form" : "+ Buat dokumen"}</button></div>
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
    <section className={`alos-content alos-genesis-workspace${activeGenesisConversationId ? " has-conversation" : ""}`} aria-label="GENESIS">
      <header className="alos-genesis-workspace-heading"><span className="alos-genesis-workspace-star">✦</span><div><h2>GENESIS</h2><p>AI Executive Assistant</p></div>{activeGenesisConversationId ? <button className="alos-genesis-new-conversation" onClick={() => startGenesisConversation()} type="button">＋ Percakapan baru</button> : <button className="alos-genesis-mode" disabled type="button">♢ Enterprise Mode <span>⌄</span></button>}</header>
      <input accept=".pdf,.docx,.xlsx,.xls,.csv,.json,.md,.txt" className="sr-only" onChange={uploadGenesisFile} ref={uploadInputRef} tabIndex={-1} type="file" />
      {error ? <p className="alos-inline-error">{error}</p> : null}
      {notice ? <p className="alos-inline-success">{notice}</p> : null}

      <div className="alos-genesis-workspace-grid">
        <article className="alos-panel alos-genesis-conversation">
          {activeGenesisConversationId ? <>
            <div className="alos-genesis-thread-toolbar"><span className="alos-genesis-source-chip">▤ <b>Sumber: Internal ALOS</b>⌄</span><button aria-label="Opsi percakapan" type="button">•••</button></div>
            <div className="alos-genesis-chat-stream" aria-live="polite">
              {genesisConversationLoading ? <p className="alos-genesis-thread-loading">Memuat percakapan…</p> : null}
              {!genesisConversationLoading && genesisMessages.length === 0 ? <p className="alos-genesis-thread-loading">Riwayat pesan belum tersedia untuk percakapan ini.</p> : null}
              {genesisMessages.map((message, index) => <div key={message.message_id}><div className={message.actor_kind === "HUMAN" ? "alos-genesis-user-message" : "alos-genesis-assistant-message"}>{message.actor_kind === "HUMAN" ? <><div><p>{message.content}</p><time>{formatGenesisTime(message.created_at)}</time></div><span>{actor.roles[0]?.slice(0, 1) ?? "A"}</span></> : <><span>✦</span><div><p>{message.content}</p><time>{formatGenesisTime(message.created_at)}</time></div></>}</div>{index === 0 && activeGenesisDraft ? <GenesisDraftMessage document={activeGenesisDraft} /> : null}</div>)}
              {genesisMessages.length === 0 && activeGenesisDraft ? <GenesisDraftMessage document={activeGenesisDraft} /> : null}
            </div>
            {!workspaceId ? <p className="alos-empty-copy">Akun ini belum memiliki workspace aktif untuk membuat DRAFT.</p> : <GenesisComposer canUpload={Boolean(workspaceId && canUploadToGenesis && !uploading)} onOpenUpload={openUploadPicker} onRequirementChange={setRequirement} onSubmit={addGenesisMessage} requirement={requirement} submitting={submitting} threadOpen />}
            <GenesisUploadPreview onPromote={() => { if (latestUpload) void createDraftFromUpload(latestUpload); }} onWithdraw={() => { if (latestUpload) void withdrawGenesisUpload(latestUpload); }} promoting={promotingUpload} upload={latestUpload} withdrawing={withdrawingUpload} />
          </> : <>
            <div className="alos-genesis-landing-hero"><div><p className="alos-kicker">AI UNTUK KEPUTUSAN YANG LEBIH BAIK</p><h3>Mulai percakapan dengan GENESIS</h3><p>Ajukan pertanyaan, minta analisis, atau dapatkan kerangka DRAFT berdasarkan sumber yang tersedia di ALOS.</p></div><div className="alos-genesis-landing-scope"><span>Data</span><span>Insight</span><span>Rekomendasi</span><span>Aksi terkontrol</span><blockquote>“Dari data menuju keputusan yang lebih baik.”</blockquote></div></div>
            <div className="alos-genesis-starter-grid">{genesisStarterActions.map((action) => <button key={action.title} onClick={() => startGenesisConversation(action.prompt)} type="button"><span>{action.icon}</span><div><strong>{action.title}</strong><small>{action.description}</small></div><b>›</b></button>)}</div>
            {!workspaceId ? <p className="alos-empty-copy">Akun ini belum memiliki workspace aktif untuk membuat DRAFT.</p> : <GenesisComposer canUpload={Boolean(workspaceId && canUploadToGenesis && !uploading)} onOpenUpload={openUploadPicker} onRequirementChange={setRequirement} onSubmit={addGenesisMessage} requirement={requirement} submitting={submitting} threadOpen={false} />}
            <GenesisUploadPreview onPromote={() => { if (latestUpload) void createDraftFromUpload(latestUpload); }} onWithdraw={() => { if (latestUpload) void withdrawGenesisUpload(latestUpload); }} promoting={promotingUpload} upload={latestUpload} withdrawing={withdrawingUpload} />
          </>}
          <p className="alos-genesis-disclaimer">GENESIS dapat membuat kesalahan. Verifikasi informasi penting sebelum membuat keputusan.</p>
        </article>

        <GenesisWorkspaceSidebar activeConversationId={activeGenesisConversationId} documentStats={documentStats} onOpenConversation={openGenesisConversation} recentConversations={recentGenesisConversations} />
      </div>

      <section className="alos-genesis-context"><div className="alos-panel-heading-row"><div><p className="alos-kicker">SUMBER PENGETAHUAN</p><h3>Context</h3></div><Link href="/h5">Kelola Sumber →</Link></div><div className="alos-genesis-context-sources"><Link href="/documents"><span className="internal">●</span><div><strong>Internal ALOS</strong><small>Dokumen, DRAFT, dan evidence terdaftar</small></div><em>{documentStats.total ? `${documentStats.total} dokumen` : "Belum terhubung"}</em></Link><span className="alos-genesis-context-plus">+</span><button className="alos-genesis-upload-source" disabled={!workspaceId || !canUploadToGenesis || uploading} onClick={openUploadPicker} type="button"><span className="external">⇧</span><div><strong>Unggah sumber</strong><small>{uploads.length ? `${uploads.length} sumber menunggu tinjauan` : "Tambahkan dokumen untuk diperiksa"}</small></div><em>›</em></button></div></section>

      {selected ? <section className="alos-document-detail-drawer" aria-label={`Rincian ${selected.document.title}`}><DocumentDetailPanel actor={actor} detail={selected} pendingChecks={pendingChecks} checkNotes={checkNotes} reviewNotes={reviewNotes} submitting={submitting} onCheckNotes={setCheckNotes} onReviewNotes={setReviewNotes} onCompleteCheck={completeCheck} onSubmit={submitForReview} onDecide={decide} /></section> : null}
    </section>
  );
}

function GenesisDraftMessage({ document }: { document: DocumentRecord }) {
  return <div className="alos-genesis-assistant-message alos-genesis-draft-response"><span>✦</span><div><p><strong>Kerangka DRAFT telah disiapkan.</strong> Permintaan Anda tercatat sebagai DRAFT yang harus diperiksa manusia sebelum dapat digunakan lebih lanjut.</p><article className="alos-genesis-draft-card"><p className="alos-kicker">DRAFT UNTUK PEMERIKSAAN</p><h3>{document.title.replace(/^Draft Genesis —\s*/i, "")}</h3><small>{document.status.replace("_", " ")} · diperbarui {formatGenesisTime(document.updated_at)}</small><Link href="/documents">Buka DRAFT di Document Center →</Link></article></div></div>;
}

function GenesisComposer({
  canUpload,
  onOpenUpload,
  onRequirementChange,
  onSubmit,
  requirement,
  submitting,
  threadOpen,
}: {
  canUpload: boolean;
  onOpenUpload: () => void;
  onRequirementChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  requirement: string;
  submitting: boolean;
  threadOpen: boolean;
}) {
  return <form className="alos-genesis-draft-form" onSubmit={onSubmit}>
    <label><span className="sr-only">Pesan untuk Genesis</span><textarea aria-label="Pesan untuk Genesis" maxLength={10000} minLength={threadOpen ? 1 : 20} onChange={(event) => onRequirementChange(event.target.value)} placeholder="Ketik pertanyaan atau kebutuhan Anda untuk GENESIS…" required value={requirement} /></label>
    <div><button aria-label="Unggah dokumen" className="alos-genesis-composer-upload" disabled={!canUpload} onClick={onOpenUpload} type="button">⌇</button><span className="alos-genesis-source-chip">▤ <b>Sumber: Internal ALOS</b>⌄</span><small>{threadOpen ? "Pesan dicatat pada riwayat percakapan." : "Hasil awal selalu DRAFT dan membutuhkan pemeriksaan manusia."}</small><button aria-label={threadOpen ? "Kirim pesan" : "Buat DRAFT dari kebutuhan"} disabled={submitting} type="submit">{submitting ? "…" : "➤"}</button></div>
  </form>;
}

function GenesisWorkspaceSidebar({
  activeConversationId,
  documentStats,
  onOpenConversation,
  recentConversations,
}: {
  activeConversationId: string | null;
  documentStats: GenesisStats;
  onOpenConversation: (document: DocumentRecord) => void;
  recentConversations: DocumentRecord[];
}) {
  return <aside className="alos-genesis-workspace-side">
    <article className="alos-panel alos-genesis-recent"><div className="alos-panel-heading-row"><div><p className="alos-kicker">RIWAYAT</p><h3>Percakapan Terbaru</h3></div><span>{recentConversations.length ? `${recentConversations.length} thread` : "Belum ada"}</span></div>{recentConversations.length ? <ul className="alos-genesis-recent-list">{recentConversations.map((document) => <li key={document.document_id}><button className={document.genesis_conversation_id === activeConversationId ? "active" : ""} onClick={() => onOpenConversation(document)} type="button"><span aria-hidden="true">▤</span><div><strong>{document.title.replace(/^Draft Genesis —\s*/i, "")}</strong><small>{formatGenesisTime(document.updated_at)}</small></div><em>›</em></button></li>)}</ul> : <p className="alos-empty-copy">Belum ada percakapan tersimpan. Kirim kebutuhan pertama untuk memulai thread yang diaudit.</p>}</article>
    <article className="alos-panel alos-genesis-agents"><div className="alos-panel-heading-row"><div><p className="alos-kicker">RUNTIME</p><h3>Genesis Workspace</h3></div><Link href="/agents">Kelola Agen →</Link></div><div className="alos-genesis-agent-empty"><span>✦</span><div><strong>Asisten DRAFT tersedia</strong><small>GENESIS mencatat kebutuhan dan menyiapkan DRAFT; tidak ada agent yang diaktifkan otomatis.</small></div></div></article>
    <article className="alos-panel alos-genesis-focus"><div className="alos-panel-heading-row"><div><p className="alos-kicker">RINGKASAN</p><h3>Fokus Eksekutif</h3></div><Link href="/documents">Lihat detail →</Link></div><ul><li><span>▤</span><strong>{documentStats.genesis}</strong><small>DRAFT dari Genesis</small><em>›</em></li><li><span>✓</span><strong>{documentStats.review}</strong><small>Dokumen perlu review</small><em>›</em></li><li><span>◉</span><strong>{documentStats.total}</strong><small>Dokumen workspace</small><em>›</em></li></ul></article>
  </aside>;
}

function GenesisUploadPreview({
  onPromote,
  onWithdraw,
  promoting,
  withdrawing,
  upload,
}: {
  onPromote: () => void;
  onWithdraw: () => void;
  promoting: boolean;
  withdrawing: boolean;
  upload: GenesisUploadRecord | null;
}) {
  if (!upload) return null;
  return <article className="alos-genesis-upload-preview" aria-live="polite"><div className="alos-genesis-upload-preview-heading"><span aria-hidden="true">▤</span><div><strong>{upload.original_filename}</strong><small>{upload.extension.toUpperCase()} · {formatUploadSize(upload.byte_size)} · SHA-256 tersimpan</small></div><em className={upload.extraction_complete ? "ready" : "review"}>{uploadExtractionLabel(upload)}</em></div>{upload.preview ? <details><summary>Lihat preview teks</summary><pre>{upload.preview}</pre></details> : <p>{upload.extraction_note ?? "Tidak ada preview yang dapat ditampilkan. Periksa berkas asli sebelum melanjutkan."}</p>}{upload.status === "SOURCE_RECEIVED" ? <div className="alos-genesis-upload-actions">{upload.extraction_complete ? <button className="alos-genesis-upload-promote" disabled={promoting || withdrawing} onClick={onPromote} type="button">{promoting ? "Menyimpan DRAFT…" : "Simpan sebagai DRAFT untuk ditinjau"}</button> : null}<button className="alos-genesis-upload-withdraw" disabled={promoting || withdrawing} onClick={onWithdraw} type="button">{withdrawing ? "Menghapus berkas…" : "Batalkan & hapus berkas"}</button></div> : null}<p className="alos-genesis-upload-preview-note">{upload.status === "DRAFT_CREATED" ? "DRAFT sudah tersimpan di Document Center dan menunggu checklist serta review independen." : "Berkas ini belum menjadi dokumen resmi. Tinjau preview sebelum membuat DRAFT untuk pemeriksaan manusia."}</p></article>;
}

function formatGenesisTime(value: string): string {
  return new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
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

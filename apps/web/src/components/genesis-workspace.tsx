"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  formatDocumentDate,
  type DocumentDetail,
  type DocumentRecord,
  type DocumentWorkspace,
} from "@/lib/documents";
import type { SessionActor } from "@/lib/governance";

type ApiFailure = { detail?: string };
type WorkflowStage = "ANALYSIS" | "RND" | "CHECKLIST" | "COMPLETION" | "AGENT";

type StageDefinition = {
  key: WorkflowStage;
  title: string;
  shortTitle: string;
  description: string;
  action: string;
};

const stages: readonly StageDefinition[] = [
  {
    key: "ANALYSIS",
    title: "Draft Analisis",
    shortTitle: "Analisis",
    description: "Catat pembacaan, ruang lingkup, bukti, dan pertanyaan yang harus ditinjau Dirut.",
    action: "Simpan Draft Analisis",
  },
  {
    key: "RND",
    title: "Research Brief",
    shortTitle: "R&D",
    description: "Rumuskan kebutuhan riset setelah analisis awal dinilai sesuai.",
    action: "Mulai R&D",
  },
  {
    key: "CHECKLIST",
    title: "Checklist Perbaikan",
    shortTitle: "Checklist",
    description: "Susun kekurangan, prioritas, owner, dan bukti penyelesaiannya.",
    action: "Buat Checklist",
  },
  {
    key: "COMPLETION",
    title: "Draft Dokumen Pelengkap",
    shortTitle: "Pelengkap",
    description: "Siapkan dokumen pelengkap tanpa pernah menimpa dokumen sumber.",
    action: "Buat Draft Pelengkap",
  },
  {
    key: "AGENT",
    title: "Usulan Agent",
    shortTitle: "Usulan Agent",
    description: "Rumuskan agent yang diperlukan; hasilnya tetap usulan, bukan agent aktif.",
    action: "Buat Usulan Agent",
  },
];

export function GenesisWorkspace({ actor }: { actor: SessionActor }) {
  const [workspaceId, setWorkspaceId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [source, setSource] = useState<DocumentDetail | null>(null);
  const [requirement, setRequirement] = useState("");
  const [conversationPrompt, setConversationPrompt] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingStage, setSavingStage] = useState<WorkflowStage | null>(null);

  const canInitiate = actor.roles.includes("DIRECTOR");
  const sourceCandidates = useMemo(
    () => documents.filter((document) => (
      document.origin !== "GENESIS" && ["APPROVED", "ACTIVE"].includes(document.status)
    )),
    [documents],
  );
  const genesisDrafts = useMemo(
    () => documents.filter((document) => document.origin === "GENESIS"),
    [documents],
  );
  const artifacts = useMemo(() => Object.fromEntries(
    stages.map((stage) => [stage.key, genesisDrafts.find((document) => document.title.startsWith(stagePrefix(stage.key)))]),
  ) as Record<WorkflowStage, DocumentRecord | undefined>, [genesisDrafts]);
  const loadDocuments = useCallback(async (nextWorkspaceId: string) => {
    if (!nextWorkspaceId) {
      setDocuments([]);
      return;
    }
    const response = await fetch(`/api/v1/documents?workspace_id=${encodeURIComponent(nextWorkspaceId)}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await errorDetail(response));
    setDocuments((await response.json()) as DocumentRecord[]);
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const response = await fetch("/api/v1/workspaces", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error(await errorDetail(response));
        const items = (await response.json()) as DocumentWorkspace[];
        const firstWorkspaceId = items[0]?.workspace_id ?? "";
        setWorkspaceId(firstWorkspaceId);
        await loadDocuments(firstWorkspaceId);
      } catch (failure) {
        setError(messageFrom(failure));
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [loadDocuments]);

  useEffect(() => {
    if (!sourceId) return;
    async function loadSource() {
      try {
        setError(null);
        const response = await fetch(`/api/v1/documents/${encodeURIComponent(sourceId)}`, {
          credentials: "same-origin",
          cache: "no-store",
        });
        if (!response.ok) throw new Error(await errorDetail(response));
        setSource((await response.json()) as DocumentDetail);
      } catch (failure) {
        setSource(null);
        setError(messageFrom(failure));
      }
    }
    void loadSource();
  }, [sourceId]);

  async function createArtifact(stage: StageDefinition) {
    const activeRequirement = conversationPrompt || requirement;
    if (!workspaceId || !source || !activeRequirement.trim() || !canInitiate) return;
    setSavingStage(stage.key);
    setError(null);
    setNotice(null);
    const title = `${stagePrefix(stage.key)} ${source.document.title}`.slice(0, 200);
    const sourceCitation = `DOC:${source.document.document_id}@v${source.document.version_number}#sha256:${source.content_sha256}`;
    const workflowRequirement = [
      `Tahap H6: ${stage.title}.`,
      "Instruksi Direktur:",
      activeRequirement.trim(),
      "",
      "Sumber internal yang sudah dapat dibaca:",
      `- ${source.document.title} (${source.document.status}, v${source.document.version_number})`,
      `- Citation: ${sourceCitation}`,
      "",
      "Batas kontrol:",
      "- Hasil harus tetap DRAFT dan membutuhkan pemeriksaan manusia.",
      "- Jangan mengubah dokumen sumber, pricing, SOP resmi, KPI, atau data operasional.",
      "- Usulan agent tidak membuat atau mengaktifkan Agent Contract.",
    ].join("\n");

    try {
      const response = await fetch("/api/v1/genesis/document-drafts", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_id: workspaceId,
          title,
          requirement: workflowRequirement,
          category: stage.key === "AGENT" ? "AGENT_PROPOSAL" : "GENESIS_RESEARCH",
          classification: source.document.classification,
        }),
      });
      if (!response.ok) throw new Error(await errorDetail(response));
      const draft = (await response.json()) as DocumentRecord;
      await loadDocuments(workspaceId);
      setNotice(`${stage.title} tersimpan sebagai DRAFT: ${draft.title}. Dokumen sumber tidak diubah.`);
    } catch (failure) {
      setError(messageFrom(failure));
    } finally {
      setSavingStage(null);
    }
  }

  function submitPrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!source) {
      setError("Pilih dokumen internal yang telah disetujui terlebih dahulu.");
      return;
    }
    if (!requirement.trim()) {
      setError("Tuliskan kebutuhan atau pertanyaan untuk Genesis.");
      return;
    }
    setError(null);
    setConversationPrompt(requirement.trim());
    setNotice("Dokumen dan instruksi siap. Simpan Draft Analisis untuk memulai alur yang diaudit.");
  }

  if (loading) return <section className="alos-content"><p>Memuat Genesis Workspace…</p></section>;

  const draftForReview = genesisDrafts.filter((document) => document.status === "DRAFT" || document.status === "IN_REVIEW");
  const backlogDrafts = [artifacts.CHECKLIST, artifacts.COMPLETION].filter(Boolean) as DocumentRecord[];
  const nextStage = stages.find((stage) => !artifacts[stage.key]);
  const conversationReady = Boolean(source && conversationPrompt);

  return (
    <section className="alos-content alos-h6-workspace" aria-label="Genesis Workspace">
      <header className="alos-h6-heading">
        <div><h2>GENESIS</h2><p>AI Executive Assistant</p></div>
        <button className="alos-h6-enterprise" disabled type="button">♢ Enterprise Mode <span>⌄</span></button>
      </header>

      {!canInitiate ? <article className="alos-h6-director-notice"><strong>Ruang kerja Direktur</strong><span>Untuk pilot H6, hanya Direktur yang dapat memulai analisis atau membuat DRAFT. Anda tetap dapat melihat dokumen yang diizinkan.</span></article> : null}
      {error ? <p className="alos-inline-error">{error}</p> : null}
      {notice ? <p className="alos-inline-success">{notice}</p> : null}

      <div className="alos-h6-grid">
        <article className="alos-panel alos-h6-chat">
          <div className="alos-h6-chat-scroll">
            <div className="alos-h6-director-message"><span>{actor.roles.includes("DIRECTOR") ? "D" : "A"}</span><div><div className="alos-h6-message-meta"><strong>Direktur Utama</strong><small>Instruksi baru</small></div><p>{conversationPrompt || "Pilih dokumen dan ketik instruksi untuk memulai percakapan dengan Genesis."}</p><label className="alos-h6-document-attachment"><span>▣</span><div><strong>{source?.document.title ?? "Pilih dokumen internal"}</strong><small>{source ? `${source.document.category} · v${source.document.version_number}` : "Hanya dokumen APPROVED atau ACTIVE"}</small></div><select aria-label="Dokumen internal yang dianalisis" disabled={!canInitiate} onChange={(event) => { setSource(null); setSourceId(event.target.value); setConversationPrompt(""); setNotice(null); }} value={sourceId}><option value="">Pilih</option>{sourceCandidates.map((document) => <option key={document.document_id} value={document.document_id}>{document.title} · v{document.version_number}</option>)}</select></label></div></div>

            <div className="alos-h6-genesis-message"><span>✦</span><div>
              {!source ? <><strong>Genesis siap membaca sumber yang diizinkan</strong><p>Pilih dokumen internal yang telah disetujui. Genesis tidak memakai draft yang belum tervalidasi sebagai dasar rekomendasi.</p>{sourceCandidates.length === 0 ? <p className="alos-h6-warning">Belum ada dokumen APPROVED atau ACTIVE pada workspace ini.</p> : null}</> : <>
                <div className="alos-h6-readable"><span>✓</span><div><strong>Dokumen dapat dibaca</strong><small>{source.document.title} · {source.content.length.toLocaleString("id-ID")} karakter</small></div><Link href="/documents">Lihat sumber ↗</Link></div>
                <section className="alos-h6-analysis-card"><h3>{artifacts.ANALYSIS ? "Draft Analisis tercatat" : "Analisis siap disusun"}</h3><p>{artifacts.ANALYSIS ? "Draft analisis sudah tersimpan dan menunggu pemeriksaan manusia sebelum Genesis melanjutkan R&D." : conversationReady ? "Genesis akan menyimpan instruksi, versi sumber, citation, ruang lingkup, dan area pemeriksaan sebagai Draft Analisis." : "Ketik instruksi untuk menjelaskan analisis atau rekomendasi yang Dirut perlukan."}</p><div className="alos-h6-analysis-source"><strong>Sumber</strong><span>DOC:{source.document.document_id.slice(0, 8)}…@v{source.document.version_number}</span><span>SHA-256 tersimpan</span></div></section>
              </>}
            </div></div>

            <div className="alos-h6-action-row">
              {!artifacts.ANALYSIS ? <button disabled={!canInitiate || !conversationReady || savingStage !== null} onClick={() => void createArtifact(stages[0])} type="button">▤ <span>{savingStage === "ANALYSIS" ? "Menyimpan…" : "Simpan Draft Analisis"}</span></button> : <Link href="/documents">▤ <span>Buka Draft Analisis</span></Link>}
              <button disabled={!canInitiate || !artifacts.ANALYSIS || !nextStage || savingStage !== null} onClick={() => nextStage && void createArtifact(nextStage)} type="button">♙ <span>{savingStage ? "Menyimpan…" : nextStage ? nextStage.action : "Alur selesai"}</span></button>
              <button className="revision" disabled={!canInitiate || !source} onClick={() => { setConversationPrompt(""); setRequirement(""); setNotice("Silakan perbarui instruksi Dirut lalu kirim kembali."); }} type="button">▱ <span>Minta Revisi</span></button>
            </div>
          </div>

          <form className="alos-h6-composer" onSubmit={submitPrompt}>
            <textarea disabled={!canInitiate} maxLength={10000} onChange={(event) => setRequirement(event.target.value)} placeholder="Ketik pesan atau perintah Anda…" value={requirement} />
            <div><span aria-hidden="true">⌇　▦　▥</span><small>Tekan Enter untuk mengirim</small><button aria-label="Siapkan analisis" disabled={!canInitiate || !workspaceId} type="submit">➤</button></div>
          </form>
        </article>

        <aside className="alos-h6-side">
          <WorkspaceSideCard empty="Belum ada DRAFT dari Genesis." items={draftForReview} title="Draft perlu ditinjau" />
          <WorkspaceSideCard empty="Backlog akan muncul setelah checklist perbaikan dibuat." items={backlogDrafts} title="Backlog Genesis" />
          <WorkspaceSideCard empty="Genesis belum mengusulkan agent." items={artifacts.AGENT ? [artifacts.AGENT] : []} title="Usulan Agent" />
        </aside>
      </div>

      <section className="alos-h6-knowledge"><div><p className="alos-kicker">SUMBER PENGETAHUAN</p><h3>Context <span>ⓘ</span></h3></div><div className="alos-h6-knowledge-cards"><Link href="/documents"><span>▣</span><div><strong>Internal ALOS</strong><small>{sourceCandidates.length ? `${sourceCandidates.length} dokumen disetujui dapat dipilih` : "Dokumen dan evidence terdaftar"}</small></div><b>›</b></Link><Link href="/h5"><span>◎</span><div><strong>External Research</strong><small>Industri, pasar, regulasi, dan best practice yang telah diverifikasi.</small></div><b>›</b></Link></div></section>
    </section>
  );
}

function WorkspaceSideCard({ empty, items, title }: { empty: string; items: DocumentRecord[]; title: string }) {
  return <article className="alos-panel alos-h6-side-card"><div className="alos-h6-side-heading"><h3>{title}</h3><Link href="/documents">Lihat semua →</Link></div>{items.length === 0 ? <p className="alos-empty-copy">{empty}</p> : <ul>{items.slice(0, 3).map((item) => <li key={item.document_id}><span>◫</span><div><strong>{item.title.replace(/^\[GENESIS\/H6\/[A-Z_]+\]\s*/, "")}</strong><small>{item.status.replace("_", " ")} · {formatDocumentDate(item.updated_at)}</small></div></li>)}</ul>}</article>;
}

function stagePrefix(stage: WorkflowStage): string {
  return `[GENESIS/H6/${stage}]`;
}

async function errorDetail(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as ApiFailure | null;
  return payload?.detail ?? "Permintaan tidak dapat diproses.";
}

function messageFrom(failure: unknown): string {
  return failure instanceof Error ? failure.message : "Terjadi kesalahan yang tidak diketahui.";
}

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

const workflowLabels = ["Baca dokumen", "Draft & review", "R&D & checklist", "Dokumen pelengkap", "Usulan agent", "Approval"];

const quickPrompts = [
  "Analisis dokumen ini dan jelaskan kekurangan yang perlu diperbaiki.",
  "Periksa apakah target, PIC, timeline, dan risiko sudah cukup jelas.",
  "Susun rekomendasi R&D yang diperlukan dari dokumen ini.",
  "Usulkan agent read-only bila ada pekerjaan berulang yang terukur.",
];

export function GenesisWorkspace({ actor }: { actor: SessionActor }) {
  const [workspaces, setWorkspaces] = useState<DocumentWorkspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [source, setSource] = useState<DocumentDetail | null>(null);
  const [requirement, setRequirement] = useState("");
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
  const currentStage = useMemo(() => {
    if (!source) return 0;
    if (!artifacts.ANALYSIS) return 1;
    if (!artifacts.RND) return 2;
    if (!artifacts.CHECKLIST) return 3;
    if (!artifacts.COMPLETION) return 4;
    if (!artifacts.AGENT) return 5;
    return 6;
  }, [artifacts, source]);

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
        setWorkspaces(items);
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
    if (!sourceId) {
      setSource(null);
      return;
    }
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

  async function changeWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setSourceId("");
    setSource(null);
    setNotice(null);
    setError(null);
    try {
      await loadDocuments(nextWorkspaceId);
    } catch (failure) {
      setError(messageFrom(failure));
    }
  }

  async function createArtifact(stage: StageDefinition) {
    if (!workspaceId || !source || !requirement.trim() || !canInitiate) return;
    setSavingStage(stage.key);
    setError(null);
    setNotice(null);
    const title = `${stagePrefix(stage.key)} ${source.document.title}`.slice(0, 200);
    const sourceCitation = `DOC:${source.document.document_id}@v${source.document.version_number}#sha256:${source.content_sha256}`;
    const workflowRequirement = [
      `Tahap H6: ${stage.title}.`,
      "Instruksi Direktur:",
      requirement.trim(),
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
    setNotice("Dokumen dan instruksi siap. Simpan Draft Analisis untuk memulai alur yang diaudit.");
  }

  if (loading) return <section className="alos-content"><p>Memuat Genesis Workspace…</p></section>;

  const draftForReview = genesisDrafts.filter((document) => document.status === "DRAFT" || document.status === "IN_REVIEW");
  const backlogDrafts = [artifacts.CHECKLIST, artifacts.COMPLETION].filter(Boolean) as DocumentRecord[];

  return (
    <section className="alos-content alos-h6-workspace" aria-label="Genesis Workspace">
      <header className="alos-h6-heading">
        <div><p className="alos-kicker">ALOS / GENESIS WORKSPACE</p><h2><span>✦</span> GENESIS</h2><p>AI Executive Assistant untuk menganalisis sumber, menyiapkan DRAFT, dan membawa keputusan Dirut ke alur yang terkendali.</p></div>
        <label>Workspace<select aria-label="Workspace Genesis" onChange={(event) => void changeWorkspace(event.target.value)} value={workspaceId}>{workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}</select></label>
      </header>

      {!canInitiate ? <article className="alos-h6-director-notice"><strong>Ruang kerja Direktur</strong><span>Untuk pilot H6, hanya Direktur yang dapat memulai analisis atau membuat DRAFT. Anda tetap dapat melihat dokumen yang diizinkan.</span></article> : null}
      {error ? <p className="alos-inline-error">{error}</p> : null}
      {notice ? <p className="alos-inline-success">{notice}</p> : null}

      <ol className="alos-h6-progress" aria-label="Alur kerja Genesis H6">
        {workflowLabels.map((label, index) => <li className={index < currentStage ? "complete" : index === currentStage ? "current" : ""} key={label}><span>{index < currentStage ? "✓" : index + 1}</span><small>{label}</small></li>)}
      </ol>

      <div className="alos-h6-grid">
        <article className="alos-panel alos-h6-chat">
          <div className="alos-h6-chat-scroll">
            <div className="alos-h6-director-message"><span>{actor.roles.includes("DIRECTOR") ? "D" : "A"}</span><div><strong>Direktur</strong><p>{requirement || "Pilih dokumen lalu tuliskan instruksi untuk Genesis."}</p></div></div>

            <div className="alos-h6-source-select">
              <label>Dokumen internal yang akan dianalisis<select disabled={!canInitiate} onChange={(event) => setSourceId(event.target.value)} value={sourceId}><option value="">Pilih dokumen yang telah disetujui</option>{sourceCandidates.map((document) => <option key={document.document_id} value={document.document_id}>{document.title} · v{document.version_number}</option>)}</select></label>
              {sourceCandidates.length === 0 ? <p>Belum ada dokumen `APPROVED` atau `ACTIVE` yang dapat menjadi sumber analisis. Selesaikan review dokumen terlebih dahulu.</p> : null}
            </div>

            <div className="alos-h6-genesis-message"><span>✦</span><div>
              {!source ? <><strong>Siap membaca sumber yang diizinkan</strong><p>Pilih dokumen internal yang sudah disetujui. Genesis tidak akan menggunakan draft yang belum tervalidasi sebagai dasar keputusan.</p></> : <>
                <div className="alos-h6-readable"><span>✓</span><div><strong>Dokumen dapat dibaca</strong><small>{source.document.title} · v{source.document.version_number} · {source.document.classification}</small></div><Link href="/documents">Lihat sumber ↗</Link></div>
                <strong>Siap membuat {artifacts.ANALYSIS ? "tahap berikutnya" : "Draft Analisis"}</strong>
                <p>Genesis akan menyimpan instruksi Dirut, referensi versi, dan citation sumber ke DRAFT. Tidak ada dokumen sumber yang diubah secara otomatis.</p>
                <p className="alos-h6-citation">Citation: DOC:{source.document.document_id.slice(0, 8)}…@v{source.document.version_number} · SHA-256 tersimpan</p>
              </>}
            </div></div>

            {source ? <div className="alos-h6-artifact-actions">
              {stages.map((stage) => {
                const draft = artifacts[stage.key];
                const previous = stages[stages.indexOf(stage) - 1];
                const locked = Boolean(previous && !artifacts[previous.key]);
                if (draft) return <div className="alos-h6-artifact-complete" key={stage.key}><span>✓</span><div><strong>{stage.shortTitle}</strong><small>{draft.status.replace("_", " ")} · {formatDocumentDate(draft.updated_at)}</small></div><Link href="/documents">Buka ↗</Link></div>;
                return <button disabled={!canInitiate || locked || !requirement.trim() || savingStage !== null} key={stage.key} onClick={() => void createArtifact(stage)} type="button"><span>{locked ? "○" : "＋"}</span><div><strong>{stage.action}</strong><small>{locked ? "Selesaikan tahap sebelumnya terlebih dahulu" : stage.description}</small></div>{savingStage === stage.key ? <em>Menyimpan…</em> : null}</button>;
              })}
            </div> : null}
          </div>

          <form className="alos-h6-composer" onSubmit={submitPrompt}>
            <textarea disabled={!canInitiate} maxLength={10000} onChange={(event) => setRequirement(event.target.value)} placeholder="Contoh: Analisis dokumen ini, rekomendasikan kekurangannya, lalu siapkan draft perbaikannya." value={requirement} />
            <div><small>Hasil selalu DRAFT; keputusan, dokumen resmi, dan agent ACTIVE tetap memerlukan manusia.</small><button aria-label="Siapkan analisis" disabled={!canInitiate || !workspaceId} type="submit">➤</button></div>
          </form>
        </article>

        <aside className="alos-h6-side">
          <WorkspaceSideCard empty="Belum ada DRAFT dari Genesis." items={draftForReview} title="Draft perlu ditinjau" />
          <WorkspaceSideCard empty="Backlog akan muncul setelah checklist perbaikan dibuat." items={backlogDrafts} title="Backlog Genesis" />
          <WorkspaceSideCard empty="Genesis belum mengusulkan agent." items={artifacts.AGENT ? [artifacts.AGENT] : []} title="Usulan Agent" />
          <article className="alos-panel alos-h6-control-card"><p className="alos-kicker">BATAS KONTROL</p><h3>Direktur memutuskan</h3><ul><li>Genesis membuat DRAFT, bukan perubahan resmi.</li><li>Dokumen sumber tidak dapat ditimpa.</li><li>Agent hanya dapat menjadi ACTIVE melalui H4.</li></ul><Link href="/governance">Buka Governance &amp; Agent Control →</Link></article>
        </aside>
      </div>

      <section className="alos-h6-knowledge"><div><p className="alos-kicker">SUMBER PENGETAHUAN</p><h3>Ruang lingkup riset</h3></div><div className="alos-h6-knowledge-cards"><Link href="/documents"><span>▣</span><div><strong>Internal ALOS</strong><small>{sourceCandidates.length ? `${sourceCandidates.length} dokumen disetujui dapat dipilih` : "Belum ada dokumen disetujui"}</small></div><b>›</b></Link><Link href="/h5"><span>◎</span><div><strong>External Research</strong><small>Teknologi, pasar, regulasi, dan tren harus ditambahkan sebagai evidence terverifikasi.</small></div><b>›</b></Link></div></section>
    </section>
  );
}

function WorkspaceSideCard({ empty, items, title }: { empty: string; items: DocumentRecord[]; title: string }) {
  return <article className="alos-panel alos-h6-side-card"><div className="alos-h6-side-heading"><h3>{title}</h3><Link href="/documents">Lihat semua →</Link></div>{items.length === 0 ? <p className="alos-empty-copy">{empty}</p> : <ul>{items.slice(0, 3).map((item) => <li key={item.document_id}><span>◫</span><div><strong>{item.title.replace(/^\[GENESIS\/H6\]\s*/, "")}</strong><small>{item.status.replace("_", " ")} · {formatDocumentDate(item.updated_at)}</small></div></li>)}</ul>}</article>;
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

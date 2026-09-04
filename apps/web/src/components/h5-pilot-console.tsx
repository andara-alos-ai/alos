"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, type SessionActor, type Workspace } from "@/lib/governance";

type SourceVault = {
  source_vault_policy_id: string;
  workspace_id: string;
  allowed_root_url: string;
  excluded_folder_url: string;
  access_mode: "READ_ONLY";
  created_at: string;
  updated_at: string;
};

type SourceVersion = {
  source_id: string;
  source_version_id: string;
  workspace_id: string;
  source_key: string;
  name: string;
  source_type: "DOCX" | "PDF" | "TEXT" | "URL";
  classification: "PUBLIC" | "INTERNAL";
  status: string;
  version_label: string;
  sha256: string;
  locator: string | null;
  citation_count: number;
  source_vault_policy_id: string | null;
};

type H5Data = {
  actor: SessionActor;
  workspaces: Workspace[];
  vault: SourceVault | null;
  sources: SourceVersion[];
};

const permittedRoot = "https://drive.google.com/drive/folders/1D66GYJVl7WZlefS8e8FO9lkL034CA9wS";
const excludedFolder = "https://drive.google.com/drive/folders/1rf-8esLauaCNylWm6Y65oQfMU68AvTqj";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === "string" ? payload.detail : undefined;
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function H5PilotConsole() {
  const router = useRouter();
  const [data, setData] = useState<H5Data | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [vaultForm, setVaultForm] = useState({
    allowedRootUrl: permittedRoot,
    excludedFolderUrl: excludedFolder,
    reason: "Membatasi pilot H5 pada sumber manajemen yang disetujui dan satu folder yang dikecualikan.",
  });
  const [sourceForm, setSourceForm] = useState({
    sourceKey: "",
    name: "",
    sourceType: "TEXT" as SourceVersion["source_type"],
    versionLabel: "v0.1",
    locator: "",
    content: "",
  });

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, foundation?: Pick<H5Data, "actor" | "workspaces">) => {
    const base = foundation ?? await loadFoundation();
    const [vault, sources] = await Promise.all([
      loadVault(selectedWorkspaceId),
      api<SourceVersion[]>(`/api/v1/workspaces/${selectedWorkspaceId}/sources`),
    ]);
    setData({ ...base, vault, sources });
    if (vault) {
      setVaultForm({
        allowedRootUrl: vault.allowed_root_url,
        excludedFolderUrl: vault.excluded_folder_url,
        reason: "Memperbarui batas Source Vault H5 yang telah disetujui.",
      });
    }
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (foundation.workspaces.length === 0) {
          setError("Akun ini belum memiliki workspace aktif.");
          return;
        }
        const firstWorkspaceId = foundation.workspaces[0].workspace_id;
        setWorkspaceId(firstWorkspaceId);
        await loadWorkspace(firstWorkspaceId, foundation);
      } catch (loadError: unknown) {
        if (loadError instanceof ApiError && loadError.status === 401) {
          router.replace("/login");
          return;
        }
        setError("Kontrol H5 tidak dapat dimuat. Coba muat ulang halaman.");
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [loadWorkspace, router]);

  const canOperatePilot = data?.actor.roles.includes("IT_LEAD") ?? false;

  async function reload() {
    if (!data || !workspaceId) return;
    await loadWorkspace(workspaceId, { actor: data.actor, workspaces: data.workspaces });
  }

  async function selectWorkspace(nextWorkspaceId: string) {
    if (!data) return;
    setWorkspaceId(nextWorkspaceId);
    setLoading(true);
    setError("");
    setNotice("");
    try {
      await loadWorkspace(nextWorkspaceId, { actor: data.actor, workspaces: data.workspaces });
    } catch {
      setError("Workspace tidak dapat dimuat.");
    } finally {
      setLoading(false);
    }
  }

  async function saveVault() {
    if (!canOperatePilot || !workspaceId) return;
    await mutate("Source Vault tersimpan. Tidak ada koneksi, token, atau pembacaan Google Drive otomatis.", async () => {
      await api<SourceVault>(`/api/v1/workspaces/${workspaceId}/source-vault`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          allowed_root_url: vaultForm.allowedRootUrl,
          excluded_folder_url: vaultForm.excludedFolderUrl,
          reason: vaultForm.reason,
        }),
      });
    });
  }

  async function registerSource() {
    const vault = data?.vault;
    if (!vault || !workspaceId) return;
    await mutate("Versi sumber dicatat sebagai SOURCE_RECEIVED. Verifikasi manusia masih wajib.", async () => {
      await api<SourceVersion>("/api/v1/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_id: workspaceId,
          source_key: sourceForm.sourceKey,
          name: sourceForm.name,
          source_type: sourceForm.sourceType,
          classification: "INTERNAL",
          version_label: sourceForm.versionLabel,
          locator: sourceForm.locator,
          content: sourceForm.content,
          source_vault_policy_id: vault.source_vault_policy_id,
          vault_attestation: true,
        }),
      });
    });
    setSourceForm({ sourceKey: "", name: "", sourceType: "TEXT", versionLabel: "v0.1", locator: "", content: "" });
  }

  async function verifySource(sourceKey: string) {
    if (!workspaceId) return;
    await mutate(`${sourceKey} terverifikasi dan sekarang dapat menjadi evidence read-only.`, async () => {
      await api<SourceVersion>(`/api/v1/sources/${sourceKey}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_id: workspaceId,
          reason: "Verifikasi manusia untuk pilot H5; sumber tersedia hanya sebagai evidence read-only.",
        }),
      });
    });
  }

  async function createDrafts(path: "/api/v1/h5/validation-agents/drafts" | "/api/v1/h5/validation-controls/drafts", success: string) {
    if (!workspaceId) return;
    await mutate(success, async () => {
      await api<Record<string, unknown>>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
    });
  }

  async function mutate(success: string, action: () => Promise<void>) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await action();
      await reload();
      setNotice(success);
    } catch (mutationError: unknown) {
      if (mutationError instanceof ApiError && mutationError.status === 401) {
        router.replace("/login");
      } else if (mutationError instanceof ApiError && mutationError.status === 403) {
        setError("Aksi H5 ini hanya dapat dilakukan oleh IT Lead pada workspace aktif.");
      } else if (mutationError instanceof ApiError && mutationError.detail) {
        setError(mutationError.detail);
      } else {
        setError("Aksi tidak dapat disimpan. Periksa input dan coba lagi.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading && !data) return <main className="loading-shell">Memuat H5 Controlled Pilot…</main>;
  if (!data) return <main className="loading-shell"><p>{error || "Sesi tidak tersedia."}</p><Link className="text-link" href="/login">Ke halaman login</Link></main>;

  return (
    <main className="dashboard-shell h5-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">ALOS / H5 VALIDATION PILOT</p>
          <h1>Source Vault &amp; Validation</h1>
          <p className="muted">Sumber dicatat manual, diverifikasi manusia, dan dipakai hanya oleh kontrak Agent DRAFT yang read-only.</p>
        </div>
        <div className="header-actions">
          <span className="role-badge">{data.actor.roles.join(" · ")}</span>
          <Link className="secondary-button button-link" href="/genesis">Genesis</Link>
          <Link className="secondary-button button-link" href="/agents">Registry</Link>
          <Link className="secondary-button button-link" href="/releases">H4 Release</Link>
        </div>
      </header>

      <section className="workspace-bar" aria-label="Workspace H5">
        <div>
          <label htmlFor="h5-workspace">Workspace aktif</label>
          <select disabled={saving} id="h5-workspace" onChange={(event) => void selectWorkspace(event.target.value)} value={workspaceId}>
            {data.workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name} · {workspace.workspace_key}</option>)}
          </select>
        </div>
        <p>Peran: {canOperatePilot ? "IT Lead dapat menyiapkan DRAFT." : "read-only"} Tidak ada API key, password, OAuth, atau crawler Drive di halaman ini.</p>
      </section>

      {error ? <p className="banner-error" role="alert">{error}</p> : null}
      {notice ? <p className="banner-success" role="status">{notice}</p> : null}

      <section className="h5-step-grid" aria-label="Tahapan H5">
        <StatusCard label="1. Source Vault" ready={Boolean(data.vault)} value={data.vault ? "Configured" : "Belum diatur"} />
        <StatusCard label="2. Evidence" ready={data.sources.some((source) => source.status === "VERIFIED")} value={`${data.sources.filter((source) => source.status === "VERIFIED").length} terverifikasi`} />
        <StatusCard label="3. Agent DRAFT" ready={false} value="Siapkan dari catalog" />
        <StatusCard label="4. UAT & review" ready={false} value="Lanjutkan di H4 Release" />
      </section>

      <section className="dashboard-grid h5-grid">
        <article className="panel">
          <div className="panel-heading"><div><p className="eyebrow">SOURCE VAULT</p><h2>Batas sumber yang dapat didaftarkan</h2></div><span className={data.vault ? "permission-ok" : "permission-readonly"}>{data.vault ? "READ_ONLY" : "Belum ada policy"}</span></div>
          <p className="safe-note">Folder sumber dan folder yang dikecualikan hanya menjadi kebijakan audit. ALOS tidak membaca Google Drive sampai content extract didaftarkan oleh manusia.</p>
          <label className="h5-field">Root folder yang diizinkan<input disabled={!canOperatePilot || saving} onChange={(event) => setVaultForm({ ...vaultForm, allowedRootUrl: event.target.value })} value={vaultForm.allowedRootUrl} /></label>
          <label className="h5-field">Folder yang dikecualikan<input disabled={!canOperatePilot || saving} onChange={(event) => setVaultForm({ ...vaultForm, excludedFolderUrl: event.target.value })} value={vaultForm.excludedFolderUrl} /></label>
          <label className="h5-field">Alasan audit<textarea disabled={!canOperatePilot || saving} onChange={(event) => setVaultForm({ ...vaultForm, reason: event.target.value })} value={vaultForm.reason} /></label>
          <button disabled={!canOperatePilot || saving} onClick={() => void saveVault()} type="button">{saving ? "Menyimpan…" : "Simpan Source Vault & audit"}</button>
        </article>

        <article className="panel h5-control-panel">
          <p className="eyebrow">VALIDATION AGENTS &amp; CONTROLS</p>
          <h2>Siapkan tanpa menjalankan Agent</h2>
          <p className="muted">Catalog yang dibuat: Daily Brief, Evidence Checker, dan Permit/Overdue Monitor. Semua LOW risk, output bercitation, dan tetap DRAFT.</p>
          <ol className="h5-control-list">
            <li><strong>1. Agent Contracts</strong><span>Buat atau perbarui successor DRAFT dari catalog H5.</span><button disabled={!canOperatePilot || saving} onClick={() => void createDrafts("/api/v1/h5/validation-agents/drafts", "Tiga Agent Contract H5 telah disiapkan sebagai DRAFT.")} type="button">Siapkan 3 Agent DRAFT</button></li>
            <li><strong>2. Tool &amp; permissions</strong><span>Hanya menyiapkan Tool dan Permission Policy DRAFT. Persetujuan independen tetap wajib.</span><button disabled={!canOperatePilot || saving} onClick={() => void createDrafts("/api/v1/h5/validation-controls/drafts", "Control DRAFT telah disiapkan. Setujui secara independen sebelum UAT.")} type="button">Siapkan Control DRAFT</button></li>
            <li><strong>3. UAT &amp; GO / HOLD / NO-GO</strong><span>Jalankan fixture, review, dan keputusan manusia melalui lifecycle release.</span><Link className="secondary-button button-link" href="/releases">Buka H4 Release Governance</Link></li>
          </ol>
        </article>
      </section>

      <section className="dashboard-grid h5-grid lower-grid">
        <article className="panel h5-register-panel">
          <p className="eyebrow">MANUAL SOURCE REGISTRATION</p>
          <h2>Catat extract bukti</h2>
          <p className="muted">Salin extract teks yang telah diperiksa manusia. Locator hanya referensi; Runtime tidak mengunduh URL tersebut.</p>
          {!data.vault ? <p className="empty-state">Atur Source Vault lebih dahulu.</p> : <div className="h5-source-form">
            <label>Source key<input disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, sourceKey: event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") })} placeholder="MISAL: SOP_OPERASIONAL" value={sourceForm.sourceKey} /></label>
            <label>Nama sumber<input disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, name: event.target.value })} value={sourceForm.name} /></label>
            <label>Jenis<select disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, sourceType: event.target.value as SourceVersion["source_type"] })} value={sourceForm.sourceType}><option value="TEXT">TEXT extract</option><option value="DOCX">DOCX extract</option><option value="PDF">PDF extract</option><option value="URL">URL extract</option></select></label>
            <label>Versi<input disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, versionLabel: event.target.value })} value={sourceForm.versionLabel} /></label>
            <label className="h5-wide">Drive locator / referensi<input disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, locator: event.target.value })} placeholder="Link file atau folder yang sudah Anda periksa" value={sourceForm.locator} /></label>
            <label className="h5-wide">Extract teks yang diverifikasi<textarea disabled={!canOperatePilot || saving} onChange={(event) => setSourceForm({ ...sourceForm, content: event.target.value })} placeholder="Tempel isi penting yang dapat menjadi evidence. Jangan masukkan credential atau informasi rahasia yang tidak diperlukan." value={sourceForm.content} /></label>
            <p className="safe-note h5-wide">Dengan menyimpan, Anda mengesahkan bahwa locator berada pada Source Vault yang diizinkan dan bukan folder yang dikecualikan.</p>
            <button disabled={!canOperatePilot || saving} onClick={() => void registerSource()} type="button">Simpan source version</button>
          </div>}
        </article>

        <article className="panel">
          <p className="eyebrow">EVIDENCE REGISTER</p>
          <h2>Verifikasi sumber sebelum retrieval</h2>
          {data.sources.length === 0 ? <p className="empty-state">Belum ada source version pada workspace ini.</p> : <div className="h5-source-list">
            {data.sources.map((source) => <article key={source.source_version_id}><div><strong>{source.name}</strong><span>{source.source_key} · {source.version_label} · {source.citation_count} citation</span><small>{source.status === "VERIFIED" ? "Verified — boleh menjadi evidence read-only" : "Source received — belum boleh diretrieval"}</small></div>{source.status === "VERIFIED" ? <span className="permission-ok">VERIFIED</span> : <button disabled={!canOperatePilot || saving} onClick={() => void verifySource(source.source_key)} type="button">Verifikasi &amp; audit</button>}</article>)}
          </div>}
        </article>
      </section>
    </main>
  );
}

async function loadFoundation(): Promise<Pick<H5Data, "actor" | "workspaces">> {
  const [actor, workspaces] = await Promise.all([
    api<SessionActor>("/api/v1/whoami"),
    api<Workspace[]>("/api/v1/workspaces"),
  ]);
  return { actor, workspaces };
}

async function loadVault(workspaceId: string): Promise<SourceVault | null> {
  try {
    return await api<SourceVault>(`/api/v1/workspaces/${workspaceId}/source-vault`);
  } catch (error: unknown) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function StatusCard({ label, ready, value }: { label: string; ready: boolean; value: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{ready ? "Ready" : "Pending"}</strong><small>{value}</small></article>;
}

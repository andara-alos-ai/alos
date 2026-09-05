"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  agentBuilderSteps,
  canEditAgentRegistry,
  draftPayloadFromForm,
  eligibleParents,
  emptyAgentDraftForm,
  emptyAgentRunForm,
  formFromAgent,
  latestVersion,
  registryConflictMessage,
  runPayloadFromForm,
  runtimeBlockedMessage,
  type AgentDraftForm,
  type AgentDraftResult,
  type AgentRecord,
  type AgentRunForm,
  type AgentRunResult,
} from "@/lib/agent-registry";
import {
  ApiError,
  apiErrorDetail,
  formatDateTime,
  type AuditEvent,
  type SessionActor,
  type Workspace,
} from "@/lib/governance";

type RegistryData = {
  actor: SessionActor;
  workspaces: Workspace[];
  agents: AgentRecord[];
  audit: AuditEvent[];
};

type RegistryFoundation = Pick<RegistryData, "actor" | "workspaces">;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => undefined);
    throw new ApiError(response.status, apiErrorDetail(payload));
  }
  return (await response.json()) as T;
}

export function AgentRegistry() {
  const router = useRouter();
  const [data, setData] = useState<RegistryData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedAgentKey, setSelectedAgentKey] = useState("");
  const [editingAgentKey, setEditingAgentKey] = useState("");
  const [form, setForm] = useState<AgentDraftForm>(emptyAgentDraftForm);
  const [runForm, setRunForm] = useState<AgentRunForm>(emptyAgentRunForm);
  const [latestRun, setLatestRun] = useState<AgentRunResult | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, base?: RegistryFoundation) => {
    const foundation = base ?? (await loadFoundation());
    const [agents, audit] = await Promise.all([
      api<AgentRecord[]>(`/api/v1/agents?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
      api<AuditEvent[]>(`/api/v1/audit-events?workspace_id=${encodeURIComponent(selectedWorkspaceId)}&limit=40`),
    ]);
    setData({ ...foundation, agents, audit: audit.filter((event) => event.action.startsWith("AGENT_")) });
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (!canEditAgentRegistry(foundation.actor.roles)) {
          setForbidden(true);
          return;
        }
        if (foundation.workspaces.length === 0) {
          setError("Akun IT Lead ini belum memiliki workspace aktif.");
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
        if (loadError instanceof ApiError && loadError.status === 403) {
          setForbidden(true);
          return;
        }
        setError("Registry tidak dapat dimuat. Coba muat ulang halaman.");
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [loadWorkspace, router]);

  const selectedAgent = useMemo(
    () => data?.agents.find((agent) => agent.agent_key === selectedAgentKey),
    [data?.agents, selectedAgentKey],
  );
  const selectedVersion = selectedAgent ? latestVersion(selectedAgent) : undefined;
  const parentOptions = useMemo(
    () => eligibleParents(data?.agents ?? [], editingAgentKey),
    [data?.agents, editingAgentKey],
  );

  function changeForm<Key extends keyof AgentDraftForm>(key: Key, value: AgentDraftForm[Key]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setLoading(true);
    setError("");
    setNotice("");
    setSelectedAgentKey("");
    setEditingAgentKey("");
    setForm(emptyAgentDraftForm());
    setRunForm(emptyAgentRunForm());
    setLatestRun(null);
    try {
      await loadWorkspace(nextWorkspaceId, data ? foundationOf(data) : undefined);
    } catch (loadError: unknown) {
      handleApiError(loadError, setError, router);
    } finally {
      setLoading(false);
    }
  }

  function startNewDraft() {
    setEditingAgentKey("");
    setSelectedAgentKey("");
    setForm(emptyAgentDraftForm());
    setRunForm(emptyAgentRunForm());
    setLatestRun(null);
    setActiveStep(0);
    setError("");
    setNotice("");
  }

  function startEdit(agent: AgentRecord) {
    const version = latestVersion(agent);
    if (!version || version.lifecycle_status !== "DRAFT") {
      setError("Hanya Agent dengan versi DRAFT yang dapat diubah.");
      return;
    }
    setEditingAgentKey(agent.agent_key);
    setSelectedAgentKey(agent.agent_key);
    setForm(formFromAgent(agent));
    setLatestRun(null);
    setActiveStep(0);
    setError("");
    setNotice("");
  }

  function selectAgent(agent: AgentRecord) {
    const version = latestVersion(agent);
    setSelectedAgentKey(agent.agent_key);
    setRunForm({
      input: "{}",
      requestedToolKeys: version?.contract_snapshot.tool_keys.join(", ") ?? "",
    });
    setLatestRun(null);
    setError("");
    setNotice("");
  }

  async function runFixture() {
    if (!data || !selectedAgent || !selectedVersion || !workspaceId) {
      return;
    }
    if (selectedVersion.lifecycle_status !== "DRAFT") {
      setError("H3 Test Run hanya tersedia untuk Agent dengan versi DRAFT aktif.");
      return;
    }
    setRunning(true);
    setError("");
    setNotice("");
    try {
      const result = await api<AgentRunResult>(
        `/api/v1/agents/${encodeURIComponent(selectedAgent.agent_key)}/runs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(runPayloadFromForm(runForm, workspaceId)),
        },
      );
      setLatestRun(result);
      await loadWorkspace(workspaceId, foundationOf(data));
      setNotice(
        result.status === "SUCCEEDED"
          ? `Fixture run ${result.agent_key} berhasil dan telah diaudit.`
          : `Fixture run diblokir secara aman dan telah diaudit (${result.error_code ?? "POLICY"}).`,
      );
    } catch (runError: unknown) {
      if (runError instanceof Error && !(runError instanceof ApiError)) {
        setError(runError.message);
      } else {
        handleRuntimeApiError(runError, setError, router);
      }
    } finally {
      setRunning(false);
    }
  }

  async function saveDraft() {
    if (!data || !workspaceId) {
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = draftPayloadFromForm(form, workspaceId);
      const result = await api<AgentDraftResult>(
        editingAgentKey ? `/api/v1/agents/${encodeURIComponent(editingAgentKey)}/draft` : "/api/v1/agents/drafts",
        {
          method: editingAgentKey ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      await loadWorkspace(workspaceId, foundationOf(data));
      setEditingAgentKey(result.agent_key);
      setSelectedAgentKey(result.agent_key);
      setActiveStep(agentBuilderSteps.length - 1);
      setNotice(`DRAFT ${result.agent_key} versi ${result.semantic_version} tersimpan dan diaudit.`);
    } catch (saveError: unknown) {
      if (saveError instanceof Error && !(saveError instanceof ApiError)) {
        setError(saveError.message);
      } else {
        handleApiError(saveError, setError, router);
      }
    } finally {
      setSaving(false);
    }
  }

  async function retire(agent: AgentRecord) {
    if (!window.confirm(`Pensiunkan ${agent.agent_key}? Riwayat dan audit tetap disimpan.`)) {
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await api<AgentDraftResult>(`/api/v1/agents/${encodeURIComponent(agent.agent_key)}/retire`, {
        method: "POST",
      });
      if (data) {
        await loadWorkspace(workspaceId, foundationOf(data));
      }
      setSelectedAgentKey(result.agent_key);
      setNotice(`${result.agent_key} dipensiunkan sebagai versi ${result.semantic_version}; tidak ada data yang dihapus.`);
    } catch (retireError: unknown) {
      handleApiError(retireError, setError, router);
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin", cache: "no-store" });
    router.replace("/login");
    router.refresh();
  }

  if (loading && !data && !forbidden) {
    return <main className="loading-shell">Memuat Agent Registry…</main>;
  }

  if (forbidden) {
    return (
      <main className="access-denied-shell">
        <p className="eyebrow">ALOS / AGENT REGISTRY</p>
        <h1>Akses khusus IT Lead</h1>
        <p>Registry Agent hanya dapat dibuka dan diubah oleh akun dengan peran IT_LEAD.</p>
        <Link className="secondary-button button-link" href="/governance">Kembali ke Governance Dashboard</Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="loading-shell">
        <p>{error || "Sesi Registry tidak tersedia."}</p>
        <Link className="text-link" href="/login">Ke halaman login</Link>
      </main>
    );
  }

  return (
    <main className="registry-shell">
      <header className="dashboard-header registry-header">
        <div>
          <p className="eyebrow">ALOS / H2 REGISTRY</p>
          <h1>Agent Registry</h1>
          <p className="muted">Kontrak terversi, hierarki terbatas, dan audit append-only. Semua hasil Builder tetap DRAFT.</p>
        </div>
        <div className="header-actions">
          <span className="role-badge">IT_LEAD</span>
          <Link className="secondary-button button-link" href="/governance">Governance</Link>
          <Link className="secondary-button button-link" href="/releases">Release</Link>
          <button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button>
        </div>
      </header>

      <section className="workspace-bar registry-workspace" aria-label="Pemilihan workspace Agent Registry">
        <div>
          <label htmlFor="registry-workspace">Workspace aktif</label>
          <select id="registry-workspace" onChange={(event) => void selectWorkspace(event.target.value)} value={workspaceId}>
            {data.workspaces.map((workspace) => (
              <option key={workspace.workspace_id} value={workspace.workspace_id}>
                {workspace.name} · {workspace.workspace_key}
              </option>
            ))}
          </select>
        </div>
        <p>Kontrak, prompt, dan evidence DRAFT dikompilasi Genesis secara lokal. API key maupun credential tidak pernah dikirim ke browser.</p>
      </section>

      {error ? <p className="banner-error" role="alert">{error}</p> : null}
      {notice ? <p className="banner-success" role="status">{notice}</p> : null}

      <section className="registry-layout">
        <aside className="panel registry-list-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">REGISTERED AGENTS</p><h2>{data.agents.length} Agent</h2></div>
            <button onClick={startNewDraft} type="button">+ DRAFT</button>
          </div>
          {data.agents.length === 0 ? <p className="empty-state">Belum ada Agent pada workspace ini. Buat DRAFT pertama untuk Gate A.</p> : null}
          <ol className="agent-list">
            {data.agents.map((agent) => {
              const version = latestVersion(agent);
              return (
                <li key={agent.agent_contract_id}>
                  <button
                    className={selectedAgentKey === agent.agent_key ? "agent-row selected" : "agent-row"}
                    onClick={() => selectAgent(agent)}
                    type="button"
                  >
                    <span className="agent-level">L{agent.agent_level}</span>
                    <span><strong>{agent.name}</strong><small>{agent.agent_key} · {version?.semantic_version ?? "—"}</small></span>
                    <span className={`lifecycle-pill lifecycle-${(version?.lifecycle_status ?? "DRAFT").toLowerCase()}`}>{version?.lifecycle_status ?? "DRAFT"}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>

        <section className="registry-content">
          <article className="panel builder-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">GENESIS BUILDER</p><h2>{editingAgentKey ? `Ubah ${editingAgentKey}` : "Buat Agent DRAFT"}</h2></div>
              <span className="permission-ok">IT Lead only</span>
            </div>
            <ol className="builder-steps" aria-label="Tahapan Builder">
              {agentBuilderSteps.map((step, index) => (
                <li className={index === activeStep ? "active" : index < activeStep ? "complete" : ""} key={step}>
                  <button onClick={() => setActiveStep(index)} type="button"><span>{index + 1}</span>{step}</button>
                </li>
              ))}
            </ol>

            {activeStep === 0 ? (
              <div className="builder-fields two-column-fields">
                <label>Agent key<input disabled={Boolean(editingAgentKey)} onChange={(event) => changeForm("agentKey", event.target.value)} placeholder="PROPERTY_DAILY_BRIEF" value={form.agentKey} /></label>
                <label>Nama Agent<input onChange={(event) => changeForm("name", event.target.value)} placeholder="Property Daily Brief" value={form.name} /></label>
                <label>Parent Agent<select onChange={(event) => changeForm("parentAgentKey", event.target.value)} value={form.parentAgentKey}><option value="">Root Agent · level 0</option>{parentOptions.map((agent) => <option key={agent.agent_key} value={agent.agent_key}>{agent.agent_key} · level {agent.agent_level + 1}</option>)}</select></label>
                <p className="field-note">Hierarki dibatasi sampai level 2; validasi parent dan circular reference tetap dilakukan oleh PostgreSQL.</p>
              </div>
            ) : null}

            {activeStep === 1 ? <div className="builder-fields"><label>Tujuan operasional<textarea minLength={20} onChange={(event) => changeForm("objective", event.target.value)} placeholder="Jelaskan pekerjaan read-only dan outcome yang diharapkan…" rows={6} value={form.objective} /></label><p className="field-note">Genesis mengompilasi purpose, prompt, dan evidence secara deterministik. Ia tidak dapat menentukan risk, tools, permission, owner, atau approval.</p></div> : null}

            {activeStep === 2 ? <div className="builder-fields two-column-fields"><label>Input schema (JSON)<textarea className="code-input" onChange={(event) => changeForm("inputSchema", event.target.value)} rows={10} spellCheck="false" value={form.inputSchema} /></label><label>Output schema (JSON)<textarea className="code-input" onChange={(event) => changeForm("outputSchema", event.target.value)} rows={10} spellCheck="false" value={form.outputSchema} /></label></div> : null}

            {activeStep === 3 ? <div className="builder-fields two-column-fields"><label>Tool keys (pisahkan koma)<input onChange={(event) => changeForm("toolKeys", event.target.value)} placeholder="SOURCE_REGISTRY_SEARCH" value={form.toolKeys} /></label><label>Permission keys (pisahkan koma)<input onChange={(event) => changeForm("permissionKeys", event.target.value)} placeholder="SOURCE_READ_INTERNAL" value={form.permissionKeys} /></label><label>KPI (array JSON)<textarea className="code-input" onChange={(event) => changeForm("kpis", event.target.value)} rows={6} spellCheck="false" value={form.kpis} /></label><p className="field-note">Tool dan izin adalah kontrol manusia. Kosongkan bila Agent tidak membutuhkan akses eksternal atau data terdaftar.</p></div> : null}

            {activeStep === 4 ? <div className="builder-fields two-column-fields"><label>Risk level<select onChange={(event) => changeForm("riskLevel", event.target.value as AgentDraftForm["riskLevel"])} value={form.riskLevel}><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option></select></label><label>Data classification<select onChange={(event) => changeForm("dataClassification", event.target.value as AgentDraftForm["dataClassification"])} value={form.dataClassification}><option value="PUBLIC">PUBLIC</option><option value="INTERNAL">INTERNAL</option><option value="CONFIDENTIAL">CONFIDENTIAL</option><option value="RESTRICTED">RESTRICTED</option></select></label><label>Timeout (detik)<input max="3600" min="1" onChange={(event) => changeForm("timeoutSeconds", event.target.value)} type="number" value={form.timeoutSeconds} /></label><label className="checkbox-field"><input checked={form.approvalRequired} onChange={(event) => changeForm("approvalRequired", event.target.checked)} type="checkbox" />Memerlukan persetujuan manusia</label><label className="full-width">Forbidden actions (satu per baris)<textarea onChange={(event) => changeForm("forbiddenActions", event.target.value)} rows={5} value={form.forbiddenActions} /></label></div> : null}

            {activeStep === 5 ? <div className="builder-review"><p>Prompt dan evidence requirement dikompilasi Genesis secara lokal dari tujuan serta forbidden actions. Pembuatan DRAFT tidak memanggil provider dan tidak mengonsumsi limit Model Gateway.</p><dl className="review-list"><div><dt>Agent</dt><dd>{form.agentKey || "Belum diisi"}</dd></div><div><dt>Risk</dt><dd>{form.riskLevel} · {form.approvalRequired ? "approval wajib" : "tanpa approval"}</dd></div><div><dt>Lifecycle</dt><dd>DRAFT saja</dd></div><div><dt>Versi</dt><dd>{editingAgentKey ? "Versi baru 0.x.0" : "0.1.0"}</dd></div></dl><p className="safe-note">Menyimpan akan menulis audit append-only. DRAFT tidak menjalankan Agent dan tidak dapat mengubah data produksi.</p></div> : null}

            <div className="builder-actions"><button className="secondary-button" disabled={activeStep === 0 || saving} onClick={() => setActiveStep((step) => step - 1)} type="button">Kembali</button>{activeStep < agentBuilderSteps.length - 1 ? <button onClick={() => setActiveStep((step) => step + 1)} type="button">Lanjut</button> : <button disabled={saving} onClick={() => void saveDraft()} type="button">{saving ? "Menyimpan…" : editingAgentKey ? "Simpan versi DRAFT & audit" : "Buat DRAFT & audit"}</button>}</div>
          </article>

          <article className="panel agent-detail-panel">
            <div className="panel-heading"><div><p className="eyebrow">CONTRACT & VERSION</p><h2>{selectedAgent ? selectedAgent.name : "Pilih Agent"}</h2></div>{selectedAgent ? <span className="role-badge">Level {selectedAgent.agent_level}</span> : null}</div>
            {!selectedAgent ? <p className="empty-state">Pilih Agent dari daftar untuk melihat Contract, versi, dan prompt hasil Genesis.</p> : null}
            {selectedAgent && selectedVersion ? <><div className="agent-detail-actions"><button disabled={selectedVersion.lifecycle_status !== "DRAFT"} onClick={() => startEdit(selectedAgent)} type="button">Ubah DRAFT</button><button className="danger-button" disabled={saving || selectedVersion.lifecycle_status === "RETIRED"} onClick={() => void retire(selectedAgent)} type="button">Pensiunkan</button></div><dl className="review-list"><div><dt>Parent</dt><dd>{selectedAgent.parent_agent_key ?? "Root Agent"}</dd></div><div><dt>Versi terbaru</dt><dd>{selectedVersion.semantic_version} · {selectedVersion.lifecycle_status}</dd></div><div><dt>Digest</dt><dd className="digest-value">{selectedVersion.digest}</dd></div><div><dt>Risk</dt><dd>{selectedAgent.risk_level}</dd></div></dl><h3>Riwayat versi</h3><div className="table-wrap"><table><thead><tr><th>Versi</th><th>Lifecycle</th><th>Digest</th></tr></thead><tbody>{selectedAgent.versions.map((version) => <tr key={version.agent_version_id}><td>{version.semantic_version}</td><td>{version.lifecycle_status}</td><td className="digest-value">{version.digest.slice(0, 16)}…</td></tr>)}</tbody></table></div><h3>Contract snapshot terbaru</h3><pre className="contract-snapshot">{JSON.stringify(selectedVersion.contract_snapshot, null, 2)}</pre></> : null}
          </article>

          <article className="panel runtime-test-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">H3 FIXTURE TEST RUN</p><h2>Jalankan DRAFT dengan aman</h2></div>
              <span className="permission-ok">IT Lead only</span>
            </div>
            {!selectedAgent || !selectedVersion ? <p className="empty-state">Pilih Agent DRAFT untuk menyiapkan fixture run Gate B.</p> : null}
            {selectedAgent && selectedVersion && selectedVersion.lifecycle_status !== "DRAFT" ? <p className="safe-note">Versi {selectedVersion.semantic_version} berstatus {selectedVersion.lifecycle_status}. Buat atau pilih DRAFT aktif untuk Test Run.</p> : null}
            {selectedAgent && selectedVersion?.lifecycle_status === "DRAFT" ? <>
              <p className="field-note">Mode ini hanya membaca fixture atau tool read-only yang sudah di-allowlist. Tidak ada perubahan data, side effect, API key, atau credential yang dikirim ke browser.</p>
              <div className="builder-fields two-column-fields runtime-test-fields">
                <label>Input fixture (JSON)<textarea className="code-input" onChange={(event) => setRunForm((current) => ({ ...current, input: event.target.value }))} rows={7} spellCheck="false" value={runForm.input} /></label>
                <label>Requested tool keys (pisahkan koma)<input onChange={(event) => setRunForm((current) => ({ ...current, requestedToolKeys: event.target.value }))} placeholder="Kosongkan bila Agent tidak membutuhkan tool" value={runForm.requestedToolKeys} /><span className="field-note">Tool di luar allowlist tetap BLOCKED dan dicatat pada audit.</span></label>
              </div>
              <div className="builder-actions"><button disabled={running} onClick={() => void runFixture()} type="button">{running ? "Menjalankan fixture…" : "Jalankan Fixture Test"}</button></div>
            </> : null}
            {latestRun ? <section className={`runtime-result runtime-${latestRun.status.toLowerCase()}`} aria-live="polite">
              <div><strong>{latestRun.status}</strong><span>{latestRun.agent_key} · {latestRun.semantic_version}</span></div>
              <dl className="review-list runtime-metrics"><div><dt>Correlation ID</dt><dd className="digest-value">{latestRun.correlation_id}</dd></div><div><dt>Provider / model</dt><dd>{latestRun.provider ?? "—"} / {latestRun.model ?? "—"}</dd></div><div><dt>Token</dt><dd>{latestRun.input_tokens ?? "—"} input · {latestRun.output_tokens ?? "—"} output</dd></div><div><dt>Latency / biaya</dt><dd>{latestRun.latency_milliseconds ?? "—"} ms · ${latestRun.estimated_cost_usd ?? "—"}</dd></div></dl>
              {latestRun.tool_decisions.length > 0 ? <ul className="tool-decisions">{latestRun.tool_decisions.map((decision) => <li key={`${decision.tool_key}-${decision.decision}`}><strong>{decision.decision}</strong> {decision.tool_key} — {decision.reason}</li>)}</ul> : null}
              {latestRun.output ? <pre className="contract-snapshot runtime-output">{JSON.stringify(latestRun.output, null, 2)}</pre> : null}
              {latestRun.error_code ? <p className="safe-note">Kode kontrol: {latestRun.error_code}</p> : null}
            </section> : null}
          </article>
        </section>
      </section>

      <section className="panel registry-audit-panel">
        <p className="eyebrow">GATE A & B EVIDENCE</p>
        <h2>Audit Agent pada workspace ini</h2>
        {data.audit.length === 0 ? <p className="empty-state">Belum ada Agent DRAFT atau fixture run yang diaudit pada workspace ini.</p> : null}
        <ol className="audit-list">{data.audit.map((event) => <li key={event.audit_event_id}><strong>{event.action}</strong><span>{event.reason}</span><time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time></li>)}</ol>
      </section>
    </main>
  );
}

async function loadFoundation(): Promise<RegistryFoundation> {
  const [actor, workspaces] = await Promise.all([
    api<SessionActor>("/api/v1/whoami"),
    api<Workspace[]>("/api/v1/workspaces"),
  ]);
  return { actor, workspaces };
}

function foundationOf(data: RegistryData): RegistryFoundation {
  return { actor: data.actor, workspaces: data.workspaces };
}

function handleApiError(error: unknown, setError: (message: string) => void, router: ReturnType<typeof useRouter>) {
  if (error instanceof ApiError && error.status === 401) {
    router.replace("/login");
  } else if (error instanceof ApiError && error.status === 403) {
    setError("Akun Anda tidak memiliki otoritas IT Lead atau akses ke workspace ini.");
  } else if (error instanceof ApiError && error.status === 409) {
    setError(registryConflictMessage(error.detail));
  } else {
    setError("Permintaan tidak dapat diproses. Periksa isian lalu coba lagi.");
  }
}

function handleRuntimeApiError(error: unknown, setError: (message: string) => void, router: ReturnType<typeof useRouter>) {
  if (error instanceof ApiError && error.status === 401) {
    router.replace("/login");
  } else if (error instanceof ApiError && error.status === 403) {
    setError("Akun Anda tidak memiliki otoritas IT Lead atau akses ke workspace ini.");
  } else if (error instanceof ApiError && error.status === 409) {
    setError(runtimeBlockedMessage(error.detail));
  } else {
    setError("Fixture Test tidak dapat diproses. Periksa input JSON lalu coba lagi.");
  }
}

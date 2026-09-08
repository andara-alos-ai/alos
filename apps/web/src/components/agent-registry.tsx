"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiRequest as api } from "@/lib/api-client";
import { GovernanceConfirmationModal, GovernanceFeedback, GovernanceNavigation, type Confirmation } from "@/components/governance-control-ui";
import { normalizeGovernanceError, type GovernanceUiError } from "@/lib/governance-errors";

import {
  agentBuilderSteps,
  canEditAgentRegistry,
  canReadAgentRegistry,
  draftPayloadFromForm,
  eligibleParents,
  emptyAgentDraftForm,
  emptyAgentRunForm,
  formFromAgent,
  latestVersion,
  runPayloadFromForm,
  type AgentDraftForm,
  type AgentDraftResult,
  type AgentRecord,
  type AgentRunForm,
  type AgentRunResult,
} from "@/lib/agent-registry";
import {
  formatDateTime,
  type AuditEvent,
  type Run,
  type SessionActor,
  type Workspace,
} from "@/lib/governance";

type RegistryData = {
  actor: SessionActor;
  workspaces: Workspace[];
  agents: AgentRecord[];
  audit: AuditEvent[];
  runs: Run[];
};

type RegistryFoundation = Pick<RegistryData, "actor" | "workspaces">;

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
  const [error, setError] = useState<GovernanceUiError | null>(null);
  const [notice, setNotice] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [agentTab, setAgentTab] = useState<"overview" | "contract" | "permissions" | "tests" | "release" | "runtime" | "audit">("overview");

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, base?: RegistryFoundation) => {
    const foundation = base ?? (await loadFoundation());
    const [agents, audit, runs] = await Promise.all([
      api<AgentRecord[]>(`/api/v1/agents?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
      loadRegistryAudit(selectedWorkspaceId),
      api<Run[]>(`/api/v1/workspaces/${encodeURIComponent(selectedWorkspaceId)}/runs?limit=100`),
    ]);
    setData({ ...foundation, agents, runs, audit: audit.filter((event) => event.action.startsWith("AGENT_") || event.action.includes("RELEASE") || event.action.includes("TEST_")) });
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (!canReadAgentRegistry(foundation.actor.roles)) {
          setForbidden(true);
          return;
        }
        if (foundation.workspaces.length === 0) {
          setError(uiError("Workspace belum tersedia", "Akun ini belum memiliki workspace aktif.", "Minta Administrator memberi akses workspace."));
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
        setError(normalizeGovernanceError(loadError));
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
  const visibleAgents = useMemo(() => data?.agents.filter((agent) => {
    const version = latestVersion(agent);
    const matchesQuery = `${agent.name} ${agent.agent_key}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (statusFilter === "ALL" || version?.lifecycle_status === statusFilter) && (riskFilter === "ALL" || agent.risk_level === riskFilter);
  }) ?? [], [data?.agents, query, riskFilter, statusFilter]);
  const mayEdit = canEditAgentRegistry(data?.actor.roles ?? []);
  const selectedRuns = data?.runs.filter((run) => run.agent_key === selectedAgentKey) ?? [];
  const selectedAudit = data?.audit.filter((event) => String(event.metadata?.agent_key ?? "") === selectedAgentKey) ?? [];
  const agentKeyValid = /^[A-Z][A-Z0-9_]{2,79}$/.test(form.agentKey.trim().toUpperCase());
  const objectiveValid = form.objective.trim().length >= 20;
  const inputSchemaError = jsonObjectFieldError(form.inputSchema);
  const outputSchemaError = jsonObjectFieldError(form.outputSchema);
  const draftFormValid = agentKeyValid && form.name.trim().length > 0 && objectiveValid && !inputSchemaError && !outputSchemaError;

  function changeForm<Key extends keyof AgentDraftForm>(key: Key, value: AgentDraftForm[Key]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setLoading(true);
    setError(null);
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
    setError(null);
    setNotice("");
  }

  function startEdit(agent: AgentRecord) {
    const version = latestVersion(agent);
    if (!version || version.lifecycle_status !== "DRAFT") {
      setError(uiError("Agent tidak dapat diedit", "Versi yang dipilih bukan DRAFT.", "Gunakan Create New Version agar versi aktif dan historical tetap immutable."));
      return;
    }
    setEditingAgentKey(agent.agent_key);
    setSelectedAgentKey(agent.agent_key);
    setForm(formFromAgent(agent));
    setLatestRun(null);
    setActiveStep(0);
    setError(null);
    setNotice("");
  }

  function startSuccessor(agent: AgentRecord) {
    setEditingAgentKey(agent.agent_key);
    setSelectedAgentKey(agent.agent_key);
    setForm(formFromAgent(agent));
    setActiveStep(0);
    setError(null);
    setNotice(`Versi ${latestVersion(agent)?.semantic_version} tetap immutable. Perubahan akan disimpan sebagai versi DRAFT baru.`);
  }

  function selectAgent(agent: AgentRecord) {
    const version = latestVersion(agent);
    setSelectedAgentKey(agent.agent_key);
    setAgentTab("overview");
    setRunForm({
      input: "{}",
      requestedToolKeys: version?.contract_snapshot.tool_keys.join(", ") ?? "",
    });
    setLatestRun(null);
    setError(null);
    setNotice("");
  }

  async function runFixture() {
    if (!data || !selectedAgent || !selectedVersion || !workspaceId) {
      return;
    }
    if (selectedVersion.lifecycle_status !== "DRAFT") {
      setError(uiError("Fixture tidak dapat dijalankan", "Versi yang dipilih bukan DRAFT.", "Buka Runtime untuk history atau buat versi DRAFT baru untuk pengujian."));
      return;
    }
    setRunning(true);
    setError(null);
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
        setError(normalizeGovernanceError(runError));
      } else {
        if (runError instanceof ApiError && runError.status === 409) await loadWorkspace(workspaceId, foundationOf(data));
        handleApiError(runError, setError, router);
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
    setError(null);
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
        setError(normalizeGovernanceError(saveError));
      } else {
        if (saveError instanceof ApiError && saveError.status === 409) await loadWorkspace(workspaceId, foundationOf(data));
        handleApiError(saveError, setError, router);
      }
    } finally {
      setSaving(false);
    }
  }

  function retire(agent: AgentRecord) {
    setConfirmation({
      title: "Delete Agent Draft?",
      impact: `Draft ${agent.agent_key} akan dihapus. Jika sudah memiliki Test Run, release, runtime, permission review, atau evidence immutable, backend akan memblokir penghapusan.`,
      confirmLabel: "Delete Draft",
      destructive: true,
      onConfirm: () => { setConfirmation(null); void performDeleteDraft(agent); },
    });
  }

  async function performDeleteDraft(agent: AgentRecord) {
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await api(`/api/v1/agents/${encodeURIComponent(agent.agent_key)}/draft`, {
        method: "DELETE",
      });
      if (data) {
        await loadWorkspace(workspaceId, foundationOf(data));
      }
      setSelectedAgentKey("");
      setNotice(`Agent DRAFT ${agent.agent_key} berhasil dihapus. Immutable governance evidence tidak terpengaruh.`);
    } catch (retireError: unknown) {
      if (retireError instanceof ApiError && retireError.status === 409 && data) await loadWorkspace(workspaceId, foundationOf(data));
      handleApiError(retireError, setError, router);
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    try {
      await api<void>("/api/v1/auth/logout", { method: "POST" });
      window.location.assign(new URL("/login", window.location.origin).href);
    } catch (logoutError: unknown) {
      setError(normalizeGovernanceError(logoutError));
    }
  }

  if (loading && !data && !forbidden) {
    return <main className="loading-shell">Memuat Agent Registry…</main>;
  }

  if (forbidden) {
    return (
      <main className="access-denied-shell">
        <p className="eyebrow">ALOS / AGENT REGISTRY</p>
        <h1>Akses Agent Control tidak tersedia</h1>
        <p>Registry hanya dapat dibaca oleh role Governance yang berwenang dan hanya dapat diubah oleh IT Lead.</p>
        <Link className="secondary-button button-link" href="/governance">Kembali ke Governance Dashboard</Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="loading-shell">
        <GovernanceFeedback error={error} notice="" />
        {!error ? <p>Sesi Registry tidak tersedia.</p> : null}
        <Link className="text-link" href="/login">Ke halaman login</Link>
      </main>
    );
  }

  return (
    <main className="registry-shell">
      <header className="dashboard-header registry-header">
        <div>
          <p className="eyebrow">ALOS / AGENT REGISTRY</p>
          <h1>Agent Registry</h1>
          <p className="muted">Kontrak terversi, hierarki terbatas, dan audit append-only. Semua hasil Builder tetap DRAFT.</p>
        </div>
        <div className="header-actions">
          <span className="role-badge">{data.actor.roles.join(" · ")}</span>
          <Link className="secondary-button button-link" href="/governance">Governance</Link>
          <Link className="secondary-button button-link" href="/releases">Release</Link>
          <button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button>
        </div>
      </header>

      <GovernanceNavigation active="agents" />

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

      <GovernanceFeedback error={error} notice={notice} onDismiss={() => setError(null)} />

      <section className="registry-layout">
        <aside className="panel registry-list-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">REGISTERED AGENTS</p><h2>{visibleAgents.length} / {data.agents.length} Agent</h2></div>
            {mayEdit ? <button onClick={startNewDraft} type="button">+ DRAFT</button> : <span className="permission-readonly">Read-only</span>}
          </div>
          <div className="registry-filters"><label>Cari Agent<input onChange={(event) => setQuery(event.target.value)} placeholder="Nama atau agent key" value={query} /></label><label>Status<select onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="ALL">Semua status</option>{["DRAFT", "TESTED", "IN_REVIEW", "APPROVED", "RELEASED", "ACTIVE", "SUSPENDED", "ROLLED_BACK", "RETURNED", "REJECTED", "RETIRED"].map((status) => <option key={status}>{status}</option>)}</select></label><label>Risk<select onChange={(event) => setRiskFilter(event.target.value)} value={riskFilter}><option value="ALL">Semua risk</option>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((risk) => <option key={risk}>{risk}</option>)}</select></label></div>
          {data.agents.length === 0 ? <p className="empty-state">Belum ada Agent di workspace ini. Buat Agent melalui GENESIS untuk memulai.</p> : null}
          {data.agents.length > 0 && visibleAgents.length === 0 ? <p className="empty-state">Tidak ada Agent yang cocok dengan pencarian atau filter.</p> : null}
          <div className="table-wrap agent-control-table"><table><thead><tr><th>Agent</th><th>Version</th><th>Purpose</th><th>Scope</th><th>Risk</th><th>Lifecycle</th><th>Owner</th><th>Last Run</th><th>Updated</th><th>Actions</th></tr></thead><tbody>{visibleAgents.map((agent) => {
            const version = latestVersion(agent); const lastRun = data.runs.find((run) => run.agent_key === agent.agent_key);
            return <tr className={selectedAgentKey === agent.agent_key ? "selected-row" : ""} key={agent.agent_contract_id}><td><button className="table-agent-link" onClick={() => selectAgent(agent)} type="button"><strong>{agent.name}</strong><small>{agent.agent_key}</small></button></td><td>{version?.semantic_version ?? "—"}</td><td>{version?.contract_snapshot.purpose.slice(0, 72) ?? "—"}</td><td>{data.workspaces.find((workspace) => workspace.workspace_id === agent.workspace_id)?.division_code ?? "COMPANY"}</td><td>{agent.risk_level}</td><td><span className={`lifecycle-pill lifecycle-${(version?.lifecycle_status ?? "DRAFT").toLowerCase()}`}>{version?.lifecycle_status ?? "DRAFT"}</span></td><td>{version?.contract_snapshot.owner_user_id.slice(0, 8) ?? "—"}</td><td>{lastRun ? <>{lastRun.status}<br /><small>{formatDateTime(lastRun.created_at)}</small></> : "Belum ada"}</td><td>{agent.updated_at ? formatDateTime(agent.updated_at) : "—"}</td><td><details className="action-menu"><summary aria-label={`Aksi ${agent.agent_key}`}>•••</summary><div><button onClick={() => selectAgent(agent)} type="button">View Detail</button>{mayEdit && version?.lifecycle_status === "DRAFT" ? <button onClick={() => startEdit(agent)} type="button">Edit Draft</button> : null}{mayEdit && version?.lifecycle_status === "DRAFT" ? <button className="danger-text" onClick={() => retire(agent)} type="button">Delete Draft</button> : null}{mayEdit && ["ACTIVE", "RELEASED", "APPROVED"].includes(version?.lifecycle_status ?? "") ? <button onClick={() => startSuccessor(agent)} type="button">Create New Version</button> : null}</div></details></td></tr>;
          })}</tbody></table></div>
        </aside>

        <section className="registry-content">
          {mayEdit ? <article className="panel builder-panel">
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
                <label>Agent key<input aria-invalid={!agentKeyValid} disabled={Boolean(editingAgentKey)} onChange={(event) => changeForm("agentKey", event.target.value)} placeholder="PROPERTY_DAILY_BRIEF" value={form.agentKey} />{!agentKeyValid ? <span className="field-error">Gunakan huruf kapital, angka, dan underscore. Contoh: EVIDENCE_CHECKER</span> : null}</label>
                <label>Nama Agent<input onChange={(event) => changeForm("name", event.target.value)} placeholder="Property Daily Brief" value={form.name} /></label>
                <label>Parent Agent<select onChange={(event) => changeForm("parentAgentKey", event.target.value)} value={form.parentAgentKey}><option value="">Root Agent · level 0</option>{parentOptions.map((agent) => <option key={agent.agent_key} value={agent.agent_key}>{agent.agent_key} · level {agent.agent_level + 1}</option>)}</select></label>
                <p className="field-note">Hierarki dibatasi sampai level 2; validasi parent dan circular reference tetap dilakukan oleh PostgreSQL.</p>
              </div>
            ) : null}

            {activeStep === 1 ? <div className="builder-fields"><label>Tujuan operasional<textarea aria-invalid={!objectiveValid} minLength={20} onChange={(event) => changeForm("objective", event.target.value)} placeholder="Jelaskan pekerjaan read-only dan outcome yang diharapkan…" rows={6} value={form.objective} />{!objectiveValid ? <span className="field-error">Tujuan Agent minimal 20 karakter.</span> : null}</label><p className="field-note">Genesis mengompilasi purpose, prompt, dan evidence secara deterministik. Ia tidak dapat menentukan risk, tools, permission, owner, atau approval.</p></div> : null}

            {activeStep === 2 ? <div className="builder-fields two-column-fields"><label>Input schema (JSON)<textarea aria-invalid={Boolean(inputSchemaError)} className="code-input" onChange={(event) => changeForm("inputSchema", event.target.value)} rows={10} spellCheck="false" value={form.inputSchema} />{inputSchemaError ? <span className="field-error">{inputSchemaError}</span> : null}</label><label>Output schema (JSON)<textarea aria-invalid={Boolean(outputSchemaError)} className="code-input" onChange={(event) => changeForm("outputSchema", event.target.value)} rows={10} spellCheck="false" value={form.outputSchema} />{outputSchemaError ? <span className="field-error">{outputSchemaError}</span> : null}</label></div> : null}

            {activeStep === 3 ? <div className="builder-fields two-column-fields"><label>Tool keys (pisahkan koma)<input onChange={(event) => changeForm("toolKeys", event.target.value)} placeholder="SOURCE_REGISTRY_SEARCH" value={form.toolKeys} /></label><label>Permission keys (pisahkan koma)<input onChange={(event) => changeForm("permissionKeys", event.target.value)} placeholder="SOURCE_READ_INTERNAL" value={form.permissionKeys} /></label><label>KPI (array JSON)<textarea className="code-input" onChange={(event) => changeForm("kpis", event.target.value)} rows={6} spellCheck="false" value={form.kpis} /></label><p className="field-note">Tool dan izin adalah kontrol manusia. Kosongkan bila Agent tidak membutuhkan akses eksternal atau data terdaftar.</p></div> : null}

            {activeStep === 4 ? <div className="builder-fields two-column-fields"><label>Risk level<select onChange={(event) => changeForm("riskLevel", event.target.value as AgentDraftForm["riskLevel"])} value={form.riskLevel}><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option></select></label><label>Data classification<select onChange={(event) => changeForm("dataClassification", event.target.value as AgentDraftForm["dataClassification"])} value={form.dataClassification}><option value="PUBLIC">PUBLIC</option><option value="INTERNAL">INTERNAL</option><option value="CONFIDENTIAL">CONFIDENTIAL</option><option value="RESTRICTED">RESTRICTED</option></select></label><label>Timeout (detik)<input max="3600" min="1" onChange={(event) => changeForm("timeoutSeconds", event.target.value)} type="number" value={form.timeoutSeconds} /></label><label className="checkbox-field"><input checked={form.approvalRequired} onChange={(event) => changeForm("approvalRequired", event.target.checked)} type="checkbox" />Memerlukan persetujuan manusia</label><label className="full-width">Forbidden actions (satu per baris)<textarea onChange={(event) => changeForm("forbiddenActions", event.target.value)} rows={5} value={form.forbiddenActions} /></label></div> : null}

            {activeStep === 5 ? <div className="builder-review"><p>Prompt dan evidence requirement dikompilasi Genesis secara lokal dari tujuan serta forbidden actions. Pembuatan DRAFT tidak memanggil provider dan tidak mengonsumsi limit Model Gateway.</p><dl className="review-list"><div><dt>Agent</dt><dd>{form.agentKey || "Belum diisi"}</dd></div><div><dt>Risk</dt><dd>{form.riskLevel} · {form.approvalRequired ? "approval wajib" : "tanpa approval"}</dd></div><div><dt>Lifecycle</dt><dd>DRAFT saja</dd></div><div><dt>Versi</dt><dd>{editingAgentKey ? "Versi baru 0.x.0" : "0.1.0"}</dd></div></dl><p className="safe-note">Menyimpan akan menulis audit append-only. DRAFT tidak menjalankan Agent dan tidak dapat mengubah data produksi.</p></div> : null}

            <div className="builder-actions"><button className="secondary-button" disabled={activeStep === 0 || saving} onClick={() => setActiveStep((step) => step - 1)} type="button">Kembali</button>{activeStep < agentBuilderSteps.length - 1 ? <button disabled={saving} onClick={() => setActiveStep((step) => step + 1)} type="button">Lanjut</button> : <button disabled={saving || !draftFormValid} onClick={() => void saveDraft()} type="button">{saving ? "Menyimpan…" : editingAgentKey ? "Simpan versi DRAFT & audit" : "Buat DRAFT & audit"}</button>}</div>
          </article> : null}

          <article className="panel agent-detail-panel">
            <div className="panel-heading"><div><p className="eyebrow">CONTRACT & VERSION</p><h2>{selectedAgent ? selectedAgent.name : "Pilih Agent"}</h2></div>{selectedAgent ? <span className="role-badge">Level {selectedAgent.agent_level}</span> : null}</div>
            {!selectedAgent ? <p className="empty-state">Pilih Agent dari daftar untuk melihat Contract, versi, dan prompt hasil Genesis.</p> : null}
            {selectedAgent && selectedVersion ? <>
              <dl className="status-guidance"><div><dt>CURRENT STATE</dt><dd>{selectedVersion.lifecycle_status}</dd></div><div><dt>CURRENT BLOCKER</dt><dd>{agentGuidance(selectedVersion.lifecycle_status).blocker}</dd></div><div><dt>NEXT REQUIRED ACTION</dt><dd>{agentGuidance(selectedVersion.lifecycle_status).action}</dd></div><div><dt>NEXT ACTOR</dt><dd>{agentGuidance(selectedVersion.lifecycle_status).actor}</dd></div></dl>
              <div className="agent-detail-actions">{mayEdit && selectedVersion.lifecycle_status === "DRAFT" ? <><button disabled={saving} onClick={() => startEdit(selectedAgent)} type="button">Edit Draft</button><button className="danger-button" disabled={saving} onClick={() => retire(selectedAgent)} type="button">Delete Draft</button></> : null}{mayEdit && ["APPROVED", "RELEASED", "ACTIVE", "SUSPENDED", "ROLLED_BACK"].includes(selectedVersion.lifecycle_status) ? <button onClick={() => startSuccessor(selectedAgent)} type="button">Create New Version</button> : null}</div>
              <nav className="agent-detail-tabs" aria-label="Detail Agent">{(["overview", "contract", "permissions", "tests", "release", "runtime", "audit"] as const).map((tab) => <button className={agentTab === tab ? "active" : ""} key={tab} onClick={() => setAgentTab(tab)} type="button">{{ overview: "Overview", contract: "Contract", permissions: "Tools & Permissions", tests: "Tests", release: "Release", runtime: "Runtime", audit: "Audit" }[tab]}</button>)}</nav>
              {agentTab === "overview" ? <><dl className="review-list"><div><dt>Agent key</dt><dd>{selectedAgent.agent_key}</dd></div><div><dt>Purpose</dt><dd>{selectedVersion.contract_snapshot.purpose}</dd></div><div><dt>Scope</dt><dd>{data.workspaces.find((workspace) => workspace.workspace_id === selectedAgent.workspace_id)?.division_code ?? "COMPANY"}</dd></div><div><dt>Parent</dt><dd>{selectedAgent.parent_agent_key ?? "Root Agent"}</dd></div><div><dt>Risk</dt><dd>{selectedAgent.risk_level}</dd></div><div><dt>Owner</dt><dd>{selectedVersion.contract_snapshot.owner_user_id}</dd></div></dl><div className="table-wrap"><table><thead><tr><th>Version</th><th>Lifecycle</th><th>Created</th><th>Digest</th></tr></thead><tbody>{selectedAgent.versions.map((version) => <tr key={version.agent_version_id}><td>{version.semantic_version}</td><td>{version.lifecycle_status}</td><td>{version.created_at ? formatDateTime(version.created_at) : "—"}</td><td className="digest-value">{version.digest.slice(0, 16)}…</td></tr>)}</tbody></table></div></> : null}
              {agentTab === "contract" ? <pre className="contract-snapshot">{JSON.stringify(selectedVersion.contract_snapshot, null, 2)}</pre> : null}
              {agentTab === "permissions" ? <><dl className="review-list"><div><dt>Tool allowlist</dt><dd>{selectedVersion.contract_snapshot.tool_keys.join(", ") || "Tidak ada tool"}</dd></div><div><dt>Permission keys</dt><dd>{selectedVersion.contract_snapshot.permission_keys.join(", ") || "Tidak ada permission"}</dd></div><div><dt>Forbidden actions</dt><dd>{selectedVersion.contract_snapshot.forbidden_actions.join(" · ")}</dd></div><div><dt>Evidence requirements</dt><dd>{selectedVersion.contract_snapshot.evidence_requirements.join(" · ") || "Belum ditentukan"}</dd></div></dl><p className="safe-note">Contract tidak otomatis memberi permission. Status approval ada di Governance → Permissions.</p></> : null}
              {agentTab === "tests" ? <p className="empty-state">Test case dan immutable Test Run Evidence dikelola pada <Link href="/releases?view=tests">Test &amp; Evidence</Link>.</p> : null}
              {agentTab === "release" ? <p className="empty-state">Review lifecycle dan action yang tersedia pada <Link href="/releases?view=request">Release Requests</Link>.</p> : null}
              {agentTab === "runtime" ? selectedRuns.length ? <div className="table-wrap"><table><thead><tr><th>Run ID</th><th>Status</th><th>Version</th><th>Provider / Model</th><th>Timestamp</th></tr></thead><tbody>{selectedRuns.map((run) => <tr key={run.agent_run_id}><td>{run.agent_run_id.slice(0, 8)}</td><td>{run.status}</td><td>{run.semantic_version}</td><td>{run.provider ?? "—"} / {run.model ?? "—"}</td><td>{formatDateTime(run.created_at)}</td></tr>)}</tbody></table></div> : <p className="empty-state">Belum ada Agent Run. Jalankan Test atau Agent untuk melihat runtime activity.</p> : null}
              {agentTab === "audit" ? selectedAudit.length ? <ol className="audit-list">{selectedAudit.map((event) => <li key={event.audit_event_id}><strong>{event.action}</strong><span>{event.reason}</span><code>{event.correlation_id ?? "—"}</code><time>{formatDateTime(event.occurred_at)}</time></li>)}</ol> : <p className="empty-state">Belum ada audit event yang terindeks untuk Agent ini.</p> : null}
            </> : null}
          </article>

          {mayEdit ? <article className="panel runtime-test-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">BOUNDED DRAFT TEST</p><h2>Jalankan DRAFT dengan aman</h2></div>
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
          </article> : null}
        </section>
      </section>

      <section className="panel registry-audit-panel">
        <p className="eyebrow">GATE A & B EVIDENCE</p>
        <h2>Audit Agent pada workspace ini</h2>
        {data.audit.length === 0 ? <p className="empty-state">Belum ada Agent DRAFT atau fixture run yang diaudit pada workspace ini.</p> : null}
        <ol className="audit-list">{data.audit.map((event) => <li key={event.audit_event_id}><strong>{event.action}</strong><span>{event.reason}</span><time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time></li>)}</ol>
      </section>
      <GovernanceConfirmationModal busy={saving} confirmation={confirmation} onCancel={() => setConfirmation(null)} />
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

async function loadRegistryAudit(workspaceId: string): Promise<AuditEvent[]> {
  try { return await api<AuditEvent[]>(`/api/v1/audit-events?workspace_id=${encodeURIComponent(workspaceId)}&limit=100`); }
  catch (error: unknown) { if (error instanceof ApiError && error.status === 403) return []; throw error; }
}

function agentGuidance(state: string): { blocker: string; action: string; actor: string } {
  const guidance: Record<string, { blocker: string; action: string; actor: string }> = {
    DRAFT: { blocker: "Required test evidence dan review belum lengkap.", action: "Kelola dan jalankan lima kategori test.", actor: "Release Maker / QA Checker" },
    TESTED: { blocker: "Business dan Technical Review belum lengkap.", action: "Submit atau lanjutkan review manusia.", actor: "Business & Technical Reviewer" },
    IN_REVIEW: { blocker: "Review independen atau Director Approval masih pending.", action: "Selesaikan gate review sesuai scope.", actor: "Reviewer / Director" },
    APPROVED: { blocker: "Versi belum dirilis.", action: "Release versi yang telah disetujui.", actor: "Director tercatat" },
    RELEASED: { blocker: "Versi belum ACTIVE dan readiness runtime tetap diperiksa backend.", action: "Activate setelah permission, tool, budget, dan kill switch siap.", actor: "Director tercatat" },
    ACTIVE: { blocker: "Tidak ada blocker lifecycle. Contract aktif immutable.", action: "Pantau Runtime; buat versi DRAFT baru untuk perubahan.", actor: "Operations / IT Lead" },
    SUSPENDED: { blocker: "Agent dihentikan dan tidak menerima run baru.", action: "Tinjau alasan, kill switch, dan rollback target.", actor: "Director / IT Lead" },
    ROLLED_BACK: { blocker: "Versi ini merupakan historical rollback evidence.", action: "Buat versi DRAFT baru bila ada perubahan.", actor: "Release Maker" },
    RETIRED: { blocker: "Agent dipensiunkan.", action: "Riwayat tetap read-only.", actor: "Governance owner" },
  };
  return guidance[state] ?? { blocker: `Lifecycle ${state} tidak dapat dimutasi dari Registry.`, action: "Buka Release Governance untuk tindakan berikutnya.", actor: "Governance owner" };
}

function jsonObjectFieldError(value: string): string {
  try { const parsed: unknown = JSON.parse(value); return parsed && !Array.isArray(parsed) && typeof parsed === "object" ? "" : "JSON harus berupa object."; }
  catch { return "JSON tidak valid. Periksa quote, koma, dan bracket."; }
}

function foundationOf(data: RegistryData): RegistryFoundation {
  return { actor: data.actor, workspaces: data.workspaces };
}

function uiError(title: string, reason: string, nextAction: string): GovernanceUiError {
  return { title, reason, nextAction, severity: "warning", status: null, correlationId: null };
}

function handleApiError(error: unknown, setError: (message: GovernanceUiError | null) => void, router: ReturnType<typeof useRouter>) {
  if (error instanceof ApiError && error.status === 401) {
    router.replace("/login");
  }
  setError(normalizeGovernanceError(error));
}

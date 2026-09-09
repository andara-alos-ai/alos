"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiRequest as api } from "@/lib/api-client";
import { GovernanceFeedback, GovernanceNavigation } from "@/components/governance-control-ui";
import { normalizeGovernanceError, type GovernanceUiError } from "@/lib/governance-errors";
import type { ReleaseRequest } from "@/lib/release-governance";
import type { AgentRecord } from "@/lib/agent-registry";
import { runtimeNextAction } from "@/lib/governance-errors";

import { formatRoleLabel } from "@/lib/dashboard-access";
import {
  type AuditEvent,
  type Budget,
  canChangeBudget,
  formatCurrency,
  formatDateTime,
  formatInteger,
  type ModelPolicy,
  type Run,
  type SessionActor,
  type Usage,
  type Workspace,
} from "@/lib/governance";

type DashboardData = {
  actor: SessionActor;
  workspaces: Workspace[];
  policy: ModelPolicy;
  budget: Budget;
  usage: Usage;
  runs: Run[];
  audit: AuditEvent[];
  auditRestricted: boolean;
  releases: ReleaseRequest[];
  agents: AgentRecord[];
  permissions: PermissionPolicy[];
  tools: ToolRecord[];
};

type PermissionPolicy = { permission_policy_id: string; agent_version_id: string; permission_key: string; effect: string; capability_key: string | null; tool_key: string | null; access_mode: string; resource_type: string; division_scope: string | null; lifecycle_status: string; approved_by_user_id: string | null };
type ToolRecord = { tool_definition_id: string; tool_key: string; name: string; risk_level: string; lifecycle_status: string; manifest: Record<string, unknown> };

type Foundation = Pick<DashboardData, "actor" | "workspaces" | "policy">;

export function GovernanceDashboard() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [error, setError] = useState<GovernanceUiError | null>(null);
  const [notice, setNotice] = useState("");
  const [view, setView] = useState<"overview" | "permissions" | "runtime" | "budget" | "audit">("overview");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ requests: "", tokens: "", cost: "" });
  const [runtimeFilter, setRuntimeFilter] = useState({ agent: "", status: "", date: "" });
  const [auditFilter, setAuditFilter] = useState({ agent: "", actor: "", action: "", correlation: "", date: "" });

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, base?: Foundation) => {
    const foundation = base ?? (await loadFoundation());
    const [budget, usage, runs, auditResult, releases, agents, permissions, tools] = await Promise.all([
      api<Budget>(`/api/v1/workspaces/${selectedWorkspaceId}/budget`),
      api<Usage>(`/api/v1/workspaces/${selectedWorkspaceId}/usage/daily`),
      api<Run[]>(`/api/v1/workspaces/${selectedWorkspaceId}/runs?limit=12`),
      loadAudit(selectedWorkspaceId),
      api<ReleaseRequest[]>(`/api/v1/release-requests?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
      api<AgentRecord[]>(`/api/v1/agents?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
      api<PermissionPolicy[]>(`/api/v1/permission-policies?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
      api<ToolRecord[]>("/api/v1/tools"),
    ]);
    setData({ ...foundation, budget, usage, runs, releases, agents, permissions: permissions.filter((permission) => permission.agent_version_id && agents.some((agent) => agent.versions.some((version) => version.agent_version_id === permission.agent_version_id))), tools, ...auditResult });
    setForm({
      requests: String(budget.daily_request_limit),
      tokens: String(budget.daily_output_token_limit),
      cost: String(budget.daily_cost_cap_usd),
    });
  }, []);

  useEffect(() => {
    const viewTimer = window.setTimeout(() => {
      const requested = new URLSearchParams(window.location.search).get("view");
      if (["overview", "permissions", "runtime", "budget", "audit"].includes(requested ?? "")) setView(requested as "overview" | "permissions" | "runtime" | "budget" | "audit");
    }, 0);
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (foundation.workspaces.length === 0) {
          setError({ title: "Workspace belum tersedia", reason: "Akun ini belum memiliki workspace aktif.", nextAction: "Minta Administrator memberi akses workspace.", severity: "warning", status: null, correlationId: null });
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
        setError(normalizeGovernanceError(loadError));
      } finally {
        setLoading(false);
      }
    }
    void initialize();
    return () => window.clearTimeout(viewTimer);
  }, [loadWorkspace, router]);

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setLoading(true);
    setError(null);
    try {
      await loadWorkspace(nextWorkspaceId, data ? foundationOf(data) : undefined);
    } catch (loadError: unknown) {
      if (loadError instanceof ApiError && loadError.status === 401) {
        router.replace("/login");
      } else {
        setError(normalizeGovernanceError(loadError));
      }
    } finally {
      setLoading(false);
    }
  }

  async function saveBudget() {
    if (!data || !canChangeBudget(data.actor.roles)) {
      return;
    }
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await api<Budget>(`/api/v1/workspaces/${workspaceId}/budget`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          daily_request_limit: Number(form.requests),
          daily_output_token_limit: Number(form.tokens),
          daily_cost_cap_usd: form.cost,
        }),
      });
      await loadWorkspace(workspaceId, foundationOf(data));
      setNotice("Limit workspace tersimpan dan perubahan dicatat pada audit trail.");
    } catch (saveError: unknown) {
      if (saveError instanceof ApiError && saveError.status === 401) {
        router.replace("/login");
      } else if (saveError instanceof ApiError && saveError.status === 403) {
        setError(normalizeGovernanceError(saveError));
      } else {
        setError(normalizeGovernanceError(saveError));
      }
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

  if (loading && !data) {
    return <main className="loading-shell">Memuat Governance Dashboard…</main>;
  }
  if (!data) {
    return (
      <main className="loading-shell">
        <GovernanceFeedback error={error} notice="" />
        <div className="builder-actions">
          <button className="secondary-button" onClick={() => window.location.reload()} type="button">Coba lagi</button>
          <Link className="text-link" href="/">Kembali ke ALOS</Link>
        </div>
      </main>
    );
  }

  const mayChange = canChangeBudget(data.actor.roles);
  const latestRun = data.runs[0];
  const pendingReviews = data.releases.filter((release) => ["TESTED", "IN_REVIEW", "APPROVED"].includes(release.state)).length;
  const actionableReleases = data.releases.filter((release) => {
    if (data.actor.roles.some((role) => ["QA_SECURITY", "TECHNICAL_REVIEWER"].includes(role)) && ["DRAFT", "RETURNED"].includes(release.state)) return true;
    if (data.actor.roles.some((role) => ["BUSINESS_REVIEWER", "TECHNICAL_REVIEWER"].includes(role)) && release.state === "IN_REVIEW") return true;
    if (data.actor.roles.includes("DIRECTOR") && ["IN_REVIEW", "APPROVED", "RELEASED"].includes(release.state)) return true;
    return data.actor.roles.includes("IT_LEAD") && release.state === "DRAFT";
  });
  const activeAgents = new Set(data.releases.filter((release) => release.state === "ACTIVE").map((release) => release.agent_key)).size;
  const suspendedAgents = new Set(data.releases.filter((release) => release.state === "SUSPENDED").map((release) => release.agent_key)).size;
  const failedRuns = data.runs.filter((run) => run.status === "FAILED").length;
  const failedTests = data.releases.reduce((total, release) => total + (release.failed_test_count ?? 0), 0);
  const blockedRuns = data.runs.filter((run) => run.status === "BLOCKED").length;
  const budgetPercent = Math.min(100, Math.round((Number(data.usage.estimated_cost_usd) / Math.max(Number(data.budget.daily_cost_cap_usd), 0.0001)) * 100));
  const budgetValidation = {
    requests: Number.isInteger(Number(form.requests)) && Number(form.requests) > 0,
    tokens: Number.isInteger(Number(form.tokens)) && Number(form.tokens) >= 1000,
    cost: Number.isFinite(Number(form.cost)) && Number(form.cost) >= 0,
  };
  const budgetFormValid = Object.values(budgetValidation).every(Boolean);
  const latestByAgent = new Map(data.agents.map((agent) => [agent.agent_key, agent.versions[0]?.lifecycle_status ?? "DRAFT"]));
  const draftAgents = [...latestByAgent.values()].filter((state) => state === "DRAFT").length;
  const inReviewAgents = new Set(data.releases.filter((release) => ["TESTED", "IN_REVIEW"].includes(release.state)).map((release) => release.agent_key)).size;
  const activeKillSwitch = data.releases.filter((release) => release.kill_switch_active).length;
  const visibleRuns = data.runs.filter((run) => (!runtimeFilter.agent || run.agent_key === runtimeFilter.agent) && (!runtimeFilter.status || run.status === runtimeFilter.status) && (!runtimeFilter.date || run.created_at.slice(0, 10) === runtimeFilter.date));
  const visibleAudit = data.audit.filter((event) => (!auditFilter.agent || String(event.metadata?.agent_key ?? "").toLowerCase().includes(auditFilter.agent.toLowerCase())) && (!auditFilter.actor || `${event.actor_user_id ?? ""} ${event.system_actor ?? ""}`.toLowerCase().includes(auditFilter.actor.toLowerCase())) && (!auditFilter.action || event.action.toLowerCase().includes(auditFilter.action.toLowerCase())) && (!auditFilter.correlation || (event.correlation_id ?? "").toLowerCase().includes(auditFilter.correlation.toLowerCase())) && (!auditFilter.date || event.occurred_at.slice(0, 10) === auditFilter.date));

  function changeView(nextView: typeof view) { setView(nextView); window.history.replaceState(null, "", `/governance?view=${nextView}`); }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">ALOS / GOVERNANCE</p>
          <h1>Governance &amp; Agent Control</h1>
          <p className="muted">Area kontrol untuk manusia berwenang. GENESIS adalah system actor, bukan akun pengguna atau approver.</p>
        </div>
        <div className="header-actions">
          <span className="role-badge">{formatRoleLabel(data.actor.roles)}</span>
          {data.actor.roles.includes("IT_LEAD") ? <Link className="secondary-button button-link" href="/agents">Agent Registry</Link> : null}
          {data.actor.roles.some((role) => ["DIRECTOR", "IT_LEAD", "QA_SECURITY"].includes(role)) ? <Link className="secondary-button button-link" href="/validation">Source Vault &amp; UAT</Link> : null}
          <Link className="secondary-button button-link" href="/releases">Release</Link>
          <button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button>
        </div>
      </header>

      <GovernanceNavigation active="overview" />
      <nav className="governance-subnav" aria-label="Area kontrol governance">
        {(["overview", "permissions", "runtime", "budget", "audit"] as const).map((item) => <button aria-current={view === item ? "page" : undefined} className={view === item ? "active" : ""} key={item} onClick={() => changeView(item)} type="button">{{ overview: "Overview", permissions: "Permissions", runtime: "Runtime & Monitoring", budget: "Budget", audit: "Audit Trail" }[item]}</button>)}
      </nav>

      <section className="workspace-bar" aria-label="Pemilihan workspace">
        <div>
          <label htmlFor="workspace">Workspace aktif</label>
          <select
            id="workspace"
            onChange={(event) => void selectWorkspace(event.target.value)}
            value={workspaceId}
          >
            {data.workspaces.map((workspace) => (
              <option key={workspace.workspace_id} value={workspace.workspace_id}>
                {workspace.name} · {workspace.workspace_key}
              </option>
            ))}
          </select>
        </div>
        <p>Perubahan limit dicatat pada audit trail dan tidak dapat mengakses API key.</p>
      </section>

      <GovernanceFeedback error={error} notice={notice} onDismiss={() => setError(null)} />

      {view === "overview" ? <>
        <section className="metric-grid governance-overview-metrics" aria-label="Ringkasan Governance">
          <Metric label="Total Agents" value={formatInteger(data.agents.length)} detail="Registry workspace" />
          <Metric label="Draft" value={formatInteger(draftAgents)} detail="Masih dapat diedit" />
          <Metric label="In Review" value={formatInteger(inReviewAgents)} detail="Contract immutable" />
          <Metric label="Active" value={formatInteger(activeAgents)} detail="Runtime eligible" />
          <Metric label="Suspended" value={formatInteger(suspendedAgents)} detail="Run baru dihentikan" />
          <Metric label="Pending Reviews" value={formatInteger(pendingReviews)} detail="Tindakan manusia" />
          <Metric label="Failed Tests" value={formatInteger(failedTests)} detail="Hasil terbaru FAILED / ERROR" />
          <Metric label="Blocked Runtime" value={formatInteger(blockedRuns)} detail="Policy block memerlukan tindakan" />
          <Metric label="Active Kill Switch" value={formatInteger(activeKillSwitch)} detail="Kontrol darurat" />
          <Metric label="Budget Terpakai" value={`${budgetPercent}%`} detail={`${formatCurrency(data.usage.estimated_cost_usd)} hari ini`} />
        </section>
        <section className="dashboard-grid governance-action-grid">
          <article className="panel"><div className="panel-heading"><div><p className="eyebrow">PENDING HUMAN ACTIONS</p><h2>Tindakan sesuai role Anda</h2></div><span className="role-badge">{formatRoleLabel(data.actor.roles)}</span></div>{actionableReleases.length > 0 ? <>{actionableReleases.slice(0, 5).map((release) => <button className="next-action-card" key={release.change_request_id} onClick={() => router.push(`/releases?view=${["DRAFT", "RETURNED"].includes(release.state) ? "tests" : "reviews"}`)} type="button"><strong>{release.agent_key} · {release.semantic_version}</strong><span>{release.state === "DRAFT" || release.state === "RETURNED" ? "Test evidence memerlukan execution atau submit oleh Checker." : release.state === "IN_REVIEW" ? "Business/Technical Review atau Director Approval diperlukan." : release.state === "APPROVED" ? "Versi siap dirilis oleh Approver tercatat." : "Versi siap diaktifkan oleh Approver tercatat."}</span><small>Open required control →</small></button>)}</> : <p className="empty-state">Tidak ada review yang menunggu untuk role Anda saat ini.</p>}</article>
          <article className="panel"><p className="eyebrow">RISK / BLOCKER SUMMARY</p><h2>Status operasional</h2><dl className="review-list"><div><dt>FAILED / BLOCKED run</dt><dd>{failedRuns + blockedRuns}</dd></div><div><dt>Suspended Agent</dt><dd>{suspendedAgents}</dd></div><div><dt>Permission belum APPROVED</dt><dd>{data.permissions.filter((permission) => permission.lifecycle_status !== "APPROVED").length}</dd></div><div><dt>Budget warning</dt><dd>{budgetPercent >= 100 ? "BUDGET_EXHAUSTED" : budgetPercent >= 90 ? "WARNING_90" : budgetPercent >= 70 ? "WARNING_70" : "NORMAL"}</dd></div></dl></article>
          <article className="panel"><p className="eyebrow">RECENT GOVERNANCE ACTIVITY</p><h2>Perubahan terakhir</h2>{data.audit.length ? <ol className="audit-list">{data.audit.slice(0, 5).map((event) => <li key={event.audit_event_id}><strong>{event.action}</strong><span>{event.reason}</span><time>{formatDateTime(event.occurred_at)}</time></li>)}</ol> : <p className="empty-state">Belum ada governance activity pada workspace ini.</p>}</article>
        </section>
      </> : null}

      {view === "permissions" ? <section className="dashboard-grid lower-grid governance-single-panel"><article className="panel"><div className="panel-heading"><div><p className="eyebrow">PERMISSIONS</p><h2>Akses yang diizinkan dan ditolak</h2></div><span className="permission-readonly">Contract tidak memberi izin otomatis</span></div>{data.permissions.length ? <div className="table-wrap"><table><thead><tr><th>Permission</th><th>Capability</th><th>Tool</th><th>Access Mode</th><th>Effect</th><th>Status</th><th>Approved By</th></tr></thead><tbody>{data.permissions.map((permission) => <tr key={permission.permission_policy_id}><td>{permission.permission_key}</td><td>{permission.capability_key ?? "—"}</td><td>{permission.tool_key ?? "—"}</td><td>{permission.access_mode}</td><td>{permission.effect}</td><td><span className={`lifecycle-pill lifecycle-${permission.lifecycle_status.toLowerCase()}`}>{permission.lifecycle_status}</span></td><td>{permission.approved_by_user_id?.slice(0, 8) ?? "Belum disetujui"}</td></tr>)}</tbody></table></div> : <p className="empty-state">Belum ada Permission Policy. Agent dengan kebutuhan akses akan tetap NEEDS_CONFIGURATION.</p>}<h3>Tool Registry</h3><div className="table-wrap"><table><thead><tr><th>Tool</th><th>Risk</th><th>Access</th><th>Lifecycle</th></tr></thead><tbody>{data.tools.map((tool) => <tr key={tool.tool_definition_id}><td>{tool.name}<br /><small>{tool.tool_key}</small></td><td>{tool.risk_level}</td><td>{String(tool.manifest.access_mode ?? "—")}</td><td>{tool.lifecycle_status}</td></tr>)}</tbody></table></div></article></section> : null}

      {view === "budget" ? <section className="dashboard-grid">
        <article className="panel budget-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">DAILY CONTROL</p><h2>Ubah limit workspace</h2></div>
            <span className={mayChange ? "permission-ok" : "permission-readonly"}>
              {mayChange ? "Dapat mengubah" : "Read-only"}
            </span>
          </div>
          <p className="muted">Hanya DIRECTOR atau IT_LEAD yang dapat menyimpan perubahan.</p>
          <div className="budget-form">
            <label>
              Request / hari
              <input aria-invalid={!budgetValidation.requests} disabled={!mayChange || saving} min="1" onChange={(event) => setForm({ ...form, requests: event.target.value })} type="number" value={form.requests} />
              {!budgetValidation.requests ? <span className="field-error">Daily Request Limit harus bilangan bulat lebih dari 0.</span> : null}
            </label>
            <label>
              Output token / hari
              <input aria-invalid={!budgetValidation.tokens} disabled={!mayChange || saving} min="1000" onChange={(event) => setForm({ ...form, tokens: event.target.value })} type="number" value={form.tokens} />
              {!budgetValidation.tokens ? <span className="field-error">Daily Output Token Limit minimal 1.000 token.</span> : null}
            </label>
            <label>
              Hard cost cap (USD)
              <input aria-invalid={!budgetValidation.cost} disabled={!mayChange || saving} min="0" onChange={(event) => setForm({ ...form, cost: event.target.value })} step="0.01" type="number" value={form.cost} />
              {!budgetValidation.cost ? <span className="field-error">Daily Cost Cap tidak boleh negatif.</span> : null}
            </label>
          </div>
          <div className="budget-thresholds" aria-label="Budget thresholds"><span>70% WARNING</span><span>90% CRITICAL</span><span>100% BLOCKED</span></div>
          <button disabled={!mayChange || saving || !budgetFormValid} onClick={() => void saveBudget()} type="button">
            {saving ? "Menyimpan…" : "Simpan limit & audit"}
          </button>
          {!mayChange ? <p className="field-note">Read-only: hanya Director atau IT Lead yang dapat mengubah budget.</p> : null}
        </article>

        <article className="panel">
          <p className="eyebrow">MODEL GATEWAY</p>
          <h2>Provider & routing</h2>
          <dl className="policy-list">
            <div><dt>Provider</dt><dd>{data.policy.provider}</dd></div>
            <div><dt>Light</dt><dd>{data.policy.model_light || "Tidak dikonfigurasi"}</dd></div>
            <div><dt>Standard</dt><dd>{data.policy.model_standard || "Tidak dikonfigurasi"}</dd></div>
            <div><dt>Critical</dt><dd>{data.policy.model_critical || "Tidak dikonfigurasi"}</dd></div>
            <div><dt>Maks. output / request</dt><dd>{formatInteger(data.policy.max_output_tokens)} token</dd></div>
          </dl>
          <p className="safe-note">Credential provider tidak tersedia pada dashboard.</p>
        </article>
      </section> : null}

      {view === "runtime" ? <section className="dashboard-grid lower-grid governance-single-panel"><article className="panel">
          <p className="eyebrow">RECENT RUNTIME</p>
          <h2>Provider, model, dan latency</h2>
          {latestRun ? (
            <div className="latest-run">
              <strong>{latestRun.agent_key}</strong>
              <span>{latestRun.provider || "Provider belum tercatat"} · {latestRun.model || "Model belum tercatat"}</span>
              <span>{latestRun.latency_milliseconds === null ? "Latency belum tersedia" : `${formatInteger(latestRun.latency_milliseconds)} ms`}</span>
            </div>
          ) : <p className="empty-state">Belum ada Agent Runtime run pada workspace ini.</p>}
          <div className="governance-filters"><select aria-label="Filter Runtime Agent" onChange={(event) => setRuntimeFilter({ ...runtimeFilter, agent: event.target.value })} value={runtimeFilter.agent}><option value="">Semua Agent</option>{[...new Set(data.runs.map((run) => run.agent_key))].map((agent) => <option key={agent}>{agent}</option>)}</select><select aria-label="Filter Runtime status" onChange={(event) => setRuntimeFilter({ ...runtimeFilter, status: event.target.value })} value={runtimeFilter.status}><option value="">Semua status</option>{["SUCCEEDED", "FAILED", "BLOCKED", "SUSPENDED", "KILLED"].map((status) => <option key={status}>{status}</option>)}</select><input aria-label="Filter Runtime tanggal" onChange={(event) => setRuntimeFilter({ ...runtimeFilter, date: event.target.value })} type="date" value={runtimeFilter.date} /></div>
          {visibleRuns.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Run ID / Agent</th><th>Version / Status</th><th>Provider / Model</th><th>Tokens / Cost</th><th>Latency / Timestamp</th><th>Reason / Next Action</th></tr></thead>
                <tbody>
                  {visibleRuns.map((run) => (
                    <tr key={run.agent_run_id}>
                      <td><code>{run.agent_run_id.slice(0, 8)}</code><br />{run.agent_key}</td><td>{run.semantic_version}<br /><strong>{run.status}</strong></td><td>{run.provider || "—"}<br />{run.model || "—"}</td><td>{formatInteger(run.input_tokens ?? 0)} in / {formatInteger(run.output_tokens ?? 0)} out<br />{formatCurrency(run.estimated_cost_usd ?? "0")}</td><td>{run.latency_milliseconds === null ? "—" : `${formatInteger(run.latency_milliseconds)} ms`}<br />{formatDateTime(run.created_at)}</td><td>{run.block_reason ? <><strong>{run.block_reason}</strong><br /><small>{run.error_code} · {runtimeNextAction(run.error_code, run.block_reason)}</small></> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="empty-state">Belum ada Agent Run yang sesuai filter. Jalankan Test atau Agent untuk melihat runtime activity.</p>}
        </article></section> : null}

      {view === "audit" ? <section className="dashboard-grid lower-grid governance-single-panel"><article className="panel">
          <p className="eyebrow">APPEND-ONLY AUDIT</p>
          <h2>Audit trail workspace</h2>
          {data.auditRestricted ? <p className="empty-state">Audit trail hanya tersedia untuk Director, IT Lead, atau Wakil IT.</p> : null}
          {!data.auditRestricted && data.audit.length === 0 ? <p className="empty-state">Belum ada audit event untuk workspace ini.</p> : null}
          <div className="governance-filters"><input aria-label="Filter Agent audit" onChange={(event) => setAuditFilter({ ...auditFilter, agent: event.target.value })} placeholder="Agent key" value={auditFilter.agent} /><input aria-label="Filter actor audit" onChange={(event) => setAuditFilter({ ...auditFilter, actor: event.target.value })} placeholder="Actor" value={auditFilter.actor} /><input aria-label="Filter action audit" onChange={(event) => setAuditFilter({ ...auditFilter, action: event.target.value })} placeholder="Action" value={auditFilter.action} /><input aria-label="Filter correlation audit" onChange={(event) => setAuditFilter({ ...auditFilter, correlation: event.target.value })} placeholder="Correlation ID" value={auditFilter.correlation} /><input aria-label="Filter tanggal audit" onChange={(event) => setAuditFilter({ ...auditFilter, date: event.target.value })} type="date" value={auditFilter.date} /></div><ol className="audit-list">
            {visibleAudit.map((event) => (
              <li key={event.audit_event_id}>
                <strong>{event.action}</strong>
                <span>{event.reason} · {event.actor_kind === "HUMAN" ? event.actor_user_id?.slice(0, 8) : event.system_actor}</span>
                <code>Correlation: {event.correlation_id ?? "—"}</code>
                <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
              </li>
            ))}
          </ol>
        </article>
      </section> : null}
    </main>
  );
}

async function loadFoundation(): Promise<Foundation> {
  const [actor, workspaces, policy] = await Promise.all([
    api<SessionActor>("/api/v1/whoami"),
    api<Workspace[]>("/api/v1/workspaces"),
    api<ModelPolicy>("/api/v1/governance/model-policy"),
  ]);
  return { actor, workspaces, policy };
}

async function loadAudit(workspaceId: string): Promise<Pick<DashboardData, "audit" | "auditRestricted">> {
  try {
    return { audit: await api<AuditEvent[]>(`/api/v1/audit-events?workspace_id=${workspaceId}&limit=30`), auditRestricted: false };
  } catch (error: unknown) {
    if (error instanceof ApiError && error.status === 403) {
      return { audit: [], auditRestricted: true };
    }
    throw error;
  }
}

function foundationOf(data: DashboardData): Foundation {
  return { actor: data.actor, workspaces: data.workspaces, policy: data.policy };
}

function Metric({ detail, label, value }: { detail: string; label: string; value: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

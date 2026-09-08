"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiRequest as api } from "@/lib/api-client";
import { GovernanceFeedback, GovernanceNavigation } from "@/components/governance-control-ui";
import { normalizeGovernanceError, type GovernanceUiError } from "@/lib/governance-errors";
import type { ReleaseRequest } from "@/lib/release-governance";

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
};

type Foundation = Pick<DashboardData, "actor" | "workspaces" | "policy">;

export function GovernanceDashboard() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [error, setError] = useState<GovernanceUiError | null>(null);
  const [notice, setNotice] = useState("");
  const [view, setView] = useState<"overview" | "runtime" | "budget" | "audit">("overview");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ requests: "", tokens: "", cost: "" });

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, base?: Foundation) => {
    const foundation = base ?? (await loadFoundation());
    const [budget, usage, runs, auditResult, releases] = await Promise.all([
      api<Budget>(`/api/v1/workspaces/${selectedWorkspaceId}/budget`),
      api<Usage>(`/api/v1/workspaces/${selectedWorkspaceId}/usage/daily`),
      api<Run[]>(`/api/v1/workspaces/${selectedWorkspaceId}/runs?limit=12`),
      loadAudit(selectedWorkspaceId),
      api<ReleaseRequest[]>(`/api/v1/release-requests?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`),
    ]);
    setData({ ...foundation, budget, usage, runs, releases, ...auditResult });
    setForm({
      requests: String(budget.daily_request_limit),
      tokens: String(budget.daily_output_token_limit),
      cost: String(budget.daily_cost_cap_usd),
    });
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (foundation.workspaces.length === 0) {
          setError({ title: "Workspace belum tersedia", reason: "Akun ini belum memiliki workspace aktif.", nextAction: "Minta Administrator memberi akses workspace.", status: null, correlationId: null });
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
    await api<void>("/api/v1/auth/logout", { method: "POST" });
    window.location.assign(new URL("/login", window.location.origin).href);
  }

  if (loading && !data) {
    return <main className="loading-shell">Memuat Governance Dashboard…</main>;
  }
  if (!data) {
    return (
      <main className="loading-shell">
        <GovernanceFeedback error={error} notice="" />
        <Link className="text-link" href="/login">Ke halaman login</Link>
      </main>
    );
  }

  const mayChange = canChangeBudget(data.actor.roles);
  const latestRun = data.runs[0];
  const pendingReviews = data.releases.filter((release) => ["TESTED", "IN_REVIEW", "APPROVED"].includes(release.state)).length;
  const activeAgents = new Set(data.releases.filter((release) => release.state === "ACTIVE").map((release) => release.agent_key)).size;
  const suspendedAgents = new Set(data.releases.filter((release) => release.state === "SUSPENDED").map((release) => release.agent_key)).size;
  const failedRuns = data.runs.filter((run) => ["FAILED", "BLOCKED"].includes(run.status)).length;
  const budgetPercent = Math.min(100, Math.round((Number(data.usage.estimated_cost_usd) / Math.max(Number(data.budget.daily_cost_cap_usd), 0.0001)) * 100));

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
        {(["overview", "runtime", "budget", "audit"] as const).map((item) => <button aria-current={view === item ? "page" : undefined} className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">{{ overview: "Overview", runtime: "Runtime & Monitoring", budget: "Budget", audit: "Audit" }[item]}</button>)}
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
          <Metric label="Agent Active" value={formatInteger(activeAgents)} detail={`${suspendedAgents} suspended`} />
          <Metric label="Pending Review" value={formatInteger(pendingReviews)} detail="Memerlukan tindakan manusia" />
          <Metric label="Runtime Bermasalah" value={formatInteger(failedRuns)} detail="FAILED atau BLOCKED terbaru" />
          <Metric label="Budget Terpakai" value={`${budgetPercent}%`} detail={`${formatCurrency(data.usage.estimated_cost_usd)} hari ini`} />
        </section>
        <section className="dashboard-grid governance-action-grid">
          <article className="panel"><div className="panel-heading"><div><p className="eyebrow">ACTION REQUIRED</p><h2>Tindakan sesuai role Anda</h2></div><span className="role-badge">{formatRoleLabel(data.actor.roles)}</span></div>{pendingReviews > 0 ? <button className="next-action-card" onClick={() => router.push("/releases")} type="button"><strong>{pendingReviews} release menunggu gate manusia</strong><span>Buka detail untuk melihat reviewer, blocker, dan langkah berikutnya.</span><small>Buka Release, Test &amp; Review →</small></button> : <p className="empty-state">Tidak ada review yang memerlukan tindakan saat ini.</p>}</article>
          <article className="panel"><p className="eyebrow">CONTROL BLOCKERS</p><h2>Status operasional</h2><dl className="review-list"><div><dt>FAILED / BLOCKED run</dt><dd>{failedRuns}</dd></div><div><dt>Suspended Agent</dt><dd>{suspendedAgents}</dd></div><div><dt>Budget warning</dt><dd>{budgetPercent >= 100 ? "BUDGET_EXHAUSTED" : budgetPercent >= 90 ? "WARNING_90" : budgetPercent >= 70 ? "WARNING_70" : "NORMAL"}</dd></div></dl></article>
        </section>
      </> : null}

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
              <input disabled={!mayChange || saving} min="1" onChange={(event) => setForm({ ...form, requests: event.target.value })} type="number" value={form.requests} />
            </label>
            <label>
              Output token / hari
              <input disabled={!mayChange || saving} min="1000" onChange={(event) => setForm({ ...form, tokens: event.target.value })} type="number" value={form.tokens} />
            </label>
            <label>
              Hard cost cap (USD)
              <input disabled={!mayChange || saving} min="0" onChange={(event) => setForm({ ...form, cost: event.target.value })} step="0.01" type="number" value={form.cost} />
            </label>
          </div>
          <button disabled={!mayChange || saving} onClick={() => void saveBudget()} type="button">
            {saving ? "Menyimpan…" : "Simpan limit & audit"}
          </button>
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
          {data.runs.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Run</th><th>Status</th><th>Model</th><th>Latency</th></tr></thead>
                <tbody>
                  {data.runs.map((run) => (
                    <tr key={run.agent_run_id}>
                      <td>{run.agent_key}</td><td>{run.status}</td><td>{run.model || "—"}</td><td>{run.latency_milliseconds === null ? "—" : `${formatInteger(run.latency_milliseconds)} ms`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </article></section> : null}

      {view === "audit" ? <section className="dashboard-grid lower-grid governance-single-panel"><article className="panel">
          <p className="eyebrow">APPEND-ONLY AUDIT</p>
          <h2>Audit trail workspace</h2>
          {data.auditRestricted ? <p className="empty-state">Audit trail hanya tersedia untuk Director, IT Lead, atau Wakil IT.</p> : null}
          {!data.auditRestricted && data.audit.length === 0 ? <p className="empty-state">Belum ada audit event untuk workspace ini.</p> : null}
          <ol className="audit-list">
            {data.audit.map((event) => (
              <li key={event.audit_event_id}>
                <strong>{event.action}</strong>
                <span>{event.reason}</span>
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

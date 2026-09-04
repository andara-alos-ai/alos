"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  ApiError,
  type AuditEvent,
  type Budget,
  canChangeBudget,
  formatCurrency,
  formatDateTime,
  formatInteger,
  remainingBudget,
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
};

type Foundation = Pick<DashboardData, "actor" | "workspaces" | "policy">;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return (await response.json()) as T;
}

export function GovernanceDashboard() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ requests: "", tokens: "", cost: "" });

  const loadWorkspace = useCallback(async (selectedWorkspaceId: string, base?: Foundation) => {
    const foundation = base ?? (await loadFoundation());
    const [budget, usage, runs, auditResult] = await Promise.all([
      api<Budget>(`/api/v1/workspaces/${selectedWorkspaceId}/budget`),
      api<Usage>(`/api/v1/workspaces/${selectedWorkspaceId}/usage/daily`),
      api<Run[]>(`/api/v1/workspaces/${selectedWorkspaceId}/runs?limit=12`),
      loadAudit(selectedWorkspaceId),
    ]);
    setData({ ...foundation, budget, usage, runs, ...auditResult });
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
        setError("Data governance tidak dapat dimuat. Coba muat ulang halaman.");
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [loadWorkspace, router]);

  const remaining = useMemo(
    () => (data ? remainingBudget(data.budget, data.usage) : null),
    [data],
  );

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setLoading(true);
    setError("");
    try {
      await loadWorkspace(nextWorkspaceId, data ? foundationOf(data) : undefined);
    } catch (loadError: unknown) {
      if (loadError instanceof ApiError && loadError.status === 401) {
        router.replace("/login");
      } else {
        setError("Workspace tidak dapat dimuat.");
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
    setError("");
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
    } catch (saveError: unknown) {
      if (saveError instanceof ApiError && saveError.status === 401) {
        router.replace("/login");
      } else if (saveError instanceof ApiError && saveError.status === 403) {
        setError("Peran Anda tidak memiliki izin untuk mengubah limit.");
      } else {
        setError("Limit tidak dapat disimpan. Periksa nilai lalu coba lagi.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
    });
    router.replace("/login");
    router.refresh();
  }

  if (loading && !data) {
    return <main className="loading-shell">Memuat Governance Dashboard…</main>;
  }
  if (!data) {
    return (
      <main className="loading-shell">
        <p>{error || "Sesi tidak tersedia."}</p>
        <a className="text-link" href="/login">Ke halaman login</a>
      </main>
    );
  }

  const mayChange = canChangeBudget(data.actor.roles);
  const latestRun = data.runs[0];

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">ALOS / GOVERNANCE</p>
          <h1>Control plane</h1>
          <p className="muted">Satu shared Agent Runtime, satu PostgreSQL, dan Genesis sebagai system actor.</p>
        </div>
        <div className="header-actions">
          <span className="role-badge">{data.actor.roles.join(" · ")}</span>
          {data.actor.roles.includes("IT_LEAD") ? <a className="secondary-button button-link" href="/agents">Agent Registry</a> : null}
          <button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button>
        </div>
      </header>

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

      {error ? <p className="banner-error" role="alert">{error}</p> : null}

      <section className="metric-grid" aria-label="Batas dan penggunaan harian">
        <Metric label="Limit request / hari" value={formatInteger(data.budget.daily_request_limit)} detail={`Sisa ${formatInteger(remaining?.requests ?? 0)}`} />
        <Metric label="Limit output token / hari" value={formatInteger(data.budget.daily_output_token_limit)} detail={`Sisa ${formatInteger(remaining?.tokens ?? 0)}`} />
        <Metric label="Hard cost cap / hari" value={formatCurrency(data.budget.daily_cost_cap_usd)} detail={`Sisa ${formatCurrency(remaining?.cost ?? "0")}`} />
        <Metric label="Pemakaian hari ini" value={`${formatInteger(data.usage.request_count)} request`} detail={`${formatInteger(data.usage.output_tokens)} output token`} />
      </section>

      <section className="dashboard-grid">
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
      </section>

      <section className="dashboard-grid lower-grid">
        <article className="panel">
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
        </article>

        <article className="panel">
          <p className="eyebrow">APPEND-ONLY AUDIT</p>
          <h2>Audit trail workspace</h2>
          {data.auditRestricted ? <p className="empty-state">Audit trail hanya tersedia untuk DIRECTOR, IT_LEAD, atau QA_SECURITY.</p> : null}
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
      </section>
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

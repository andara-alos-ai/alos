"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { apiRequest, withQuery } from "@/lib/api-client";
import {
  factoryMissingDependencies,
  factoryStatusLabel,
  factoryStatusTone,
  type FactoryPage,
  type FactoryRequest,
} from "@/lib/genesis-factory";
import { type SessionActor } from "@/lib/governance";

type FactoryUiError = {
  title: string;
  reason: string;
  nextAction: string;
};

export function GenesisFactoryConsole({ actor }: { actor: SessionActor }) {
  const [workspaceId, setWorkspaceId] = useState(actor.workspace_ids[0] ?? "");
  const [requirement, setRequirement] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [requests, setRequests] = useState<FactoryRequest[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<FactoryUiError | null>(null);
  const [notice, setNotice] = useState("");

  const loadRequests = useCallback(
    async (nextWorkspaceId: string) => {
      if (!nextWorkspaceId) return;
      const page = await apiRequest<FactoryPage>(
        withQuery("/api/v1/genesis/factory/requests", {
          workspace_id: nextWorkspaceId,
          limit: 50,
        }),
      );
      setRequests(page.items);
      setSelectedId((current) => current || page.items[0]?.factory_request_id || "");
    },
    [],
  );

  useEffect(() => {
    async function initialize() {
      setLoading(true);
      setError(null);
      try {
        const first = actor.workspace_ids[0] ?? "";
        setWorkspaceId(first);
        if (first) await loadRequests(first);
      } catch (failure) {
        setError(toError(failure));
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [actor.workspace_ids, loadRequests]);

  async function createRequest(event: FormEvent) {
    event.preventDefault();
    if (!workspaceId || requirement.trim().length < 10 || saving) return;
    setSaving(true);
    setError(null);
    setNotice("");
    const key = idempotencyKey.trim() || `factory-${Date.now()}`;
    try {
      const created = await apiRequest<FactoryRequest>("/api/v1/genesis/factory/requests", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          requirement: requirement.trim(),
          idempotency_key: key,
        }),
      });
      setRequests((current) => [created, ...current.filter((item) => item.factory_request_id !== created.factory_request_id)]);
      setSelectedId(created.factory_request_id);
      setRequirement("");
      setIdempotencyKey("");
      setNotice("Factory requirement berhasil dibuat dan tersimpan.");
    } catch (failure) {
      setError(toError(failure));
    } finally {
      setSaving(false);
    }
  }

  async function analyzeSelected() {
    if (!selectedId || analyzing) return;
    setAnalyzing(true);
    setError(null);
    setNotice("");
    try {
      const updated = await apiRequest<FactoryRequest>(
        `/api/v1/genesis/factory/requests/${selectedId}/analyze`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setRequests((current) =>
        current.map((item) => (item.factory_request_id === updated.factory_request_id ? updated : item)),
      );
      setNotice("Analysis selesai. Lifecycle dan blockers diperbarui.");
    } catch (failure) {
      setError(toError(failure));
    } finally {
      setAnalyzing(false);
    }
  }

  async function refreshSelected() {
    if (!workspaceId) return;
    await loadRequests(workspaceId);
  }

  const selected = requests.find((item) => item.factory_request_id === selectedId) ?? requests[0];

  if (loading) return <section className="alos-content">Memuat GENESIS Factory…</section>;

  return (
    <section className="alos-content genesis-factory-console">
      <div className="alos-panel">
        <div className="alos-panel-title">
          <p className="alos-kicker">GENESIS FACTORY</p>
          <h3>Requirement Baru</h3>
          <p>Masukkan kebutuhan bisnis. Backend tetap authoritative atas lifecycle, tools, tests, dan governance.</p>
        </div>
        <form onSubmit={(event) => void createRequest(event)}>
          <label>
            Workspace
            <select onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId}>
              {actor.workspace_ids.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </label>
          <label>
            Requirement
            <textarea minLength={10} onChange={(event) => setRequirement(event.target.value)} required value={requirement} />
          </label>
          <label>
            Idempotency key
            <input onChange={(event) => setIdempotencyKey(event.target.value)} placeholder="Kosongkan untuk generate" value={idempotencyKey} />
          </label>
          <button disabled={saving || requirement.trim().length < 10} type="submit">
            {saving ? "Menyimpan…" : "Create Factory Request"}
          </button>
        </form>
        {notice ? <p className="genesis-factory-notice">{notice}</p> : null}
      </div>

      <div className="alos-panel">
        <div className="alos-panel-heading-row">
          <div className="alos-panel-title">
            <p className="alos-kicker">REQUESTS</p>
            <h3>Persistent Factory Records</h3>
          </div>
          <button onClick={() => void refreshSelected()} type="button">Reload</button>
        </div>
        <div className="genesis-factory-layout">
          <div>
            {requests.length ? requests.map((request) => (
              <button
                className={request.factory_request_id === selected?.factory_request_id ? "selected" : ""}
                key={request.factory_request_id}
                onClick={() => setSelectedId(request.factory_request_id)}
                type="button"
              >
                <strong>{request.requirement.slice(0, 90)}</strong>
                <small>{factoryStatusLabel(request.status)} · {new Date(request.updated_at).toLocaleString("id-ID")}</small>
              </button>
            )) : <p className="genesis-factory-empty">Belum ada Factory request.</p>}
          </div>
          <FactoryDetail request={selected} />
        </div>
      </div>

      {selected ? (
        <div className="alos-panel genesis-factory-actions">
          <button disabled={analyzing || selected.status === "BLOCKED"} onClick={() => void analyzeSelected()} type="button">
            {analyzing ? "Analyzing…" : "Analyze Requirement"}
          </button>
          <small>Factory tidak pernah auto-activate. Release dan governance tetap melalui jalur yang ada.</small>
        </div>
      ) : null}

      {error ? (
        <section className="genesis-factory-error" role="alert">
          <strong>{error.title}</strong>
          <span>{error.reason}</span>
          <small>Langkah berikutnya: {error.nextAction}</small>
        </section>
      ) : null}
    </section>
  );
}

function FactoryDetail({ request }: { request: FactoryRequest | undefined }) {
  if (!request) return <p className="genesis-factory-empty">Pilih request untuk melihat detail.</p>;
  const missing = factoryMissingDependencies(request);
  return (
    <article className="genesis-factory-detail">
      <div className="genesis-factory-detail-head">
        <span className={`alos-status-pill ${factoryStatusTone(request.status)}`}>
          {factoryStatusLabel(request.status)}
        </span>
        <small>{request.factory_request_id}</small>
      </div>
      <h4>{request.requirement}</h4>
      <dl>
        <div><dt>Objective</dt><dd>{request.requirement_understanding?.objective ?? "—"}</dd></div>
        <div><dt>Implementation type</dt><dd>{request.implementation_decision?.implementation_type ?? "—"}</dd></div>
        <div><dt>Capabilities</dt><dd>{request.implementation_decision?.required_capabilities.join(", ") || "—"}</dd></div>
        <div><dt>Required tools</dt><dd>{request.dependency_resolution?.tool_keys.join(", ") || "—"}</dd></div>
        <div><dt>Missing dependencies</dt><dd>{missing.join(", ") || "None"}</dd></div>
        <div><dt>Risk</dt><dd>{request.implementation_decision?.risk ?? "—"}</dd></div>
        <div><dt>Human gate</dt><dd>{request.implementation_decision?.human_gate_required ? "REQUIRED" : "—"}</dd></div>
        <div><dt>Generated tests</dt><dd>{request.generated_tests.map((test) => `${test.category}:${test.execution_status}`).join(", ") || "—"}</dd></div>
        <div><dt>Blockers</dt><dd>{request.blockers.length ? request.blockers.map((item) => String(item.reason ?? item.code ?? "blocked")).join("; ") : "None"}</dd></div>
        <div><dt>Agent contract</dt><dd>{request.factory_proposal?.agent_contract?.agent_key ?? "—"}</dd></div>
      </dl>
    </article>
  );
}

function toError(failure: unknown): FactoryUiError {
  if (failure instanceof Error) {
    return {
      title: "Factory request gagal",
      reason: failure.message,
      nextAction: "Periksa scope dan input, lalu coba kembali.",
    };
  }
  return { title: "Factory request gagal", reason: "Kegagalan tidak dikenali.", nextAction: "Muat ulang data." };
}

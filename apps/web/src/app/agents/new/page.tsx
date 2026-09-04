"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/governance";

type Workspace = {
  workspace_id: string;
  name: string;
  workspace_key: string;
};

type DraftResult = {
  agent_key: string;
  semantic_version: string;
  lifecycle_status: string;
  digest: string;
};

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

const KEY_PATTERN = /^[A-Z][A-Z0-9_]{2,79}$/;

export default function AgentBuilderPage() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<DraftResult | null>(null);
  const [form, setForm] = useState({
    workspace_id: "",
    agent_key: "",
    name: "",
    requirement: "",
    parent_agent_key: "",
  });

  useEffect(() => {
    async function initialize() {
      try {
        const workspaceList = await api<Workspace[]>("/api/v1/workspaces");
        if (workspaceList.length === 0) {
          setError("Akun ini belum memiliki workspace aktif.");
          return;
        }
        setWorkspaces(workspaceList);
        setForm((current) => ({ ...current, workspace_id: workspaceList[0].workspace_id }));
      } catch (loadError: unknown) {
        if (loadError instanceof ApiError && loadError.status === 401) {
          router.replace("/login");
          return;
        }
        setError("Data workspace tidak dapat dimuat. Coba muat ulang halaman.");
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [router]);

  const submit = useCallback(async () => {
    setError("");
    setResult(null);
    if (!KEY_PATTERN.test(form.agent_key)) {
      setError("Agent Key harus huruf besar/angka/garis bawah, diawali huruf (mis. GEN_DAILY_BRIEF).");
      return;
    }
    if (form.name.trim().length < 1 || form.requirement.trim().length < 2) {
      setError("Nama dan requirement wajib diisi.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        workspace_id: form.workspace_id,
        agent_key: form.agent_key,
        name: form.name.trim(),
        requirement: form.requirement.trim(),
        parent_agent_key: form.parent_agent_key.trim() || null,
      };
      const response = await api<{ draft: DraftResult }>("/api/v1/designer/agent-drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(response.draft);
    } catch (submitError: unknown) {
      if (submitError instanceof ApiError && submitError.status === 401) {
        router.replace("/login");
        return;
      }
      if (submitError instanceof ApiError && submitError.status === 403) {
        setError("Peran Anda tidak memiliki izin membuat Agent Contract draft.");
        return;
      }
      setError("Draft tidak dapat dibuat. Periksa key (mungkin sudah ada) lalu coba lagi.");
    } finally {
      setSubmitting(false);
    }
  }, [form, router]);

  if (loading) {
    return <main className="loading-shell">Memuat Agent Builder…</main>;
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">ALOS / GENESIS</p>
          <h1>Agent Builder</h1>
          <p className="muted">
            Requirement bahasa-natural menjadi Agent Contract. Hasil selalu berstatus{" "}
            <strong>DRAFT</strong> — aktivasi tetap melalui test, review, dan approval manusia.
          </p>
        </div>
        <div className="header-actions">
          <Link className="secondary-button" href="/">Kembali ke dashboard</Link>
        </div>
      </header>

      {error ? <p className="banner-error" role="alert">{error}</p> : null}

      {result ? (
        <section className="panel">
          <p className="eyebrow">DRAFT TERSIMPAN</p>
          <h2>{result.agent_key}</h2>
          <dl className="policy-list">
            <div><dt>Versi</dt><dd>{result.semantic_version}</dd></div>
            <div><dt>Status</dt><dd>{result.lifecycle_status}</dd></div>
            <div><dt>Digest</dt><dd>{result.digest.slice(0, 16)}…</dd></div>
          </dl>
          <p className="safe-note">
            Agent belum aktif. Lanjutkan ke test, review teknis/bisnis, dan approval pada alur release.
          </p>
          <button
            type="button"
            onClick={() => {
              setResult(null);
              setForm((current) => ({ ...current, agent_key: "", name: "", requirement: "" }));
            }}
          >
            Buat draft lain
          </button>
        </section>
      ) : (
        <section className="panel budget-panel">
          <div className="budget-form" style={{ flexDirection: "column", gap: "1rem" }}>
            <label>
              Workspace
              <select
                value={form.workspace_id}
                onChange={(event) => setForm({ ...form, workspace_id: event.target.value })}
              >
                {workspaces.map((workspace) => (
                  <option key={workspace.workspace_id} value={workspace.workspace_id}>
                    {workspace.name} · {workspace.workspace_key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Agent Key
              <input
                placeholder="GEN_DAILY_BRIEF"
                value={form.agent_key}
                onChange={(event) => setForm({ ...form, agent_key: event.target.value.toUpperCase() })}
              />
            </label>
            <label>
              Nama agent
              <input
                placeholder="Daily Brief Agent"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>
            <label>
              Parent Agent Key (opsional, untuk Sub/Sub-Sub Agent)
              <input
                placeholder="kosongkan untuk Core Agent (level 0)"
                value={form.parent_agent_key}
                onChange={(event) =>
                  setForm({ ...form, parent_agent_key: event.target.value.toUpperCase() })
                }
              />
            </label>
            <label>
              Requirement (bahasa natural)
              <textarea
                rows={6}
                placeholder="Contoh: Agen read-only yang merangkum sumber terverifikasi lintas divisi setiap pagi, membuat draf brief dengan kutipan, tanpa mengambil tindakan."
                value={form.requirement}
                onChange={(event) => setForm({ ...form, requirement: event.target.value })}
              />
            </label>
          </div>
          <button disabled={submitting} onClick={() => void submit()} type="button">
            {submitting ? "Menyusun draft…" : "Buat Agent Contract DRAFT"}
          </button>
          <p className="safe-note">
            GENESIS hanya menyusun purpose, prompt, dan evidence requirement. Pemilihan model,
            tool, risk, dan approval tetap ditentukan oleh kontrol deterministik dan reviewer manusia.
          </p>
        </section>
      )}
    </main>
  );
}

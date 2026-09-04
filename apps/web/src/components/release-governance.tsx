"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { AgentRecord } from "@/lib/agent-registry";
import { ApiError, apiErrorDetail, formatDateTime, type SessionActor, type Workspace } from "@/lib/governance";
import {
  canApproveRelease,
  canCheckRelease,
  canDesignAgent,
  canMakeRelease,
  canOperateKillSwitch,
  canReadReleaseRegistry,
  canReviewGate,
  defaultTestForm,
  designerPayload,
  draftAgents,
  latestRunByTestCase,
  releaseErrorMessage,
  releaseTestCategories,
  testCasePayload,
  type DesignerResult,
  type ReleaseRequest,
  type ReleaseRequestDetail,
  type TestCategory,
} from "@/lib/release-governance";

type ReleaseData = {
  actor: SessionActor;
  workspaces: Workspace[];
  agents: AgentRecord[];
  requests: ReleaseRequest[];
};

type ReleaseFoundation = Pick<ReleaseData, "actor" | "workspaces">;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", credentials: "same-origin", ...init });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => undefined);
    throw new ApiError(response.status, apiErrorDetail(payload));
  }
  return (await response.json()) as T;
}

export function ReleaseGovernance() {
  const router = useRouter();
  const [data, setData] = useState<ReleaseData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [detail, setDetail] = useState<ReleaseRequestDetail | null>(null);
  const [designer, setDesigner] = useState({ requirement: "", agentKey: "", name: "", parentAgentKey: "" });
  const [releaseAgentKey, setReleaseAgentKey] = useState("");
  const [releaseRequirement, setReleaseRequirement] = useState("");
  const [testForm, setTestForm] = useState(defaultTestForm());
  const [review, setReview] = useState({ decision: "APPROVED", notes: "" });
  const [control, setControl] = useState({ reason: "", rollbackTarget: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  const loadWorkspace = useCallback(async (nextWorkspaceId: string, base?: ReleaseFoundation) => {
    const foundation = base ?? await loadFoundation();
    const [agents, requests] = await Promise.all([
      canReadReleaseRegistry(foundation.actor.roles)
        ? api<AgentRecord[]>(`/api/v1/agents?workspace_id=${encodeURIComponent(nextWorkspaceId)}`)
        : Promise.resolve([]),
      api<ReleaseRequest[]>(`/api/v1/release-requests?workspace_id=${encodeURIComponent(nextWorkspaceId)}`),
    ]);
    setData({ ...foundation, agents, requests });
  }, []);

  const loadDetail = useCallback(async (requestId: string) => {
    if (!requestId) {
      setDetail(null);
      return;
    }
    setDetail(await api<ReleaseRequestDetail>(`/api/v1/release-requests/${encodeURIComponent(requestId)}`));
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (foundation.workspaces.length === 0) {
          setError("Akun ini belum memiliki workspace aktif.");
          return;
        }
        const first = foundation.workspaces[0].workspace_id;
        setWorkspaceId(first);
        await loadWorkspace(first, foundation);
      } catch (loadError: unknown) {
        handleError(loadError, setError, router);
      } finally {
        setLoading(false);
      }
    }
    void initialize();
  }, [loadWorkspace, router]);

  const drafts = useMemo(() => draftAgents(data?.agents ?? []), [data?.agents]);
  const selectedDraft = drafts.find((agent) => agent.agent_key === releaseAgentKey);
  const latestTestRuns = useMemo(() => latestRunByTestCase(detail?.test_runs ?? []), [detail?.test_runs]);
  const reviewGate = canReviewGate(data?.actor.roles ?? []);

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId);
    setSelectedRequestId("");
    setDetail(null);
    setReleaseAgentKey("");
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await loadWorkspace(nextWorkspaceId, data ? { actor: data.actor, workspaces: data.workspaces } : undefined);
    } catch (loadError: unknown) {
      handleError(loadError, setError, router);
    } finally {
      setLoading(false);
    }
  }

  async function selectRequest(requestId: string) {
    setSelectedRequestId(requestId);
    setError("");
    setNotice("");
    try {
      await loadDetail(requestId);
    } catch (loadError: unknown) {
      handleError(loadError, setError, router);
    }
  }

  async function refreshRequest(requestId: string) {
    if (!data || !workspaceId) return;
    await loadWorkspace(workspaceId, { actor: data.actor, workspaces: data.workspaces });
    setSelectedRequestId(requestId);
    await loadDetail(requestId);
  }

  async function createDesignerDraft() {
    if (!data || !workspaceId) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const result = await api<DesignerResult>("/api/v1/designer/agent-drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(designerPayload({ workspaceId, ...designer })),
      });
      await loadWorkspace(workspaceId, { actor: data.actor, workspaces: data.workspaces });
      setReleaseAgentKey(result.draft.agent_key);
      setNotice(`Genesis membuat DRAFT ${result.draft.agent_key} versi ${result.draft.semantic_version}; tetap memerlukan test dan approval manusia.`);
    } catch (actionError: unknown) {
      handleError(actionError, setError, router);
    } finally {
      setWorking(false);
    }
  }

  async function createReleaseRequest() {
    if (!data || !workspaceId || !selectedDraft) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      if (releaseRequirement.trim().length < 20) throw new Error("Requirement release minimal 20 karakter.");
      const result = await api<ReleaseRequest>(`/api/v1/agents/${encodeURIComponent(selectedDraft.agent_key)}/release-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, requirement: releaseRequirement.trim() }),
      });
      await refreshRequest(result.change_request_id);
      setNotice(`Release request ${result.agent_key} dibuat dalam state DRAFT dan diaudit.`);
    } catch (actionError: unknown) {
      handleError(actionError, setError, router);
    } finally {
      setWorking(false);
    }
  }

  async function registerTestCase() {
    if (!detail) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const payload = testCasePayload(testForm);
      await api(`/api/v1/release-requests/${detail.change_request_id}/test-cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await refreshRequest(detail.change_request_id);
      setTestForm(defaultTestForm(testForm.category));
      setNotice(`Test case ${payload.test_key} terdaftar dan diaudit.`);
    } catch (actionError: unknown) {
      handleError(actionError, setError, router);
    } finally {
      setWorking(false);
    }
  }

  async function executeTest(testKey: string) {
    if (!detail) return;
    await runAction(
      `/api/v1/release-requests/${detail.change_request_id}/test-cases/${encodeURIComponent(testKey)}/execute`,
      undefined,
      `Test ${testKey} dieksekusi dan hasilnya diaudit.`,
    );
  }

  async function submitReview() {
    if (!detail) return;
    await runAction(`/api/v1/release-requests/${detail.change_request_id}/submit-review`, undefined, "Evidence test dikirim untuk review.");
  }

  async function recordReview() {
    if (!detail || !reviewGate) return;
    await runAction(
      `/api/v1/release-requests/${detail.change_request_id}/reviews`,
      { gate: reviewGate, decision: review.decision, notes: review.notes.trim() },
      `${reviewGate} review tercatat dan diaudit.`,
    );
  }

  async function controlAction(path: string, success: string, body?: Record<string, string>) {
    if (!detail) return;
    if ((path.includes("kill-switch") || path.includes("activate")) && !window.confirm("Lanjutkan aksi lifecycle ini? Audit permanen akan dibuat.")) return;
    await runAction(`/api/v1/release-requests/${detail.change_request_id}/${path}`, body, success);
  }

  async function runAction(path: string, body: Record<string, string> | undefined, success: string) {
    if (!detail) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const result = await api<ReleaseRequest>(path, {
        method: "POST",
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      await refreshRequest(result.change_request_id);
      setNotice(success);
    } catch (actionError: unknown) {
      handleError(actionError, setError, router);
    } finally {
      setWorking(false);
    }
  }

  async function logout() {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin", cache: "no-store" });
    router.replace("/login");
    router.refresh();
  }

  if (loading && !data) return <main className="loading-shell">Memuat Release Governance…</main>;
  if (!data) return <main className="loading-shell"><p>{error || "Sesi Release Governance tidak tersedia."}</p><Link className="text-link" href="/login">Ke halaman login</Link></main>;

  return (
    <main className="release-shell">
      <header className="dashboard-header registry-header">
        <div><p className="eyebrow">ALOS / H4 RELEASE</p><h1>Release Governance</h1><p className="muted">Lifecycle berotorisasi: DRAFT → RUN → TEST → REVIEW → APPROVED → ACTIVE.</p></div>
        <div className="header-actions"><span className="role-badge">{data.actor.roles.join(" · ")}</span><Link className="secondary-button button-link" href="/governance">Governance</Link><Link className="secondary-button button-link" href="/agents">Registry</Link><button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button></div>
      </header>

      <section className="workspace-bar registry-workspace" aria-label="Pemilihan workspace H4">
        <div><label htmlFor="release-workspace">Workspace aktif</label><select id="release-workspace" onChange={(event) => void selectWorkspace(event.target.value)} value={workspaceId}>{data.workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name} · {workspace.workspace_key}</option>)}</select></div>
        <p>SoD tidak dapat dilewati oleh prompt: Maker, Checker, dua Reviewer, dan Approver harus akun yang berbeda.</p>
      </section>

      {error ? <p className="banner-error" role="alert">{error}</p> : null}
      {notice ? <p className="banner-success" role="status">{notice}</p> : null}

      <section className="release-grid">
        <article className="panel release-list-panel"><div className="panel-heading"><div><p className="eyebrow">RELEASE REQUESTS</p><h2>{data.requests.length} Request</h2></div><span className="permission-readonly">Audit persist</span></div><ol className="agent-list">{data.requests.map((request) => <li key={request.change_request_id}><button className={selectedRequestId === request.change_request_id ? "agent-row selected" : "agent-row"} onClick={() => void selectRequest(request.change_request_id)} type="button"><span className="agent-level">H4</span><span><strong>{request.agent_key}</strong><small>{request.semantic_version} · {request.state}</small></span><span className={`lifecycle-pill lifecycle-${request.state.toLowerCase()}`}>{request.state}</span></button></li>)}</ol>{data.requests.length === 0 ? <p className="empty-state">Belum ada release request. Buat DRAFT lalu buka request pertama.</p> : null}</article>

        <section className="release-content">
          <article className="panel designer-panel">
            <div className="panel-heading"><div><p className="eyebrow">GENESIS DESIGNER</p><h2>Prompt → DRAFT aman</h2></div><span className="permission-ok">IT Lead only</span></div>
            {canDesignAgent(data.actor.roles) ? <><label>Requirement bahasa natural<textarea onChange={(event) => setDesigner((value) => ({ ...value, requirement: event.target.value }))} placeholder="Contoh: Buat Agent yang merangkum peluang properti internal setiap pagi tanpa mengubah data." rows={4} value={designer.requirement} /></label><div className="builder-fields two-column-fields compact-fields"><label>Agent key (opsional)<input onChange={(event) => setDesigner((value) => ({ ...value, agentKey: event.target.value }))} value={designer.agentKey} /></label><label>Nama Agent (opsional)<input onChange={(event) => setDesigner((value) => ({ ...value, name: event.target.value }))} value={designer.name} /></label></div><p className="field-note">Bila key dan nama dikosongkan, Genesis membuat identitas deterministik. Hasil selalu DRAFT, tanpa tool, permission, atau aktivasi.</p><div className="builder-actions"><button disabled={working} onClick={() => void createDesignerDraft()} type="button">Buat DRAFT dari prompt</button></div></> : <p className="safe-note">Genesis Designer hanya tersedia bagi IT Lead.</p>}
          </article>

          <article className="panel release-start-panel">
            <div className="panel-heading"><div><p className="eyebrow">MAKER</p><h2>Buka Release Request</h2></div><span className="permission-ok">Maker only</span></div>
            {canMakeRelease(data.actor.roles) ? <><div className="builder-fields two-column-fields"><label>Agent DRAFT<select onChange={(event) => setReleaseAgentKey(event.target.value)} value={releaseAgentKey}><option value="">Pilih DRAFT</option>{drafts.map((agent) => <option key={agent.agent_key} value={agent.agent_key}>{agent.name} · {agent.agent_key} · {agent.versions[0]?.semantic_version}</option>)}</select></label><label>Requirement release<textarea onChange={(event) => setReleaseRequirement(event.target.value)} placeholder="Jelaskan outcome dan batas release internal ini." rows={4} value={releaseRequirement} /></label></div><div className="builder-actions"><button disabled={working || !selectedDraft} onClick={() => void createReleaseRequest()} type="button">Buka request DRAFT</button></div></> : <p className="safe-note">Akun ini bukan Maker. Gunakan akun IT Lead, Division Owner, atau Director yang berbeda dari Checker/Approver.</p>}
          </article>

          <article className="panel lifecycle-panel">
            <div className="panel-heading"><div><p className="eyebrow">GATE C LIFECYCLE</p><h2>{detail ? `${detail.agent_key} · ${detail.semantic_version}` : "Pilih Release Request"}</h2></div>{detail ? <span className={`lifecycle-pill lifecycle-${detail.state.toLowerCase()}`}>{detail.state}</span> : null}</div>
            {!detail ? <p className="empty-state">Pilih request untuk melihat test, review, dan transisi lifecycle.</p> : <><p className="safe-note">{detail.requirement}</p><dl className="review-list"><div><dt>Kill switch</dt><dd>{detail.kill_switch_active ? "AKTIF — Agent tidak dapat berjalan" : "Tidak aktif"}</dd></div><div><dt>Checker / Approver</dt><dd>{detail.checker_user_id ? "Checker tercatat" : "Checker belum tercatat"} · {detail.approver_user_id ? "Approver tercatat" : "Approver belum tercatat"}</dd></div></dl><div className="lifecycle-track">{["DRAFT", "TESTED", "IN_REVIEW", "APPROVED", "RELEASED", "ACTIVE"].map((state) => <span className={detail.state === state ? "active" : ""} key={state}>{state}</span>)}</div></>}
          </article>

          {detail ? <article className="panel test-registry-panel"><div className="panel-heading"><div><p className="eyebrow">TEST CASE REGISTRY</p><h2>Positive, negative, regression, security, recovery</h2></div><span className="permission-ok">Maker / Checker</span></div>
            {detail.state === "DRAFT" || detail.state === "RETURNED" ? <>{canMakeRelease(data.actor.roles) ? <div className="builder-fields two-column-fields"><label>Kategori<select onChange={(event) => setTestForm(defaultTestForm(event.target.value as TestCategory))} value={testForm.category}>{releaseTestCategories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label><label>Test key<input onChange={(event) => setTestForm((form) => ({ ...form, testKey: event.target.value }))} value={testForm.testKey} /></label><label className="full-width">Fixture JSON<textarea className="code-input" onChange={(event) => setTestForm((form) => ({ ...form, fixture: event.target.value }))} rows={7} spellCheck="false" value={testForm.fixture} /></label><label>Expected status<select onChange={(event) => setTestForm((form) => ({ ...form, expectedStatus: event.target.value }))} value={testForm.expectedStatus}><option value="SUCCEEDED">SUCCEEDED</option><option value="FAILED">FAILED</option><option value="BLOCKED">BLOCKED</option></select></label></div> : null}<div className="builder-actions">{canMakeRelease(data.actor.roles) ? <button disabled={working} onClick={() => void registerTestCase()} type="button">Daftarkan test case</button> : null}</div></> : null}
            <div className="table-wrap"><table><thead><tr><th>Kategori</th><th>Test</th><th>Expected</th><th>Hasil terakhir</th><th>Aksi</th></tr></thead><tbody>{detail.test_cases.map((testCase) => { const result = latestTestRuns.get(testCase.test_case_id); return <tr key={testCase.test_case_id}><td>{testCase.category}</td><td>{testCase.test_key}</td><td>{String(testCase.expected_assertions.status ?? "—")}</td><td>{result ? `${result.status} · ${result.correlation_id.slice(0, 8)}…` : "Belum dijalankan"}</td><td>{canCheckRelease(data.actor.roles) && ["DRAFT", "RETURNED"].includes(detail.state) ? <button disabled={working} onClick={() => void executeTest(testCase.test_key)} type="button">Jalankan</button> : "—"}</td></tr>; })}</tbody></table></div>
            {canCheckRelease(data.actor.roles) && ["DRAFT", "RETURNED"].includes(detail.state) ? <div className="builder-actions"><button disabled={working || detail.test_cases.length < 5} onClick={() => void submitReview()} type="button">Kirim seluruh evidence untuk review</button></div> : null}
          </article> : null}

          {detail ? <article className="panel review-panel"><div className="panel-heading"><div><p className="eyebrow">REVIEW & APPROVAL</p><h2>SoD wajib</h2></div><span className="permission-readonly">Human control</span></div>
            <div className="table-wrap"><table><thead><tr><th>Gate</th><th>Keputusan</th><th>Catatan</th><th>Waktu</th></tr></thead><tbody>{detail.reviews.map((item) => <tr key={`${item.review_gate}-${item.created_at}`}><td>{item.review_gate}</td><td>{item.decision}</td><td>{item.notes}</td><td>{formatDateTime(item.created_at)}</td></tr>)}</tbody></table></div>
            {detail.state === "IN_REVIEW" && reviewGate ? <div className="builder-fields two-column-fields compact-fields"><label>Gate<input disabled value={reviewGate} /></label><label>Keputusan<select onChange={(event) => setReview((value) => ({ ...value, decision: event.target.value }))} value={review.decision}><option value="APPROVED">APPROVED</option><option value="RETURNED">RETURNED</option><option value="REJECTED">REJECTED</option></select></label><label className="full-width">Catatan reviewer<textarea onChange={(event) => setReview((value) => ({ ...value, notes: event.target.value }))} rows={3} value={review.notes} /></label></div> : null}
            <div className="builder-actions">{detail.state === "IN_REVIEW" && reviewGate ? <button disabled={working || !review.notes.trim()} onClick={() => void recordReview()} type="button">Catat review {reviewGate}</button> : null}{detail.state === "IN_REVIEW" && canApproveRelease(data.actor.roles) ? <button disabled={working} onClick={() => void controlAction("approve", "Request disetujui dan diaudit.")} type="button">Approve</button> : null}{detail.state === "APPROVED" && canApproveRelease(data.actor.roles) ? <button disabled={working} onClick={() => void controlAction("release", "Versi dirilis ke staging internal.")} type="button">Release</button> : null}{detail.state === "RELEASED" && canApproveRelease(data.actor.roles) ? <button disabled={working || detail.kill_switch_active} onClick={() => void controlAction("activate", "Versi aktif setelah approval manusia.")} type="button">Activate</button> : null}</div>
          </article> : null}

          {detail ? <article className="panel safety-controls-panel"><div className="panel-heading"><div><p className="eyebrow">SAFETY CONTROLS</p><h2>Suspend, kill switch, rollback</h2></div><span className="permission-ok">Audited</span></div><div className="builder-fields two-column-fields"><label>Alasan<textarea onChange={(event) => setControl((value) => ({ ...value, reason: event.target.value }))} placeholder="Alasan operasional yang akan dicatat pada audit." rows={3} value={control.reason} /></label><label>Target rollback<select onChange={(event) => setControl((value) => ({ ...value, rollbackTarget: event.target.value }))} value={control.rollbackTarget}><option value="">Pilih versi terdahulu</option>{detail.rollback_targets.map((target) => <option key={target} value={target}>{target}</option>)}</select></label></div><div className="builder-actions">{["ACTIVE", "RELEASED"].includes(detail.state) && canApproveRelease(data.actor.roles) ? <button className="secondary-button" disabled={working || !control.reason.trim()} onClick={() => void controlAction("suspend", "Agent disuspensi dan diaudit.", { reason: control.reason.trim() })} type="button">Suspend</button> : null}{canOperateKillSwitch(data.actor.roles) ? <button className="danger-button" disabled={working || !control.reason.trim()} onClick={() => void controlAction("kill-switch", "Kill switch aktif dan Agent dihentikan.", { reason: control.reason.trim() })} type="button">Aktifkan kill switch</button> : null}{detail.kill_switch_active && canOperateKillSwitch(data.actor.roles) ? <button className="secondary-button" disabled={working || !control.reason.trim()} onClick={() => void controlAction("clear-kill-switch", "Kill switch dibersihkan secara eksplisit.", { reason: control.reason.trim() })} type="button">Clear kill switch</button> : null}{["ACTIVE", "SUSPENDED"].includes(detail.state) && canApproveRelease(data.actor.roles) ? <button disabled={working || !control.reason.trim() || !control.rollbackTarget} onClick={() => void controlAction("rollback", "Rollback tercatat dan versi target menjadi aktif.", { reason: control.reason.trim(), target_semantic_version: control.rollbackTarget })} type="button">Rollback</button> : null}</div></article> : null}

          {detail ? <article className="panel lifecycle-evidence-panel"><p className="eyebrow">APPEND-ONLY EVIDENCE</p><h2>Riwayat lifecycle</h2><ol className="audit-list">{detail.lifecycle_events.map((event) => <li key={event.event_sequence}><strong>{event.from_state ?? "—"} → {event.to_state}</strong><span>{event.reason} · correlation {event.correlation_id}</span><time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time></li>)}</ol></article> : null}
        </section>
      </section>
    </main>
  );
}

async function loadFoundation(): Promise<ReleaseFoundation> {
  const [actor, workspaces] = await Promise.all([api<SessionActor>("/api/v1/whoami"), api<Workspace[]>("/api/v1/workspaces")]);
  return { actor, workspaces };
}

function handleError(error: unknown, setError: (message: string) => void, router: ReturnType<typeof useRouter>) {
  if (error instanceof ApiError && error.status === 401) {
    router.replace("/login");
  } else if (error instanceof ApiError && error.status === 403) {
    setError("Akun ini tidak memiliki peran atau akses workspace untuk aksi H4 tersebut.");
  } else if (error instanceof ApiError) {
    setError(releaseErrorMessage(error.detail));
  } else if (error instanceof Error) {
    setError(error.message);
  } else {
    setError("Permintaan H4 tidak dapat diproses.");
  }
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { GovernanceConfirmationModal, GovernanceFeedback, GovernanceNavigation, type Confirmation } from "@/components/governance-control-ui";
import { ApiError, apiRequest as api } from "@/lib/api-client";
import type { AgentRecord } from "@/lib/agent-registry";
import { normalizeGovernanceError, type GovernanceUiError } from "@/lib/governance-errors";
import { formatDateTime, type SessionActor, type Workspace } from "@/lib/governance";
import {
  canApproveRelease, canCheckRelease, canDesignAgent, canMakeRelease, canOperateKillSwitch,
  canReadReleaseRegistry, canReviewGate, defaultTestForm, designerPayload, draftAgents,
  latestRunByTestCase, mayAmendReleaseDraft, releaseNextAction, releaseProgress,
  releaseTestCategories, testCasePayload, type DesignerResult, type ReleaseRequest,
  type ReleaseRequestDetail, type ReleaseWorkspaceView, type TestCategory,
} from "@/lib/release-governance";

type ReleaseData = { actor: SessionActor; workspaces: Workspace[]; agents: AgentRecord[]; requests: ReleaseRequest[] };
type ReleaseFoundation = Pick<ReleaseData, "actor" | "workspaces">;
const views: Array<{ key: ReleaseWorkspaceView; label: string }> = [
  { key: "request", label: "Release Request" }, { key: "tests", label: "Test & Evidence" },
  { key: "reviews", label: "Reviews & Approval" }, { key: "safety", label: "Kill Switch & Rollback" },
  { key: "history", label: "Audit History" },
];

export function ReleaseGovernance() {
  const router = useRouter();
  const [data, setData] = useState<ReleaseData | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [detail, setDetail] = useState<ReleaseRequestDetail | null>(null);
  const [view, setView] = useState<ReleaseWorkspaceView>("request");
  const [designer, setDesigner] = useState({ requirement: "", agentKey: "", name: "", parentAgentKey: "" });
  const [releaseAgentKey, setReleaseAgentKey] = useState("");
  const [releaseRequirement, setReleaseRequirement] = useState("");
  const [testForm, setTestForm] = useState(defaultTestForm());
  const [editingTestKey, setEditingTestKey] = useState<string | null>(null);
  const [review, setReview] = useState({ decision: "APPROVED", notes: "" });
  const [control, setControl] = useState({ reason: "", rollbackTarget: "" });
  const [error, setError] = useState<GovernanceUiError | null>(null);
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  const loadWorkspace = useCallback(async (nextWorkspaceId: string, base?: ReleaseFoundation) => {
    const foundation = base ?? await loadFoundation();
    const [agents, requests] = await Promise.all([
      canReadReleaseRegistry(foundation.actor.roles) ? api<AgentRecord[]>(`/api/v1/agents?workspace_id=${encodeURIComponent(nextWorkspaceId)}`) : Promise.resolve([]),
      api<ReleaseRequest[]>(`/api/v1/release-requests?workspace_id=${encodeURIComponent(nextWorkspaceId)}`),
    ]);
    setData({ ...foundation, agents, requests });
  }, []);

  const loadDetail = useCallback(async (requestId: string) => {
    if (!requestId) { setDetail(null); return; }
    const nextDetail = await api<ReleaseRequestDetail>(`/api/v1/release-requests/${encodeURIComponent(requestId)}`);
    setDetail(nextDetail); setEditingTestKey(null); setTestForm(defaultTestForm("POSITIVE", nextDetail.agent_key));
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const foundation = await loadFoundation();
        if (foundation.workspaces.length === 0) {
          setError({ title: "Workspace belum tersedia", reason: "Akun ini belum memiliki workspace aktif.", nextAction: "Minta Administrator memberi akses workspace.", status: null, correlationId: null });
          return;
        }
        const first = foundation.workspaces[0].workspace_id; setWorkspaceId(first); await loadWorkspace(first, foundation);
      } catch (loadError: unknown) { handleError(loadError, setError, router); }
      finally { setLoading(false); }
    }
    void initialize();
  }, [loadWorkspace, router]);

  const drafts = useMemo(() => draftAgents(data?.agents ?? []), [data?.agents]);
  const selectedDraft = drafts.find((agent) => agent.agent_key === releaseAgentKey);
  const latestTestRuns = useMemo(() => latestRunByTestCase(detail?.test_runs ?? []), [detail?.test_runs]);
  const reviewGate = canReviewGate(data?.actor.roles ?? []);
  const nextAction = detail && data ? releaseNextAction(detail, data.actor.roles) : null;
  const progress = detail ? releaseProgress(detail.state) : null;
  const mayAmend = Boolean(detail && data && mayAmendReleaseDraft(detail, data.actor.user_id));

  async function selectWorkspace(nextWorkspaceId: string) {
    setWorkspaceId(nextWorkspaceId); setSelectedRequestId(""); setDetail(null); setReleaseAgentKey(""); setError(null); setNotice(""); setLoading(true);
    try { await loadWorkspace(nextWorkspaceId, data ? { actor: data.actor, workspaces: data.workspaces } : undefined); }
    catch (loadError: unknown) { handleError(loadError, setError, router); }
    finally { setLoading(false); }
  }

  async function selectRequest(requestId: string) {
    setSelectedRequestId(requestId); setError(null); setNotice("");
    try { await loadDetail(requestId); } catch (loadError: unknown) { handleError(loadError, setError, router); }
  }

  async function refreshRequest(requestId: string) {
    if (!data || !workspaceId) return;
    await loadWorkspace(workspaceId, { actor: data.actor, workspaces: data.workspaces });
    setSelectedRequestId(requestId); await loadDetail(requestId);
  }

  async function createDesignerDraft() {
    if (!data || !workspaceId) return;
    setWorking(true); setError(null); setNotice("");
    try {
      const result = await api<DesignerResult>("/api/v1/designer/agent-drafts", { method: "POST", body: JSON.stringify(designerPayload({ workspaceId, ...designer })) });
      await loadWorkspace(workspaceId, { actor: data.actor, workspaces: data.workspaces }); setReleaseAgentKey(result.draft.agent_key);
      setNotice(`DRAFT ${result.draft.agent_key} versi ${result.draft.semantic_version} dibuat. Agent belum aktif dan tetap memerlukan test serta approval manusia.`);
    } catch (actionError: unknown) { handleError(actionError, setError, router); }
    finally { setWorking(false); }
  }

  async function createReleaseRequest() {
    if (!data || !workspaceId || !selectedDraft) return;
    setWorking(true); setError(null); setNotice("");
    try {
      if (releaseRequirement.trim().length < 20) throw new Error("Requirement release minimal 20 karakter.");
      const result = await api<ReleaseRequest>(`/api/v1/agents/${encodeURIComponent(selectedDraft.agent_key)}/release-requests`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, requirement: releaseRequirement.trim() }) });
      await refreshRequest(result.change_request_id); setNotice(`Release request ${result.agent_key} dibuat sebagai DRAFT dan dicatat pada audit trail.`);
    } catch (actionError: unknown) { handleError(actionError, setError, router); }
    finally { setWorking(false); }
  }

  async function registerTestCase() {
    if (!detail) return;
    setWorking(true); setError(null); setNotice("");
    try {
      const payload = testCasePayload(testForm); const amended = Boolean(editingTestKey);
      await api(`/api/v1/release-requests/${detail.change_request_id}/test-cases${editingTestKey ? `/${encodeURIComponent(editingTestKey)}` : ""}`, { method: editingTestKey ? "PUT" : "POST", body: JSON.stringify(payload) });
      await refreshRequest(detail.change_request_id); setTestForm(defaultTestForm(testForm.category, detail.agent_key)); setEditingTestKey(null);
      setNotice(amended ? `Test case ${payload.test_key} diperbarui. Evidence historis tetap utuh.` : `Test case ${payload.test_key} terdaftar dan diaudit.`);
    } catch (actionError: unknown) { handleError(actionError, setError, router); }
    finally { setWorking(false); }
  }

  function repairTestCase(testCase: ReleaseRequestDetail["test_cases"][number]) {
    setEditingTestKey(testCase.test_key); setTestForm({ ...defaultTestForm(testCase.category, detail?.agent_key), testKey: testCase.test_key }); setError(null);
    setNotice(`Template aman ${testCase.test_key} dimuat. Simpan lalu minta Checker menjalankan ulang.`);
  }

  async function runAction(path: string, body: Record<string, string> | undefined, success: string) {
    if (!detail) return;
    setWorking(true); setError(null); setNotice("");
    try {
      const result = await api<ReleaseRequest>(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
      await refreshRequest(result.change_request_id); setNotice(success);
    } catch (actionError: unknown) { handleError(actionError, setError, router); }
    finally { setWorking(false); }
  }

  function executeTest(testKey: string) { if (detail) void runAction(`/api/v1/release-requests/${detail.change_request_id}/test-cases/${encodeURIComponent(testKey)}/execute`, undefined, `Test ${testKey} selesai; hasil dan run ID tersimpan sebagai evidence.`); }
  function submitReview() { if (detail) void runAction(`/api/v1/release-requests/${detail.change_request_id}/submit-review`, undefined, "Seluruh evidence dikirim ke review manusia."); }
  function recordReview() { if (detail && reviewGate) void runAction(`/api/v1/release-requests/${detail.change_request_id}/reviews`, { gate: reviewGate, decision: review.decision, notes: review.notes.trim() }, `${reviewGate} review tercatat dan tidak dapat dihapus.`); }
  function requestControlAction(path: string, title: string, impact: string, success: string, body?: Record<string, string>, destructive = false) {
    if (!detail) return;
    setConfirmation({ title, impact, confirmLabel: title, destructive, onConfirm: () => { setConfirmation(null); void runAction(`/api/v1/release-requests/${detail.change_request_id}/${path}`, body, success); } });
  }
  async function logout() { await api<void>("/api/v1/auth/logout", { method: "POST" }); window.location.assign(new URL("/login", window.location.origin).href); }

  if (loading && !data) return <main className="loading-shell">Memuat Release Governance…</main>;
  if (!data) return <main className="loading-shell"><GovernanceFeedback error={error} notice="" /><Link className="text-link" href="/login">Ke halaman login</Link></main>;

  return <main className="release-shell">
    <header className="dashboard-header registry-header"><div><p className="eyebrow">ALOS / GOVERNANCE / AGENT CONTROL</p><h1>Release, Test &amp; Review</h1><p className="muted">Control center berotorisasi. Tidak ada prompt yang dapat melewati test, SoD, approval, atau audit.</p></div><div className="header-actions"><span className="role-badge">{data.actor.roles.join(" · ")}</span><button className="secondary-button" onClick={() => void logout()} type="button">Keluar</button></div></header>
    <GovernanceNavigation active="releases" />
    <nav className="governance-subnav" aria-label="Area kerja release">{views.map((item) => <button aria-current={view === item.key ? "page" : undefined} className={view === item.key ? "active" : ""} key={item.key} onClick={() => setView(item.key)} type="button">{item.label}</button>)}</nav>
    <section className="workspace-bar registry-workspace"><div><label htmlFor="release-workspace">Workspace aktif</label><select id="release-workspace" onChange={(event) => void selectWorkspace(event.target.value)} value={workspaceId}>{data.workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name} · {workspace.workspace_key}</option>)}</select></div><p>Maker, Checker, Business Reviewer, Technical Reviewer, dan Approver harus memenuhi separation of duties.</p></section>
    <GovernanceFeedback error={error} notice={notice} onDismiss={() => setError(null)} />
    <section className="release-grid">
      <article className="panel release-list-panel"><div className="panel-heading"><div><p className="eyebrow">RELEASE REQUESTS</p><h2>{data.requests.length} Request</h2></div><span className="permission-readonly">Immutable history</span></div><ol className="agent-list">{data.requests.map((request) => <li key={request.change_request_id}><button className={selectedRequestId === request.change_request_id ? "agent-row selected" : "agent-row"} onClick={() => void selectRequest(request.change_request_id)} type="button"><span className="agent-level">REL</span><span><strong>{request.agent_key}</strong><small>{request.semantic_version} · Maker tercatat</small></span><span className={`lifecycle-pill lifecycle-${request.state.toLowerCase()}`}>{request.state}</span></button></li>)}</ol>{data.requests.length === 0 ? <p className="empty-state">Belum ada request. IT Lead dapat membuat Agent DRAFT, lalu Maker membuka release request.</p> : null}</article>
      <section className="release-content">
        {detail ? <article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="eyebrow">STATUS &amp; NEXT ACTION</p><h2>{detail.agent_key} · {detail.semantic_version}</h2></div><span className={`lifecycle-pill lifecycle-${detail.state.toLowerCase()}`}>{detail.state}</span></div><div className="release-progress"><span style={{ width: `${progress?.percent ?? 0}%` }} /></div><p className="field-note">Tahap {progress?.current} dari {progress?.total} · lifecycle history tetap append-only.</p><button className="next-action-card" onClick={() => nextAction && setView(nextAction.view)} type="button"><strong>{nextAction?.title}</strong><span>{nextAction?.reason}</span><small>Buka area terkait →</small></button></article> : null}
        {view === "request" ? <RequestView data={data} designer={designer} drafts={drafts} detail={detail} releaseAgentKey={releaseAgentKey} releaseRequirement={releaseRequirement} selectedDraft={selectedDraft} working={working} setDesigner={setDesigner} setReleaseAgentKey={setReleaseAgentKey} setReleaseRequirement={setReleaseRequirement} createDesignerDraft={createDesignerDraft} createReleaseRequest={createReleaseRequest} /> : null}
        {view === "tests" ? detail ? <TestsView data={data} detail={detail} editingTestKey={editingTestKey} latestTestRuns={latestTestRuns} mayAmend={mayAmend} testForm={testForm} working={working} setEditingTestKey={setEditingTestKey} setTestForm={setTestForm} executeTest={executeTest} registerTestCase={registerTestCase} repairTestCase={repairTestCase} submitReview={submitReview} /> : <SelectRequest /> : null}
        {view === "reviews" ? detail ? <ReviewsView data={data} detail={detail} review={review} reviewGate={reviewGate} working={working} setReview={setReview} recordReview={recordReview} requestControlAction={requestControlAction} /> : <SelectRequest /> : null}
        {view === "safety" ? detail ? <SafetyView data={data} detail={detail} control={control} working={working} setControl={setControl} requestControlAction={requestControlAction} /> : <SelectRequest /> : null}
        {view === "history" ? detail ? <HistoryView detail={detail} /> : <SelectRequest /> : null}
      </section>
    </section>
    <GovernanceConfirmationModal busy={working} confirmation={confirmation} onCancel={() => setConfirmation(null)} />
  </main>;
}

type RequestViewProps = { data: ReleaseData; designer: { requirement: string; agentKey: string; name: string; parentAgentKey: string }; drafts: AgentRecord[]; detail: ReleaseRequestDetail | null; releaseAgentKey: string; releaseRequirement: string; selectedDraft: AgentRecord | undefined; working: boolean; setDesigner: React.Dispatch<React.SetStateAction<RequestViewProps["designer"]>>; setReleaseAgentKey: (value: string) => void; setReleaseRequirement: (value: string) => void; createDesignerDraft: () => Promise<void>; createReleaseRequest: () => Promise<void> };
function RequestView({ data, designer, drafts, detail, releaseAgentKey, releaseRequirement, selectedDraft, working, setDesigner, setReleaseAgentKey, setReleaseRequirement, createDesignerDraft, createReleaseRequest }: RequestViewProps) {
  return <><article className="panel designer-panel"><div className="panel-heading"><div><p className="eyebrow">GENESIS DESIGNER</p><h2>Natural language → Agent DRAFT</h2></div><span className="permission-ok">IT Lead</span></div>{canDesignAgent(data.actor.roles) ? <><label>Requirement bahasa natural<textarea minLength={20} onChange={(event) => setDesigner((value) => ({ ...value, requirement: event.target.value }))} placeholder="Buat Agent read-only untuk memonitor task overdue dan evidence yang belum lengkap." rows={4} value={designer.requirement} /></label><div className="builder-fields two-column-fields compact-fields"><label>Agent key (opsional)<input onChange={(event) => setDesigner((value) => ({ ...value, agentKey: event.target.value }))} value={designer.agentKey} /></label><label>Nama Agent (opsional)<input onChange={(event) => setDesigner((value) => ({ ...value, name: event.target.value }))} value={designer.name} /></label></div><p className="field-note">Output selalu DRAFT. GENESIS tidak dapat memberi permission, menyetujui, atau mengaktifkan dirinya sendiri.</p><div className="builder-actions"><button disabled={working || designer.requirement.trim().length < 20} onClick={() => void createDesignerDraft()} type="button">{working ? "Membuat DRAFT…" : "Buat Agent DRAFT"}</button></div></> : <p className="safe-note">Role Anda tidak dapat membuat Agent. Tindakan berikutnya: minta IT Lead membuat DRAFT.</p>}</article>
    <article className="panel release-start-panel"><div className="panel-heading"><div><p className="eyebrow">MAKER</p><h2>Buka Release Request</h2></div><span className="permission-ok">Draft only</span></div>{canMakeRelease(data.actor.roles) && canReadReleaseRegistry(data.actor.roles) ? <><div className="builder-fields two-column-fields"><label>Agent DRAFT<select onChange={(event) => setReleaseAgentKey(event.target.value)} value={releaseAgentKey}><option value="">Pilih DRAFT</option>{drafts.map((agent) => <option key={agent.agent_key} value={agent.agent_key}>{agent.name} · {agent.versions[0]?.semantic_version}</option>)}</select></label><label>Requirement release<textarea minLength={20} onChange={(event) => setReleaseRequirement(event.target.value)} placeholder="Outcome, scope, dan batas release internal." rows={4} value={releaseRequirement} /></label></div><div className="builder-actions"><button disabled={working || !selectedDraft || releaseRequirement.trim().length < 20} onClick={() => void createReleaseRequest()} type="button">{working ? "Membuka request…" : "Buka request DRAFT"}</button></div></> : <p className="safe-note">Pembuatan request dari Registry tersedia untuk IT Lead. Reviewer dan Approver hanya menjalankan aksi sesuai perannya.</p>}</article>
    {detail ? <ReleaseSummary detail={detail} /> : <SelectRequest />}</>;
}

type TestsViewProps = { data: ReleaseData; detail: ReleaseRequestDetail; editingTestKey: string | null; latestTestRuns: Map<string, ReleaseRequestDetail["test_runs"][number]>; mayAmend: boolean; testForm: ReturnType<typeof defaultTestForm>; working: boolean; setEditingTestKey: (value: string | null) => void; setTestForm: React.Dispatch<React.SetStateAction<ReturnType<typeof defaultTestForm>>>; executeTest: (key: string) => void; registerTestCase: () => Promise<void>; repairTestCase: (test: ReleaseRequestDetail["test_cases"][number]) => void; submitReview: () => void };
function TestsView({ data, detail, editingTestKey, latestTestRuns, mayAmend, testForm, working, setEditingTestKey, setTestForm, executeTest, registerTestCase, repairTestCase, submitReview }: TestsViewProps) {
  return <article className="panel test-registry-panel"><div className="panel-heading"><div><p className="eyebrow">TEST &amp; EVIDENCE</p><h2>Expected dibanding actual runtime</h2></div><span className="permission-readonly">History immutable</span></div>{mayAmend ? <><div className="builder-fields two-column-fields compact-fields"><label>Kategori<select disabled={Boolean(editingTestKey)} onChange={(event) => setTestForm(defaultTestForm(event.target.value as TestCategory, detail.agent_key))} value={testForm.category}>{releaseTestCategories.map((category) => <option key={category}>{category}</option>)}</select></label><label>Test key<input disabled={Boolean(editingTestKey)} onChange={(event) => setTestForm((form) => ({ ...form, testKey: event.target.value }))} value={testForm.testKey} /></label><label className="full-width">Fixture JSON<textarea className="code-input" onChange={(event) => setTestForm((form) => ({ ...form, fixture: event.target.value }))} rows={7} value={testForm.fixture} /></label><label>Expected status<select onChange={(event) => setTestForm((form) => ({ ...form, expectedStatus: event.target.value }))} value={testForm.expectedStatus}><option>SUCCEEDED</option><option>FAILED</option><option>BLOCKED</option></select></label></div><div className="builder-actions"><button disabled={working} onClick={() => void registerTestCase()} type="button">{working ? "Menyimpan…" : editingTestKey ? "Simpan perbaikan" : "Tambah test case"}</button>{editingTestKey ? <button className="secondary-button" onClick={() => setEditingTestKey(null)} type="button">Batal</button> : null}</div></> : <p className="field-note">Test case hanya dapat diubah oleh Maker saat DRAFT/RETURNED. Evidence run tidak dapat diubah atau dihapus.</p>}<div className="table-wrap evidence-table"><table><thead><tr><th>Kategori / Test</th><th>Expected</th><th>Actual / Result</th><th>Evidence</th><th>Aksi</th></tr></thead><tbody>{detail.test_cases.map((testCase) => { const result = latestTestRuns.get(testCase.test_case_id); return <tr key={testCase.test_case_id}><td><strong>{testCase.category}</strong><br /><small>{testCase.test_key}</small></td><td>{String(testCase.expected_assertions.status ?? "—")}</td><td>{result ? <><span className={`test-result test-${result.status.toLowerCase()}`}>{result.status}</span><br /><small>{result.actual_status ?? "Actual status tidak tersedia"}{result.error_code ? ` · ${result.error_code}` : ""}</small></> : "Belum dijalankan"}</td><td>{result ? <small>Run: {result.agent_run_id?.slice(0, 8) ?? "—"}<br />Ref: {result.correlation_id.slice(0, 8)}<br />{result.completed_at ? formatDateTime(result.completed_at) : "Belum selesai"}</small> : "—"}</td><td>{mayAmend ? <button className="secondary-button" disabled={working} onClick={() => repairTestCase(testCase)} type="button">Perbaiki</button> : null}{canCheckRelease(data.actor.roles) && ["DRAFT", "RETURNED"].includes(detail.state) ? <button disabled={working} onClick={() => executeTest(testCase.test_key)} type="button">Jalankan</button> : null}</td></tr>; })}</tbody></table></div>{detail.test_cases.length === 0 ? <p className="empty-state">Maker belum mendaftarkan test. Minimal lima kategori wajib tersedia.</p> : null}{canCheckRelease(data.actor.roles) && ["DRAFT", "RETURNED"].includes(detail.state) ? <div className="builder-actions"><button disabled={working || detail.test_cases.length < 5} onClick={submitReview} title={detail.test_cases.length < 5 ? "Minimal lima kategori test harus tersedia." : undefined} type="button">Kirim evidence untuk review</button></div> : <p className="safe-note">Next action: Checker independen menjalankan test dan mengirim evidence.</p>}</article>;
}

type ControlAction = (path: string, title: string, impact: string, success: string, body?: Record<string, string>, destructive?: boolean) => void;
function ReviewsView({ data, detail, review, reviewGate, working, setReview, recordReview, requestControlAction }: { data: ReleaseData; detail: ReleaseRequestDetail; review: { decision: string; notes: string }; reviewGate: "BUSINESS" | "TECHNICAL" | null; working: boolean; setReview: React.Dispatch<React.SetStateAction<{ decision: string; notes: string }>>; recordReview: () => void; requestControlAction: ControlAction }) {
  return <article className="panel review-panel"><div className="panel-heading"><div><p className="eyebrow">REVIEWS &amp; APPROVAL</p><h2>Gate manusia terpisah</h2></div><span className="permission-readonly">No self-approval</span></div><div className="review-gates"><ReviewGateCard gate="BUSINESS" reviews={detail.reviews} /><ReviewGateCard gate="TECHNICAL" reviews={detail.reviews} /><div><span>FINAL APPROVAL</span><strong>{detail.approver_user_id ? "APPROVER TERCATAT" : "PENDING"}</strong><small>Hanya Director berwenang dan tetap tunduk pada SoD.</small></div></div>{detail.state === "IN_REVIEW" && reviewGate ? <div className="builder-fields two-column-fields compact-fields"><label>Gate<input disabled value={reviewGate} /></label><label>Keputusan<select onChange={(event) => setReview((value) => ({ ...value, decision: event.target.value }))} value={review.decision}><option>APPROVED</option><option>RETURNED</option><option>REJECTED</option></select></label><label className="full-width">Catatan wajib<textarea onChange={(event) => setReview((value) => ({ ...value, notes: event.target.value }))} rows={3} value={review.notes} /></label><div className="builder-actions full-width"><button disabled={working || !review.notes.trim()} onClick={recordReview} type="button">Catat review {reviewGate}</button></div></div> : null}{!reviewGate && detail.state === "IN_REVIEW" ? <p className="safe-note">Next action: Business Reviewer dan Technical Reviewer independen menyelesaikan review.</p> : null}<div className="builder-actions">{detail.state === "IN_REVIEW" && canApproveRelease(data.actor.roles) ? <button disabled={working} onClick={() => requestControlAction("approve", "Approve release", "Merekam persetujuan final setelah seluruh gate manusia lengkap.", "Request disetujui dan diaudit.")} type="button">Approve</button> : null}{detail.state === "APPROVED" && canApproveRelease(data.actor.roles) ? <button disabled={working} onClick={() => requestControlAction("release", "Release ke staging", "Menandai versi siap di staging internal; Agent belum otomatis ACTIVE.", "Versi dirilis ke staging internal.")} type="button">Release</button> : null}{detail.state === "RELEASED" && canApproveRelease(data.actor.roles) ? <button disabled={working || detail.kill_switch_active} onClick={() => requestControlAction("activate", "Aktifkan Agent", "Agent mulai dapat dijalankan sesuai kontrak, permission, budget, dan policy.", "Versi aktif setelah approval manusia.")} type="button">Activate</button> : null}</div><div className="table-wrap"><table><thead><tr><th>Gate</th><th>Keputusan</th><th>Catatan</th><th>Waktu</th></tr></thead><tbody>{detail.reviews.map((item) => <tr key={`${item.review_gate}-${item.created_at}`}><td>{item.review_gate}</td><td>{item.decision}</td><td>{item.notes}</td><td>{formatDateTime(item.created_at)}</td></tr>)}</tbody></table></div></article>;
}

function SafetyView({ data, detail, control, working, setControl, requestControlAction }: { data: ReleaseData; detail: ReleaseRequestDetail; control: { reason: string; rollbackTarget: string }; working: boolean; setControl: React.Dispatch<React.SetStateAction<{ reason: string; rollbackTarget: string }>>; requestControlAction: ControlAction }) {
  return <article className="panel safety-controls-panel"><div className="panel-heading"><div><p className="eyebrow">SAFETY CONTROL</p><h2>Kill Switch, Suspend &amp; Rollback</h2></div><span className={detail.kill_switch_active ? "danger-status" : "permission-ok"}>{detail.kill_switch_active ? "KILL SWITCH ACTIVE" : "Monitoring"}</span></div><p className="muted">Semua aksi memerlukan alasan, menampilkan dampak sebelum konfirmasi, dan menghasilkan audit record permanen.</p><div className="builder-fields two-column-fields"><label>Alasan wajib<textarea onChange={(event) => setControl((value) => ({ ...value, reason: event.target.value }))} placeholder="Kondisi, dampak, dan dasar tindakan." rows={4} value={control.reason} /></label><label>Target rollback<select onChange={(event) => setControl((value) => ({ ...value, rollbackTarget: event.target.value }))} value={control.rollbackTarget}><option value="">Pilih versi terdahulu</option>{detail.rollback_targets.map((target) => <option key={target}>{target}</option>)}</select><span className="field-note">Rollback target berasal dari versi Registry yang sudah tersimpan.</span></label></div>{!canOperateKillSwitch(data.actor.roles) ? <p className="safe-note">Role Anda read-only untuk emergency control. Hubungi Director atau IT Lead.</p> : null}<div className="builder-actions">{["ACTIVE", "RELEASED"].includes(detail.state) && canApproveRelease(data.actor.roles) ? <button className="secondary-button" disabled={working || !control.reason.trim()} onClick={() => requestControlAction("suspend", "Suspend Agent", "Menghentikan penggunaan Agent tanpa menghapus kontrak atau history.", "Agent disuspensi dan diaudit.", { reason: control.reason.trim() }, true)} type="button">Suspend</button> : null}{canOperateKillSwitch(data.actor.roles) && !detail.kill_switch_active ? <button className="danger-button" disabled={working || !control.reason.trim()} onClick={() => requestControlAction("kill-switch", "Aktifkan Kill Switch", "Menghentikan Agent segera. Aktivasi diblokir sampai kontrol dibersihkan.", "Kill switch aktif dan Agent dihentikan.", { reason: control.reason.trim() }, true)} type="button">Aktifkan Kill Switch</button> : null}{detail.kill_switch_active && canOperateKillSwitch(data.actor.roles) ? <button className="secondary-button" disabled={working || !control.reason.trim()} onClick={() => requestControlAction("clear-kill-switch", "Clear Kill Switch", "Membuka kembali jalur lifecycle setelah penyebab penghentian diverifikasi.", "Kill switch dibersihkan secara eksplisit.", { reason: control.reason.trim() })} type="button">Clear Kill Switch</button> : null}{["ACTIVE", "SUSPENDED"].includes(detail.state) && canApproveRelease(data.actor.roles) ? <button disabled={working || !control.reason.trim() || !control.rollbackTarget} onClick={() => requestControlAction("rollback", "Rollback versi", `Mengaktifkan kembali versi ${control.rollbackTarget || "yang dipilih"}.`, "Rollback selesai dan diaudit.", { reason: control.reason.trim(), target_semantic_version: control.rollbackTarget }, true)} type="button">Rollback</button> : null}</div></article>;
}

function HistoryView({ detail }: { detail: ReleaseRequestDetail }) { return <article className="panel lifecycle-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">APPEND-ONLY AUDIT</p><h2>Lifecycle History</h2></div><span className="permission-readonly">Read-only</span></div><ol className="audit-list">{detail.lifecycle_events.map((event) => <li key={event.event_sequence}><strong>{event.from_state ?? "—"} → {event.to_state}</strong><span>{event.reason}</span><code>Correlation: {event.correlation_id}</code><time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time></li>)}</ol></article>; }
function ReleaseSummary({ detail }: { detail: ReleaseRequestDetail }) { return <article className="panel"><div className="panel-heading"><div><p className="eyebrow">REQUEST SUMMARY</p><h2>Scope dan kontrol</h2></div><span className="permission-readonly">Audited</span></div><p className="safe-note">{detail.requirement}</p><dl className="review-list"><div><dt>Agent / version</dt><dd>{detail.agent_key} · {detail.semantic_version}</dd></div><div><dt>Maker</dt><dd>{detail.maker_user_id}</dd></div><div><dt>Checker</dt><dd>{detail.checker_user_id ?? "Belum ditetapkan"}</dd></div><div><dt>Approver</dt><dd>{detail.approver_user_id ?? "Belum tercatat"}</dd></div><div><dt>Kill switch</dt><dd>{detail.kill_switch_active ? "ACTIVE" : "Tidak aktif"}</dd></div></dl></article>; }
function ReviewGateCard({ gate, reviews }: { gate: "BUSINESS" | "TECHNICAL"; reviews: ReleaseRequestDetail["reviews"] }) { const result = reviews.find((item) => item.review_gate === gate); return <div><span>{gate} REVIEW</span><strong>{result?.decision ?? "PENDING"}</strong><small>{result ? result.notes : "Menunggu reviewer independen."}</small></div>; }
function SelectRequest() { return <article className="panel"><p className="empty-state">Pilih release request untuk membuka area kontrol ini.</p></article>; }
async function loadFoundation(): Promise<ReleaseFoundation> { const [actor, workspaces] = await Promise.all([api<SessionActor>("/api/v1/whoami"), api<Workspace[]>("/api/v1/workspaces")]); return { actor, workspaces }; }
function handleError(error: unknown, setError: (message: GovernanceUiError | null) => void, router: ReturnType<typeof useRouter>) { if (error instanceof ApiError && error.status === 401) router.replace("/login"); setError(normalizeGovernanceError(error)); }

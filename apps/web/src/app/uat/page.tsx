"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  createUatRun,
  getGoLiveReadiness,
  getUatRuns,
  recordUatScenario,
  signoffUatRun,
  startUatRun,
} from "@/lib/api";
import { formatDateTime, humanizeCode } from "@/lib/format";
import type {
  PilotReadinessReport,
  UatRun,
  UatScenarioResult,
  UatScenarioStatus,
  UatSignoffScope,
} from "@/lib/types";

const divisionScopes: UatSignoffScope[] = [
  "SALES_MARKETING",
  "FINANCE",
  "PROPERTY",
  "HR",
  "LEGAL",
];

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Data UAT belum dapat diproses.";
}

function signerScopes(
  roles: string[],
  divisions: string[],
): UatSignoffScope[] {
  const scopes: UatSignoffScope[] = [];
  if (roles.includes("DIRECTOR")) scopes.push("DIRECTOR");
  if (roles.includes("AI_EXECUTIVE")) scopes.push("AI_EXECUTIVE");
  if (roles.includes("IT_ADMIN") && divisions.includes("IT")) scopes.push("IT");
  if (roles.includes("DIVISION_HEAD")) {
    divisionScopes.forEach((scope) => {
      if (divisions.includes(scope)) scopes.push(scope);
    });
  }
  return scopes;
}

export default function UatPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const [runs, setRuns] = useState<UatRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [gate, setGate] = useState<PilotReadinessReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [runTitle, setRunTitle] = useState("Siklus UAT Controlled Pilot");
  const [resultForm, setResultForm] = useState({
    status: "PASSED" as UatScenarioStatus,
    actualResult: "",
    defectSeverity: "LOW" as "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
    defectSummary: "",
    evidenceReference: "",
  });
  const [signoffForm, setSignoffForm] = useState({
    scope: "" as UatSignoffScope | "",
    decision: "ACCEPTED" as "ACCEPTED" | "ACCEPTED_WITH_RISK" | "REJECTED",
    riskSeverity: "LOW" as "LOW" | "MEDIUM",
    notes: "",
  });

  const load = useCallback(async () => {
    if (!token || !activeProjectId) {
      setRuns([]);
      setGate(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [runItems, readiness] = await Promise.all([
        getUatRuns(token, activeProjectId),
        getGoLiveReadiness(token, activeProjectId),
      ]);
      setRuns(runItems);
      setGate(readiness);
      setSelectedRunId((current) => (
        current && runItems.some((item) => item.uat_run_id === current)
          ? current
          : runItems[0]?.uat_run_id || null
      ));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const task = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(task);
  }, [load, status]);

  const selectedRun = useMemo(
    () => runs.find((item) => item.uat_run_id === selectedRunId) || runs[0] || null,
    [runs, selectedRunId],
  );
  const selectedScenario = useMemo(
    () => selectedRun?.scenarios.find((item) => item.scenario_id === selectedScenarioId)
      || selectedRun?.scenarios[0]
      || null,
    [selectedRun, selectedScenarioId],
  );

  const canManageRun = Boolean(
    principal?.roles.some((role) => role === "DIRECTOR" || role === "IT_ADMIN"),
  );
  const canRecordScenario = Boolean(
    (selectedRun?.status === "IN_PROGRESS"
      || (selectedRun?.status === "READY_FOR_SIGNOFF" && selectedRun.signoffs.length === 0))
    && selectedScenario
    && principal?.roles.some((role) => selectedScenario.allowed_roles.includes(role))
    && (!selectedScenario.division_code
      || principal?.division_codes.includes(selectedScenario.division_code)),
  );
  const availableSignoffScopes = useMemo(() => {
    if (!principal || !selectedRun) return [];
    const completed = new Set(selectedRun.signoffs.map((item) => item.signoff_scope));
    return signerScopes(principal.roles, principal.division_codes)
      .filter((scope) => !completed.has(scope));
  }, [principal, selectedRun]);
  const selectedSignoffScope = availableSignoffScopes.includes(signoffForm.scope as UatSignoffScope)
    ? signoffForm.scope as UatSignoffScope
    : availableSignoffScopes[0] || "";

  function replaceRun(next: UatRun) {
    setRuns((current) => {
      const exists = current.some((item) => item.uat_run_id === next.uat_run_id);
      return exists
        ? current.map((item) => item.uat_run_id === next.uat_run_id ? next : item)
        : [next, ...current];
    });
    setSelectedRunId(next.uat_run_id);
  }

  function chooseScenario(scenario: UatScenarioResult) {
    setSelectedScenarioId(scenario.scenario_id);
    setResultForm({
      status: scenario.status === "NOT_STARTED" ? "PASSED" : scenario.status,
      actualResult: scenario.actual_result || "",
      defectSeverity: scenario.defect_severity || "LOW",
      defectSummary: scenario.defect_summary || "",
      evidenceReference: scenario.evidence[0]?.reference || "",
    });
  }

  async function submitRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canManageRun) return;
    setBusy(true);
    setFeedback(null);
    try {
      const created = await createUatRun(token, activeProjectId, runTitle.trim());
      replaceRun(created);
      setFeedback("Siklus UAT dibuat sebagai DRAFT. Mulai setelah tim dan data uji siap.");
    } catch (requestError) {
      setFeedback(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function startRun() {
    if (!token || !selectedRun || !canManageRun) return;
    setBusy(true);
    setFeedback(null);
    try {
      replaceRun(await startUatRun(token, selectedRun.uat_run_id));
      setFeedback("Siklus UAT dimulai dan siap diisi oleh penguji berwenang.");
    } catch (requestError) {
      setFeedback(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function submitScenario(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedRun || !selectedScenario || !canRecordScenario) return;
    const requiresEvidence = resultForm.status === "PASSED"
      || resultForm.status === "PASSED_WITH_RISK";
    const hasDefect = ["PASSED_WITH_RISK", "FAILED", "BLOCKED"].includes(resultForm.status);
    setBusy(true);
    setFeedback(null);
    try {
      const next = await recordUatScenario(
        token,
        selectedRun.uat_run_id,
        selectedScenario.scenario_id,
        {
          status: resultForm.status,
          actual_result: resultForm.actualResult.trim() || null,
          defect_severity: hasDefect ? resultForm.defectSeverity : null,
          defect_summary: hasDefect ? resultForm.defectSummary.trim() || null : null,
          evidence: requiresEvidence
            ? [{ document_version_id: null, reference: resultForm.evidenceReference.trim() }]
            : [],
        },
      );
      replaceRun(next);
      setFeedback("Hasil, evidence, dan temuan UAT dicatat pada audit trail.");
    } catch (requestError) {
      setFeedback(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function submitSignoff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedRun || !selectedSignoffScope) return;
    setBusy(true);
    setFeedback(null);
    try {
      const next = await signoffUatRun(token, selectedRun.uat_run_id, {
        signoff_scope: selectedSignoffScope,
        decision: signoffForm.decision,
        risk_severity: signoffForm.decision === "ACCEPTED_WITH_RISK"
          ? signoffForm.riskSeverity
          : null,
        notes: signoffForm.notes.trim(),
      });
      replaceRun(next);
      setSignoffForm({ scope: "", decision: "ACCEPTED", riskSeverity: "LOW", notes: "" });
      setFeedback("Keputusan sign-off tersimpan dan tidak dapat ditimpa.");
      if (["ACCEPTED", "ACCEPTED_WITH_RISK", "REJECTED"].includes(next.status)) {
        await load();
      }
    } catch (requestError) {
      setFeedback(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  if (!activeProjectId) {
    return <EmptyState title="Pilih proyek pilot" description="Pilih konteks proyek ACTIVE untuk membuka siklus UAT dan gate go-live." />;
  }

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Controlled pilot acceptance</p><h1>UAT & Go-Live</h1><p>Catat hasil nyata, evidence, defect, dan persetujuan manusia. ALOS tidak dapat menyatakan dirinya lulus tanpa delapan sign-off yang diwajibkan.</p></div><button className="button secondary" disabled={busy} onClick={() => void load()} type="button">Perbarui data</button></header>
      {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
      {loading ? <LoadingState label="Memuat siklus UAT…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {!loading && !error ? <>
        <section className="metricGrid uatMetrics"><article className="metricCard"><div><small>Go-live gate</small><strong>{gate ? humanizeCode(gate.overall_status) : "—"}</strong><p>{gate ? `${gate.blocked_checks} blocker · ${gate.warning_checks} perhatian` : "Belum dievaluasi"}</p></div></article><article className="metricCard"><div><small>Skenario lulus</small><strong>{selectedRun?.scenarios.filter((item) => item.status === "PASSED" || item.status === "PASSED_WITH_RISK").length || 0}/8</strong><p>Evidence wajib untuk setiap kelulusan</p></div></article><article className="metricCard"><div><small>Sign-off manusia</small><strong>{selectedRun?.signoffs.length || 0}/8</strong><p>Business owner, IT, eksekutif, direktur</p></div></article><article className="metricCard"><div><small>Status siklus</small><strong>{selectedRun ? humanizeCode(selectedRun.status) : "—"}</strong><p>{selectedRun ? `Cycle ${selectedRun.cycle_number}` : "Belum ada siklus"}</p></div></article></section>

        {canManageRun ? <section className="panel transactionCreatePanel"><div className="panelHeader"><div><p className="eyebrow">UAT cycle control</p><h2>Buat siklus baru</h2></div><span className="statusBadge">Data sintetis/tersanitasi</span></div><form className="transactionForm" onSubmit={submitRun}><label>Nama siklus<input maxLength={160} minLength={3} onChange={(event) => setRunTitle(event.target.value)} required value={runTitle} /></label><button className="button primary" disabled={busy} type="submit">Buat DRAFT</button></form></section> : null}

        <div className="transactionLayout uatLayout">
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">UAT register</p><h2>Siklus pengujian</h2></div><span className="resultCount">{runs.length} siklus</span></div>{runs.length ? <div className="transactionRecordList">{runs.map((run) => <button className={run.uat_run_id === selectedRun?.uat_run_id ? "selected" : ""} key={run.uat_run_id} onClick={() => { setSelectedRunId(run.uat_run_id); setSelectedScenarioId(null); }} type="button"><span><strong>{run.title}</strong><small>Cycle {run.cycle_number}</small></span><span><b className="statusBadge">{humanizeCode(run.status)}</b><small>{formatDateTime(run.updated_at)}</small></span></button>)}</div> : <EmptyState title="Belum ada siklus UAT" description="IT atau Direktur dapat membuat siklus setelah project setup selesai." />}</section>

          <section className="panel transactionDetail"><div className="panelHeader"><div><p className="eyebrow">Acceptance cycle</p><h2>{selectedRun?.title || "Pilih siklus"}</h2></div>{selectedRun ? <span className="statusBadge large">{humanizeCode(selectedRun.status)}</span> : null}</div>{selectedRun ? <div className="transactionDetailBody">{selectedRun.status === "DRAFT" && canManageRun ? <button className="button primary" disabled={busy} onClick={() => void startRun()} type="button">Mulai UAT</button> : null}<div className="uatScenarioList">{selectedRun.scenarios.map((scenario) => <button className={scenario.scenario_id === selectedScenario?.scenario_id ? "selected" : ""} key={scenario.scenario_id} onClick={() => chooseScenario(scenario)} type="button"><span><b>{scenario.scenario_id}</b><strong>{scenario.title}</strong><small>{scenario.workspace}</small></span><span className="statusBadge">{humanizeCode(scenario.status)}</span></button>)}</div></div> : <EmptyState title="Pilih siklus" description="Pilih siklus untuk melihat skenario dan sign-off." />}</section>
        </div>

        {selectedRun && selectedScenario ? <section className="panel uatScenarioPanel"><div className="panelHeader"><div><p className="eyebrow">{selectedScenario.scenario_id} · {selectedScenario.workspace}</p><h2>{selectedScenario.title}</h2><p>{selectedScenario.objective}</p></div><span className="statusBadge large">{humanizeCode(selectedScenario.status)}</span></div><div className="uatScenarioBody"><div><dl className="detailGrid"><div><dt>Diuji</dt><dd>{formatDateTime(selectedScenario.tested_at)}</dd></div><div><dt>Evidence</dt><dd>{selectedScenario.evidence.length}</dd></div><div><dt>Severity</dt><dd>{selectedScenario.defect_severity ? humanizeCode(selectedScenario.defect_severity) : "—"}</dd></div></dl>{selectedScenario.actual_result ? <div className="readOnlyNotice"><p><strong>Hasil terakhir</strong><span>{selectedScenario.actual_result}</span></p></div> : null}</div>{canRecordScenario ? <form className="actionPanel" onSubmit={submitScenario}><div><p className="eyebrow">Human test record</p><h3>Catat hasil skenario</h3></div><label>Status<select onChange={(event) => setResultForm({ ...resultForm, status: event.target.value as UatScenarioStatus })} value={resultForm.status}><option value="IN_PROGRESS">In progress</option><option value="PASSED">Passed</option><option value="PASSED_WITH_RISK">Passed with risk</option><option value="FAILED">Failed</option><option value="BLOCKED">Blocked</option></select></label><label>Hasil aktual<textarea maxLength={4000} onChange={(event) => setResultForm({ ...resultForm, actualResult: event.target.value })} required={resultForm.status === "PASSED" || resultForm.status === "PASSED_WITH_RISK"} rows={4} value={resultForm.actualResult} /></label>{["PASSED_WITH_RISK", "FAILED", "BLOCKED"].includes(resultForm.status) ? <><label>Severity<select onChange={(event) => setResultForm({ ...resultForm, defectSeverity: event.target.value as typeof resultForm.defectSeverity })} value={resultForm.defectSeverity}><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option></select></label><label>Temuan / risk<textarea maxLength={2000} minLength={8} onChange={(event) => setResultForm({ ...resultForm, defectSummary: event.target.value })} required rows={3} value={resultForm.defectSummary} /></label></> : null}{resultForm.status === "PASSED" || resultForm.status === "PASSED_WITH_RISK" ? <label>Referensi evidence<input maxLength={500} minLength={3} onChange={(event) => setResultForm({ ...resultForm, evidenceReference: event.target.value })} placeholder="Nomor workflow, audit, atau dokumen" required value={resultForm.evidenceReference} /></label> : null}<button className="button primary" disabled={busy} type="submit">Simpan hasil UAT</button></form> : <div className="readOnlyNotice"><p><strong>Mode baca</strong><span>Hanya penguji dengan role dan divisi sesuai yang dapat mencatat hasil sebelum proses sign-off dimulai.</span></p></div>}</div></section> : null}

        {selectedRun ? <section className="panel uatSignoffPanel"><div className="panelHeader"><div><p className="eyebrow">Human acceptance</p><h2>Sign-off wajib</h2><p>Keputusan yang telah disimpan bersifat final untuk siklus ini.</p></div><span className="statusBadge large">{selectedRun.signoffs.length}/8</span></div><div className="uatSignoffGrid">{selectedRun.required_signoff_scopes.map((scope) => { const signoff = selectedRun.signoffs.find((item) => item.signoff_scope === scope); return <article key={scope}><strong>{humanizeCode(scope)}</strong><span className="statusBadge">{signoff ? humanizeCode(signoff.decision) : "Menunggu"}</span><small>{signoff ? `${signoff.signer_role}${signoff.risk_severity ? ` · Risk ${signoff.risk_severity}` : ""} · ${formatDateTime(signoff.signed_at)}` : "Belum ada keputusan"}</small></article>; })}</div>{selectedRun.status === "READY_FOR_SIGNOFF" && availableSignoffScopes.length ? <form className="actionPanel uatSignoffForm" onSubmit={submitSignoff}><label>Scope<select onChange={(event) => setSignoffForm({ ...signoffForm, scope: event.target.value as UatSignoffScope })} value={selectedSignoffScope}>{availableSignoffScopes.map((scope) => <option key={scope} value={scope}>{humanizeCode(scope)}</option>)}</select></label><label>Keputusan<select onChange={(event) => setSignoffForm({ ...signoffForm, decision: event.target.value as typeof signoffForm.decision })} value={signoffForm.decision}><option value="ACCEPTED">Accepted</option><option value="ACCEPTED_WITH_RISK">Accepted with risk</option><option value="REJECTED">Rejected</option></select></label>{signoffForm.decision === "ACCEPTED_WITH_RISK" ? <label>Severity risk<select onChange={(event) => setSignoffForm({ ...signoffForm, riskSeverity: event.target.value as typeof signoffForm.riskSeverity })} value={signoffForm.riskSeverity}><option value="LOW">Low</option><option value="MEDIUM">Medium</option></select></label> : null}<label>Catatan keputusan<textarea maxLength={1000} minLength={8} onChange={(event) => setSignoffForm({ ...signoffForm, notes: event.target.value })} required rows={3} value={signoffForm.notes} /></label><button className="button primary" disabled={busy} type="submit">Simpan sign-off</button></form> : null}</section> : null}
      </> : null}
    </>
  );
}

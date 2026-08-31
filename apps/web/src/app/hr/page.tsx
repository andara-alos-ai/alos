"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  decideRecruitment,
  getDocuments,
  getPersonnelChecklist,
  getRecruitmentRequests,
  submitRecruitmentRequest,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type {
  DocumentRecord,
  PersonnelChecklist,
  RecruitmentRequestRecord,
} from "@/lib/types";

const divisionCodes = ["FINANCE", "SALES_MARKETING", "PROPERTY", "HR", "LEGAL", "IT"];

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi HR belum dapat diproses.";
}

function codes(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean))];
}

export default function HrPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const [requests, setRequests] = useState<RecruitmentRequestRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<PersonnelChecklist | null>(null);
  const [checklistRequestId, setChecklistRequestId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [submission, setSubmission] = useState({
    documentVersionId: "",
    positionTitle: "",
    requestingDivisionCode: "HR",
    employmentType: "CONTRACT" as "PERMANENT" | "CONTRACT" | "INTERNSHIP",
    headcount: "1",
    justification: "",
    criteriaVersion: "0.1.0",
    candidateAlias: "",
    requiredCriteria: "CV, WORK_EXPERIENCE",
    metCriteria: "CV",
  });
  const [decision, setDecision] = useState({
    value: "SELECTED" as "SELECTED" | "REJECTED",
    notes: "",
    personnelRequirements: "IDENTITY_DOCUMENT, BANK_ACCOUNT, TAX_ID",
  });

  const selected = useMemo(
    () => requests.find((request) => request.recruitment_request_id === selectedId) || null,
    [requests, selectedId],
  );
  const visibleChecklist = checklistRequestId === selectedId ? checklist : null;
  const isHrOperator = Boolean(
    principal
    && principal.division_codes.includes("HR")
    && principal.roles.some((role) => role === "HR" || role === "DIVISION_HEAD"),
  );
  const isDivisionRequester = Boolean(principal?.roles.includes("DIVISION_HEAD"));
  const canSubmit = isHrOperator || isDivisionRequester;
  const isOwnSubmission = Boolean(
    principal && selected && principal.user_id === selected.submitted_by_user_id,
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [requestPage, documentPage] = await Promise.all([
        getRecruitmentRequests(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setRequests(requestPage.items);
      setDocuments(documentPage.items);
      setSelectedId((current) => (
        requestPage.items.some((request) => request.recruitment_request_id === current)
          ? current
          : requestPage.items[0]?.recruitment_request_id || null
      ));
      setSubmission((current) => ({
        ...current,
        requestingDivisionCode: isHrOperator
          ? current.requestingDivisionCode
          : principal?.division_codes[0] || current.requestingDivisionCode,
        documentVersionId: documentPage.items.some(
          (document) => document.document_version_id === current.documentVersionId,
        ) ? current.documentVersionId : documentPage.items[0]?.document_version_id || "",
      }));
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, isHrOperator, principal?.division_codes, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadData, status]);

  useEffect(() => {
    if (!token || !selected || selected.status !== "SELECTED") return;
    let active = true;
    getPersonnelChecklist(token, selected.recruitment_request_id)
      .then((result) => {
        if (active) {
          setChecklist(result);
          setChecklistRequestId(selected.recruitment_request_id);
        }
      })
      .catch((requestError) => {
        if (active) setFeedback(message(requestError));
      });
    return () => { active = false; };
  }, [selected, token]);

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canSubmit) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await submitRecruitmentRequest(token, {
        project_id: activeProjectId,
        candidate_document_version_id: submission.documentVersionId,
        position_title: submission.positionTitle.trim(),
        requesting_division_code: submission.requestingDivisionCode,
        employment_type: submission.employmentType,
        headcount: Number(submission.headcount),
        justification: submission.justification.trim(),
        criteria_version: submission.criteriaVersion.trim(),
        candidate_alias: submission.candidateAlias.trim(),
        required_criteria: codes(submission.requiredCriteria),
        met_criteria: codes(submission.metCriteria),
      });
      setSubmission((current) => ({
        ...current,
        positionTitle: "",
        justification: "",
        candidateAlias: "",
      }));
      await loadData();
      setSelectedId(result.recruitment_request_id);
      setFeedback("Permintaan dan screening administratif tersimpan untuk review HR Human.");
    } catch (submitError) {
      setFeedback(message(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !isHrOperator || isOwnSubmission) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await decideRecruitment(token, selected.recruitment_request_id, {
        decision: decision.value,
        notes: decision.notes.trim(),
        personnel_requirements:
          decision.value === "SELECTED" ? codes(decision.personnelRequirements) : [],
      });
      setDecision((current) => ({ ...current, notes: "" }));
      await loadData();
      setFeedback(
        result.personnel_checklist_id
          ? "Keputusan tersimpan dan checklist berkas personalia telah dibuat."
          : "Kandidat ditutup sesuai keputusan HR Human.",
      );
    } catch (decisionError) {
      setFeedback(message(decisionError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">HR · FLOW-005</p><h1>Rekrutmen sampai Personalia</h1><p>Kelola permintaan, screening administratif, keputusan HR Human, dan checklist berkas personalia.</p></div><button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button></header>
      {!activeProjectId ? <EmptyState title="Pilih proyek terlebih dahulu" description="Permintaan rekrutmen harus terkait dengan proyek yang dapat diakses." /> : null}
      {activeProjectId && loading ? <LoadingState label="Memuat proses rekrutmen…" /> : null}
      {activeProjectId && !loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {activeProjectId && !loading && !error ? <>
        {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
        {canSubmit ? <section className="panel transactionCreatePanel"><div className="panelHeader"><div><p className="eyebrow">Controlled intake</p><h2>Ajukan kandidat</h2></div></div><form className="transactionForm" onSubmit={submitRequest}>
          <label>Dokumen kandidat tersanitasi<select onChange={(event) => setSubmission({ ...submission, documentVersionId: event.target.value })} required value={submission.documentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label>
          <label>Alias kandidat<input maxLength={80} minLength={2} onChange={(event) => setSubmission({ ...submission, candidateAlias: event.target.value })} required value={submission.candidateAlias} /></label>
          <label>Posisi<input maxLength={160} minLength={3} onChange={(event) => setSubmission({ ...submission, positionTitle: event.target.value })} required value={submission.positionTitle} /></label>
          <label>Divisi pemohon<select disabled={!isHrOperator} onChange={(event) => setSubmission({ ...submission, requestingDivisionCode: event.target.value })} value={submission.requestingDivisionCode}>{divisionCodes.map((division) => <option key={division}>{division}</option>)}</select></label>
          <label>Jenis hubungan<select onChange={(event) => setSubmission({ ...submission, employmentType: event.target.value as typeof submission.employmentType })} value={submission.employmentType}><option>PERMANENT</option><option>CONTRACT</option><option>INTERNSHIP</option></select></label>
          <label>Headcount<input max="50" min="1" onChange={(event) => setSubmission({ ...submission, headcount: event.target.value })} required type="number" value={submission.headcount} /></label>
          <label>Versi kriteria<input onChange={(event) => setSubmission({ ...submission, criteriaVersion: event.target.value })} pattern="\d+\.\d+\.\d+" required value={submission.criteriaVersion} /></label>
          <label>Kriteria wajib<textarea maxLength={1000} minLength={2} onChange={(event) => setSubmission({ ...submission, requiredCriteria: event.target.value })} required rows={2} value={submission.requiredCriteria} /><small>Pisahkan kode dengan koma.</small></label>
          <label>Kriteria terpenuhi<textarea maxLength={1000} onChange={(event) => setSubmission({ ...submission, metCriteria: event.target.value })} rows={2} value={submission.metCriteria} /></label>
          <label>Justifikasi<textarea maxLength={2000} minLength={10} onChange={(event) => setSubmission({ ...submission, justification: event.target.value })} required rows={3} value={submission.justification} /></label>
          <button className="button primary" disabled={busy || !documents.length} type="submit">{busy ? "Memproses…" : "Ajukan rekrutmen"}</button>
        </form></section> : null}

        <div className="transactionLayout">
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Recruitment queue</p><h2>Permintaan rekrutmen</h2></div><span className="resultCount">{requests.length} permintaan</span></div>{!requests.length ? <EmptyState title="Belum ada permintaan" description="Permintaan rekrutmen proyek akan tampil di sini." /> : <div className="transactionRecordList">{requests.map((request) => <button className={request.recruitment_request_id === selectedId ? "selected" : ""} key={request.recruitment_request_id} onClick={() => setSelectedId(request.recruitment_request_id)} type="button"><span><strong>{request.position_title}</strong><small>{request.candidate_alias} · {request.requesting_division_code}</small></span><span><b className="statusBadge">{humanizeCode(request.status)}</b><small>{request.headcount} orang</small></span></button>)}</div>}</section>
          <section className="panel transactionDetail"><div className="panelHeader"><div><p className="eyebrow">HR detail</p><h2>{selected?.position_title || "Pilih permintaan"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>{selected ? <div className="transactionDetailBody">
            <dl className="detailGrid"><div><dt>Alias kandidat</dt><dd>{selected.candidate_alias}</dd></div><div><dt>Screening</dt><dd>{humanizeCode(selected.screening_status)}</dd></div><div><dt>Kriteria kurang</dt><dd>{selected.missing_criteria.length ? selected.missing_criteria.join(", ") : "Tidak ada"}</dd></div><div><dt>Pengaju</dt><dd>{shortId(selected.submitted_by_user_id)}</dd></div><div><dt>Jenis</dt><dd>{humanizeCode(selected.employment_type)}</dd></div><div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div></dl>
            <p>{selected.justification}</p>
            {isHrOperator && selected.status === "PENDING_HR_REVIEW" && !isOwnSubmission ? <form className="actionPanel" onSubmit={submitDecision}><div><p className="eyebrow">HR human decision</p><h3>Putuskan kandidat</h3></div><label>Keputusan<select onChange={(event) => setDecision({ ...decision, value: event.target.value as typeof decision.value })} value={decision.value}><option>SELECTED</option><option>REJECTED</option></select></label>{decision.value === "SELECTED" ? <label>Checklist berkas personalia<textarea maxLength={1000} minLength={2} onChange={(event) => setDecision({ ...decision, personnelRequirements: event.target.value })} required rows={2} value={decision.personnelRequirements} /><small>Pisahkan kode dengan koma.</small></label> : null}<label>Catatan keputusan<textarea maxLength={3000} minLength={3} onChange={(event) => setDecision({ ...decision, notes: event.target.value })} required rows={3} value={decision.notes} /></label><button className="button primary" disabled={busy} type="submit">Simpan keputusan</button></form> : null}
            {isHrOperator && selected.status === "PENDING_HR_REVIEW" && isOwnSubmission ? <div className="readOnlyNotice"><p><strong>Menunggu reviewer HR lain</strong><span>Pengaju tidak dapat memutuskan kandidat yang diajukannya sendiri.</span></p></div> : null}
            {visibleChecklist ? <section className="interactionHistory"><h3>Checklist personalia</h3>{visibleChecklist.requirements.map((requirement) => <article key={requirement.requirement_code}><div><strong>{humanizeCode(requirement.requirement_code)}</strong><span>{humanizeCode(requirement.status)}</span></div></article>)}</section> : null}
            {!isHrOperator && !isDivisionRequester ? <div className="readOnlyNotice"><p><strong>Akses monitoring</strong><span>Keputusan rekrutmen hanya dilakukan HR Human.</span></p></div> : null}
          </div> : <EmptyState title="Pilih permintaan" description="Pilih permintaan untuk melihat screening dan keputusan HR." />}</section>
        </div>
      </> : null}
    </>
  );
}

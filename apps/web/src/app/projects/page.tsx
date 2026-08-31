"use client";

import { type FormEvent, useMemo, useState } from "react";

import { EmptyState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, createProject, updateProjectStatus } from "@/lib/api";
import { formatDateTime, humanizeCode } from "@/lib/format";
import type { Project } from "@/lib/types";

const transitions: Record<Project["status"], Project["status"][]> = {
  DRAFT: ["ACTIVE"],
  ACTIVE: ["ON_HOLD", "CLOSED"],
  ON_HOLD: ["ACTIVE", "CLOSED"],
  CLOSED: [],
};

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Konfigurasi proyek belum dapat diproses.";
}

export default function ProjectsPage() {
  const { principal, projects, refreshProjects, token } = useSession();
  const [selectedId, setSelectedId] = useState(projects[0]?.project_id || null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [projectForm, setProjectForm] = useState({ code: "", name: "" });
  const [statusForm, setStatusForm] = useState({
    status: "ACTIVE" as Project["status"],
    reason: "",
  });

  const selected = useMemo(
    () => projects.find((project) => project.project_id === selectedId) || projects[0] || null,
    [projects, selectedId],
  );
  const nextStatuses = selected ? transitions[selected.status] : [];
  const targetStatus = nextStatuses.includes(statusForm.status)
    ? statusForm.status
    : nextStatuses[0];
  const canCreate = Boolean(
    principal?.roles.some((role) => role === "DIRECTOR" || role === "IT_ADMIN"),
  );
  const canDecideStatus = Boolean(principal?.roles.includes("DIRECTOR"));

  async function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !canCreate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const created = await createProject(token, {
        code: projectForm.code.trim().toUpperCase(),
        name: projectForm.name.trim(),
      });
      await refreshProjects();
      setSelectedId(created.project_id);
      setProjectForm({ code: "", name: "" });
      setFeedback("Proyek dibuat sebagai DRAFT dan menunggu aktivasi Direktur Utama.");
    } catch (error) {
      setFeedback(message(error));
    } finally {
      setBusy(false);
    }
  }

  async function submitStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !targetStatus || !canDecideStatus) return;
    setBusy(true);
    setFeedback(null);
    try {
      await updateProjectStatus(token, selected.project_id, {
        status: targetStatus,
        reason: statusForm.reason.trim(),
      });
      await refreshProjects();
      setStatusForm({ status: "ACTIVE", reason: "" });
      setFeedback("Status proyek diperbarui dan dicatat pada audit trail.");
    } catch (error) {
      setFeedback(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Controlled configuration</p><h1>Proyek & Status</h1><p>Buat konteks proyek dan kelola lifecycle secara deterministik. Aktivasi tetap menjadi keputusan Direktur Utama.</p></div><button className="button secondary" disabled={busy} onClick={() => void refreshProjects()} type="button">Perbarui data</button></header>
      {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
      {canCreate ? <section className="panel transactionCreatePanel"><div className="panelHeader"><div><p className="eyebrow">Project setup</p><h2>Buat proyek</h2></div><span className="statusBadge">Default DRAFT</span></div><form className="transactionForm" onSubmit={submitProject}><label>Kode proyek<input maxLength={32} minLength={2} onChange={(event) => setProjectForm({ ...projectForm, code: event.target.value })} pattern="[A-Za-z][A-Za-z0-9_-]+" required value={projectForm.code} /></label><label>Nama proyek<input maxLength={160} minLength={3} onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })} required value={projectForm.name} /></label><button className="button primary" disabled={busy} type="submit">Buat proyek</button></form></section> : null}
      <div className="transactionLayout">
        <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Project register</p><h2>Daftar proyek</h2></div><span className="resultCount">{projects.length} proyek</span></div>{projects.length ? <div className="transactionRecordList">{projects.map((project) => <button className={project.project_id === selected?.project_id ? "selected" : ""} key={project.project_id} onClick={() => setSelectedId(project.project_id)} type="button"><span><strong>{project.name}</strong><small>{project.code}</small></span><span><b className="statusBadge">{humanizeCode(project.status)}</b><small>{formatDateTime(project.created_at)}</small></span></button>)}</div> : <EmptyState title="Belum ada proyek" description="Buat proyek pilot dengan data sintetis sebelum menjalankan workflow." />}</section>
        <section className="panel transactionDetail"><div className="panelHeader"><div><p className="eyebrow">Project lifecycle</p><h2>{selected?.name || "Pilih proyek"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>{selected ? <div className="transactionDetailBody"><dl className="detailGrid"><div><dt>Kode</dt><dd>{selected.code}</dd></div><div><dt>Status</dt><dd>{humanizeCode(selected.status)}</dd></div><div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div></dl>{canDecideStatus && nextStatuses.length ? <form className="actionPanel" onSubmit={submitStatus}><div><p className="eyebrow">Director decision</p><h3>Ubah status proyek</h3></div><label>Status berikutnya<select onChange={(event) => setStatusForm({ ...statusForm, status: event.target.value as Project["status"] })} value={targetStatus}>{nextStatuses.map((status) => <option key={status} value={status}>{humanizeCode(status)}</option>)}</select></label><label>Alasan keputusan<textarea maxLength={500} minLength={8} onChange={(event) => setStatusForm({ ...statusForm, reason: event.target.value })} required rows={3} value={statusForm.reason} /></label><button className="button primary" disabled={busy} type="submit">Simpan status</button></form> : null}{selected.status === "CLOSED" ? <div className="readOnlyNotice"><p><strong>Proyek telah ditutup</strong><span>Status CLOSED bersifat terminal dan tidak dapat diaktifkan kembali.</span></p></div> : null}{!canDecideStatus && selected.status !== "CLOSED" ? <div className="readOnlyNotice"><p><strong>Keputusan Direktur diperlukan</strong><span>IT dapat menyiapkan proyek, tetapi tidak dapat mengaktifkan, menahan, atau menutupnya.</span></p></div> : null}</div> : <EmptyState title="Pilih proyek" description="Pilih proyek untuk melihat status dan lifecycle." />}</section>
      </div>
    </>
  );
}

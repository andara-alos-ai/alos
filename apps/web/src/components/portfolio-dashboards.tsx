"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { apiMessage, apiRequest } from "@/lib/api-client";
import { type SessionActor, type Workspace } from "@/lib/governance";

import { DivisionViews } from "./divisions/division-views";
import { ProjectViews } from "./projects/project-views";
import {
  buildProjectPortfolioUrl,
  type DivisionsOverviewSnapshot,
  type ProjectPortfolioFilters,
  type ProjectPortfolioSnapshot,
} from "@/lib/portfolio";

const EMPTY_FILTERS: ProjectPortfolioFilters = {
  division_code: "",
  status: "",
  category: "",
  date_from: "",
  date_to: "",
  search: "",
  page: 1,
};

export function DivisionsOverviewDashboard() {
  const [data, setData] = useState<DivisionsOverviewSnapshot | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        setData(await apiRequest<DivisionsOverviewSnapshot>("/api/v1/divisions/overview", { signal: controller.signal }));
      } catch (error) {
        if ((error as Error).name !== "AbortError") setFailed(true);
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  if (failed) return <PortfolioLoadError label="ringkasan divisi" />;
  if (!data) return <PortfolioLoading label="Memuat ringkasan divisi…" />;
  return <DivisionsOverviewContent dashboard={data} />;
}

export function DivisionsOverviewContent({ dashboard }: { dashboard: DivisionsOverviewSnapshot }) {
  return <DivisionViews dashboard={dashboard} />;
}

export function ProjectPortfolioDashboard({ actor }: { actor?: SessionActor }) {
  const [filters, setFilters] = useState<ProjectPortfolioFilters>(EMPTY_FILTERS);
  const [data, setData] = useState<ProjectPortfolioSnapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const url = useMemo(() => buildProjectPortfolioUrl(filters), [filters]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setFailed(false);
      try {
        setData(await apiRequest<ProjectPortfolioSnapshot>(url, { signal: controller.signal }));
      } catch (error) {
        if ((error as Error).name !== "AbortError") setFailed(true);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [reloadKey, url]);

  if (failed && !data) return <PortfolioLoadError label="portofolio proyek" />;
  if (!data) return <PortfolioLoading label="Memuat portofolio proyek…" />;
  return (
    <>
      {actor ? <ProjectCreatePanel actor={actor} onCreated={() => setReloadKey((value) => value + 1)} /> : null}
      {actor ? <ProjectOperationsPanel onChanged={() => setReloadKey((value) => value + 1)} projects={data.projects} /> : null}
      <ProjectPortfolioContent
      dashboard={data}
      filters={filters}
      loading={loading}
      onFiltersChange={setFilters}
      />
    </>
  );
}

type ProjectControl = ProjectPortfolioSnapshot["projects"][number];

function ProjectOperationsPanel({ onChanged, projects }: { onChanged: () => void; projects: ProjectControl[] }) {
  const [projectId, setProjectId] = useState(projects[0]?.project_id ?? "");
  const [mode, setMode] = useState<"update" | "milestone" | "issue">("update");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = projects.find((project) => project.project_id === projectId) ?? projects[0];
  const [update, setUpdate] = useState({ status: "ON_TRACK", progress_percent: "0", deadline: "", budget_spent: "" });
  const [milestone, setMilestone] = useState({ title: "", due_date: "", status: "ON_TRACK" });
  const [issue, setIssue] = useState({ title: "", description: "", severity: "MEDIUM", due_date: "" });

  useEffect(() => {
    if (!projectId && projects[0]) {
      const timer = window.setTimeout(() => setProjectId(projects[0].project_id), 0);
      return () => window.clearTimeout(timer);
    }
  }, [projectId, projects]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || saving) return;
    setSaving(true); setError(""); setNotice("");
    try {
      if (mode === "update") {
        await apiRequest(`/api/v1/projects/${selected.project_id}`, { method: "PATCH", body: JSON.stringify({ status: update.status, progress_percent: Number(update.progress_percent), deadline: update.deadline || null, budget_spent: update.budget_spent ? Number(update.budget_spent) : null }) });
        setNotice("Status dan progress proyek diperbarui.");
      } else if (mode === "milestone") {
        await apiRequest(`/api/v1/projects/${selected.project_id}/milestones`, { method: "POST", body: JSON.stringify({ ...milestone }) });
        setMilestone({ title: "", due_date: "", status: "ON_TRACK" }); setNotice("Milestone berhasil ditambahkan.");
      } else {
        await apiRequest("/api/v1/project-issues", { method: "POST", body: JSON.stringify({ workspace_id: selected.workspace_id, division_code: selected.division_code, project_id: selected.project_id, title: issue.title, description: issue.description, severity: issue.severity, due_date: issue.due_date || null }) });
        setIssue({ title: "", description: "", severity: "MEDIUM", due_date: "" }); setNotice("Isu proyek berhasil dicatat.");
      }
      onChanged();
    } catch (failure) { setError(apiMessage(failure)); } finally { setSaving(false); }
  }

  async function removeProject() {
    if (!selected || saving) return;
    if (!window.confirm(`Hapus proyek “${selected.name}” secara permanen? Proyek tanpa data terkait akan langsung hilang dari dashboard.`)) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest(`/api/v1/projects/${selected.project_id}`, { method: "DELETE" });
      setProjectId("");
      setNotice("Proyek telah dihapus.");
      onChanged();
    } catch (failure) { setError(apiMessage(failure)); } finally { setSaving(false); }
  }

  if (!projects.length) return null;
  return <section className="alos-content alos-project-create-shell"><div className="alos-operation-heading"><div><p className="alos-kicker">PROJECT CONTROLS</p><h3>Perbarui proyek, milestone, dan isu</h3></div><select aria-label="Pilih proyek" onChange={(event) => setProjectId(event.target.value)} value={selected?.project_id ?? ""}>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.code} · {project.name}</option>)}</select></div>{error ? <div className="alos-operation-banner error">{error}</div> : null}{notice ? <div className="alos-operation-banner success">{notice}</div> : null}<div className="alos-operation-toolbar"><button className={mode === "update" ? "alos-workspace-primary" : "alos-outline-button"} onClick={() => setMode("update")} type="button">Update proyek</button><button className={mode === "milestone" ? "alos-workspace-primary" : "alos-outline-button"} onClick={() => setMode("milestone")} type="button">Tambah milestone</button><button className={mode === "issue" ? "alos-workspace-primary" : "alos-outline-button"} onClick={() => setMode("issue")} type="button">Catat isu</button><button className="danger" disabled={saving} onClick={() => void removeProject()} type="button">Hapus proyek</button></div><form className="alos-operation-form" onSubmit={(event) => void submit(event)}>{mode === "update" ? <><label>Status<select onChange={(event) => setUpdate({ ...update, status: event.target.value })} value={update.status}><option>ON_TRACK</option><option>AT_RISK</option><option>CRITICAL</option><option>COMPLETED</option></select></label><label>Progress (%)<input max="100" min="0" onChange={(event) => setUpdate({ ...update, progress_percent: event.target.value })} required step="0.1" type="number" value={update.progress_percent} /></label><label>Tenggat<input onChange={(event) => setUpdate({ ...update, deadline: event.target.value })} type="date" value={update.deadline} /></label><label>Biaya aktual<input min="0" onChange={(event) => setUpdate({ ...update, budget_spent: event.target.value })} step="1" type="number" value={update.budget_spent} /></label></> : null}{mode === "milestone" ? <><label className="wide">Milestone<input minLength={2} onChange={(event) => setMilestone({ ...milestone, title: event.target.value })} required value={milestone.title} /></label><label>Tenggat<input onChange={(event) => setMilestone({ ...milestone, due_date: event.target.value })} required type="date" value={milestone.due_date} /></label><label>Status<select onChange={(event) => setMilestone({ ...milestone, status: event.target.value })} value={milestone.status}><option>ON_TRACK</option><option>AT_RISK</option><option>CRITICAL</option><option>COMPLETED</option></select></label></> : null}{mode === "issue" ? <><label className="wide">Judul isu<input minLength={2} onChange={(event) => setIssue({ ...issue, title: event.target.value })} required value={issue.title} /></label><label className="wide">Deskripsi<textarea onChange={(event) => setIssue({ ...issue, description: event.target.value })} value={issue.description} /></label><label>Severity<select onChange={(event) => setIssue({ ...issue, severity: event.target.value })} value={issue.severity}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label><label>Tenggat<input onChange={(event) => setIssue({ ...issue, due_date: event.target.value })} type="date" value={issue.due_date} /></label></> : null}<button className="alos-workspace-primary" disabled={saving} type="submit">{saving ? "Menyimpan…" : "Simpan"}</button></form></section>;
}

function ProjectCreatePanel({ actor, onCreated }: { actor: SessionActor; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState(actor.workspace_ids[0] ?? "");
  const [form, setForm] = useState({ code: "", name: "", category: "PROPERTY", deadline: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const activeWorkspace = workspaces.find((item) => item.workspace_id === workspaceId);

  useEffect(() => {
    if (!open || workspaces.length) return;
    apiRequest<Workspace[]>("/api/v1/workspaces")
      .then((items) => {
        const visible = items.filter((item) => actor.workspace_ids.includes(item.workspace_id));
        setWorkspaces(visible);
        if (!workspaceId && visible[0]) setWorkspaceId(visible[0].workspace_id);
      })
      .catch((failure) => setError(apiMessage(failure)));
  }, [actor.workspace_ids, open, workspaceId, workspaces.length]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!activeWorkspace?.division_code) return;
    setSaving(true); setError("");
    try {
      await apiRequest("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          division_code: activeWorkspace.division_code,
          code: form.code,
          name: form.name,
          category: form.category,
          deadline: form.deadline || null,
        }),
      });
      setForm({ code: "", name: "", category: "PROPERTY", deadline: "" });
      setOpen(false);
      onCreated();
    } catch (failure) {
      setError(apiMessage(failure));
    } finally {
      setSaving(false);
    }
  }

  return <section className="alos-content alos-project-create-shell"><div className="alos-operation-heading"><div><p className="alos-kicker">PORTFOLIO OPERATIONS</p><h3>Kelola proyek dalam scope Anda</h3></div><button className="alos-workspace-primary" onClick={() => setOpen((value) => !value)} type="button">{open ? "Tutup" : "+ Buat proyek"}</button></div>{error ? <div className="alos-operation-banner error">{error}</div> : null}{open ? <form className="alos-operation-form" onSubmit={(event) => void submit(event)}><label>Workspace<select onChange={(event) => setWorkspaceId(event.target.value)} required value={workspaceId}>{workspaces.map((item) => <option key={item.workspace_id} value={item.workspace_id}>{item.name} · {item.division_code ?? "Tanpa divisi"}</option>)}</select></label><label>Kode<input maxLength={40} minLength={2} onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "") })} required value={form.code} /></label><label>Kategori<input maxLength={80} minLength={2} onChange={(event) => setForm({ ...form, category: event.target.value })} required value={form.category} /></label><label className="wide">Nama proyek<input maxLength={160} minLength={2} onChange={(event) => setForm({ ...form, name: event.target.value })} required value={form.name} /></label><label>Tenggat<input onChange={(event) => setForm({ ...form, deadline: event.target.value })} type="date" value={form.deadline} /></label><button className="alos-workspace-primary" disabled={saving || !activeWorkspace?.division_code} type="submit">{saving ? "Menyimpan…" : "Simpan proyek"}</button></form> : null}</section>;
}

export function ProjectPortfolioContent({
  dashboard,
  filters,
  loading,
  onFiltersChange,
}: {
  dashboard: ProjectPortfolioSnapshot;
  filters: ProjectPortfolioFilters;
  loading: boolean;
  onFiltersChange: (filters: ProjectPortfolioFilters) => void;
}) {
  return (
    <ProjectViews
      dashboard={dashboard}
      filters={filters}
      loading={loading}
      onFiltersChange={onFiltersChange}
    />
  );
}

function PortfolioLoading({ label }: { label: string }) {
  return <section className="alos-content alos-portfolio-loading" aria-live="polite"><p>{label}</p><div /><div /></section>;
}

function PortfolioLoadError({ label }: { label: string }) {
  return <section className="alos-content"><article className="alos-executive-error"><strong>Gagal memuat {label}</strong><span>Data tetap aman. Muat ulang halaman untuk mencoba kembali.</span></article></section>;
}

"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/icons";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  addUserProject,
  addUserRole,
  ApiError,
  createUser,
  getUsers,
  revokeUserProject,
  revokeUserRole,
  updateUserStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  canManageIdentity,
  divisionForRole,
  divisionLabels,
  divisions,
  type DivisionCode,
  optionalDateTimeToIso,
  roleHasFixedDivision,
  validateAuditReason,
} from "@/lib/identity";
import { roleLabels } from "@/lib/navigation";
import {
  roles as allRoles,
  type Role,
  type UserDirectoryRecord,
  type UserStatus,
} from "@/lib/types";

const statusLabels: Record<UserStatus, string> = {
  INVITED: "Diundang",
  ACTIVE: "Aktif",
  SUSPENDED: "Ditangguhkan",
};

type DirectoryFilters = {
  search: string;
  status: UserStatus | "";
  role: Role | "";
  division_code: string;
};

const emptyFilters: DirectoryFilters = { search: "", status: "", role: "", division_code: "" };

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Perubahan data pengguna belum dapat diproses.";
}

export default function UsersPage() {
  const { principal, projects, status, token } = useSession();
  const [users, setUsers] = useState<UserDirectoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filters, setFilters] = useState<DirectoryFilters>(emptyFilters);
  const [draftFilters, setDraftFilters] = useState<DirectoryFilters>(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<Role>("SALES");
  const [newDivision, setNewDivision] = useState<DivisionCode>("SALES_MARKETING");

  const [governanceReason, setGovernanceReason] = useState("");
  const [assignmentRole, setAssignmentRole] = useState<Role>("DIVISION_HEAD");
  const [assignmentDivision, setAssignmentDivision] = useState<DivisionCode>("FINANCE");
  const [roleExpiry, setRoleExpiry] = useState("");
  const [roleReason, setRoleReason] = useState("");
  const [projectId, setProjectId] = useState("");
  const [projectExpiry, setProjectExpiry] = useState("");
  const [projectReason, setProjectReason] = useState("");

  const selected = useMemo(
    () => users.find((user) => user.user_id === selectedId) || null,
    [selectedId, users],
  );
  const canManage = canManageIdentity(principal?.roles || []);
  const isSelf = selected?.user_id === principal?.user_id;
  const availableProjects = useMemo(() => {
    const assigned = new Set(selected?.projects.map((item) => item.project_id) || []);
    return projects.filter((project) => !assigned.has(project.project_id));
  }, [projects, selected?.projects]);
  const selectedProjectId = availableProjects.some((project) => project.project_id === projectId)
    ? projectId
    : availableProjects[0]?.project_id || "";

  const loadUsers = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const page = await getUsers(token, filters);
      setUsers(page.items);
      setTotal(page.total);
      setSelectedId((current) =>
        page.items.some((item) => item.user_id === current)
          ? current
          : page.items[0]?.user_id || null,
      );
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [filters, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadUsers(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadUsers, status]);

  function clearFeedback() {
    setActionError(null);
    setActionMessage(null);
  }

  async function runAction(name: string, successMessage: string, action: () => Promise<unknown>) {
    clearFeedback();
    setBusy(name);
    try {
      await action();
      await loadUsers();
      setActionMessage(successMessage);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setBusy(null);
    }
  }

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    if (draftFilters.search.trim().length === 1) {
      setActionError("Pencarian minimal 2 karakter.");
      return;
    }
    clearFeedback();
    setFilters({ ...draftFilters, search: draftFilters.search.trim() });
  }

  function resetFilters() {
    setDraftFilters(emptyFilters);
    setFilters(emptyFilters);
    clearFeedback();
  }

  async function submitNewUser(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    clearFeedback();
    setBusy("create-user");
    try {
      const created = await createUser(token, {
        email: newEmail.trim(),
        display_name: newName.trim(),
        role: newRole,
        division_code: divisionForRole(newRole, newDivision),
      });
      setNewEmail("");
      setNewName("");
      setShowCreate(false);
      setDraftFilters(emptyFilters);
      setFilters(emptyFilters);
      const page = await getUsers(token, emptyFilters);
      setUsers(page.items);
      setTotal(page.total);
      setSelectedId(created.user_id);
      setActionMessage("Akun aktif berhasil dibuat dan siap digunakan melalui Google.");
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function changeStatus() {
    if (!selected || !token) return;
    const reasonError = validateAuditReason(governanceReason);
    if (reasonError) {
      setActionError(reasonError);
      return;
    }
    const nextStatus = selected.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
    await runAction(
      "status",
      nextStatus === "ACTIVE" ? "Akun berhasil diaktifkan kembali." : "Akun berhasil ditangguhkan.",
      () => updateUserStatus(token, selected.user_id, nextStatus, governanceReason.trim()),
    );
    setGovernanceReason("");
  }

  async function submitRole(event: FormEvent) {
    event.preventDefault();
    if (!selected || !token) return;
    const reasonError = validateAuditReason(roleReason);
    if (reasonError) {
      setActionError(reasonError);
      return;
    }
    await runAction("add-role", "Role berhasil ditambahkan.", () =>
      addUserRole(token, selected.user_id, {
        role: assignmentRole,
        division_code: divisionForRole(assignmentRole, assignmentDivision),
        valid_until: optionalDateTimeToIso(roleExpiry),
        reason: roleReason.trim(),
      }),
    );
    setRoleReason("");
    setRoleExpiry("");
  }

  async function revokeRole(assignmentId: string) {
    if (!selected || !token) return;
    const reasonError = validateAuditReason(governanceReason);
    if (reasonError) {
      setActionError(reasonError);
      return;
    }
    await runAction("revoke-role", "Role berhasil dicabut.", () =>
      revokeUserRole(token, selected.user_id, assignmentId, governanceReason.trim()),
    );
    setGovernanceReason("");
  }

  async function submitProject(event: FormEvent) {
    event.preventDefault();
    if (!selected || !token || !selectedProjectId) return;
    const reasonError = validateAuditReason(projectReason);
    if (reasonError) {
      setActionError(reasonError);
      return;
    }
    await runAction("add-project", "Akses proyek berhasil ditambahkan.", () =>
      addUserProject(token, selected.user_id, {
        project_id: selectedProjectId,
        valid_until: optionalDateTimeToIso(projectExpiry),
        reason: projectReason.trim(),
      }),
    );
    setProjectReason("");
    setProjectExpiry("");
  }

  async function revokeProject(assignmentId: string) {
    if (!selected || !token) return;
    const reasonError = validateAuditReason(governanceReason);
    if (reasonError) {
      setActionError(reasonError);
      return;
    }
    await runAction("revoke-project", "Akses proyek berhasil dicabut.", () =>
      revokeUserProject(token, selected.user_id, assignmentId, governanceReason.trim()),
    );
    setGovernanceReason("");
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Identity & Access Management</p>
          <h1>Pengguna & Akses</h1>
          <p>Kelola akun internal, role, divisi, dan cakupan proyek dengan jejak audit terpusat.</p>
        </div>
        {canManage ? (
          <button className="button primary" onClick={() => setShowCreate((value) => !value)} type="button">
            <Icon name="users" /> {showCreate ? "Tutup formulir" : "Tambah pengguna"}
          </button>
        ) : null}
      </header>

      {showCreate && canManage ? (
        <section className="panel identityCreatePanel">
          <div className="panelHeader">
            <div><p className="eyebrow">Pre-provisioning</p><h2>Buat akun internal</h2></div>
            <span className="statusBadge">Langsung aktif</span>
          </div>
          <form className="identityForm" onSubmit={(event) => void submitNewUser(event)}>
            <label>Nama lengkap<input autoComplete="name" maxLength={160} onChange={(event) => setNewName(event.target.value)} required value={newName} /></label>
            <label>Email Google<input autoComplete="email" maxLength={254} onChange={(event) => setNewEmail(event.target.value)} required type="email" value={newEmail} /></label>
            <label>Role awal<select onChange={(event) => setNewRole(event.target.value as Role)} value={newRole}>{allRoles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label>
            <label>Divisi<select disabled={roleHasFixedDivision(newRole)} onChange={(event) => setNewDivision(event.target.value as DivisionCode)} value={divisionForRole(newRole, newDivision) || ""}>{divisionForRole(newRole, newDivision) === null ? <option value="">Lintas divisi</option> : divisions.map((division) => <option key={division} value={division}>{divisionLabels[division]}</option>)}</select></label>
            <div className="identityFormFooter"><p>Email harus sama dengan akun Google yang akan dipakai masuk ke ALOS.</p><button className="button primary" disabled={Boolean(busy)} type="submit">{busy === "create-user" ? "Menyimpan…" : "Buat akun"}</button></div>
          </form>
        </section>
      ) : null}

      <form className="identityFilters" onSubmit={applyFilters}>
        <label>Cari pengguna<input onChange={(event) => setDraftFilters({ ...draftFilters, search: event.target.value })} placeholder="Nama atau email" value={draftFilters.search} /></label>
        <label>Status<select onChange={(event) => setDraftFilters({ ...draftFilters, status: event.target.value as UserStatus | "" })} value={draftFilters.status}><option value="">Semua status</option><option value="ACTIVE">Aktif</option><option value="SUSPENDED">Ditangguhkan</option><option value="INVITED">Diundang</option></select></label>
        <label>Role<select onChange={(event) => setDraftFilters({ ...draftFilters, role: event.target.value as Role | "" })} value={draftFilters.role}><option value="">Semua role</option>{allRoles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label>
        <label>Divisi<select onChange={(event) => setDraftFilters({ ...draftFilters, division_code: event.target.value })} value={draftFilters.division_code}><option value="">Semua divisi</option>{divisions.map((division) => <option key={division} value={division}>{divisionLabels[division]}</option>)}</select></label>
        <div className="identityFilterActions"><button className="button primary" type="submit">Terapkan</button><button className="button secondary" onClick={resetFilters} type="button">Reset</button></div>
      </form>

      {actionError ? <div className="formError identityFeedback" role="alert">{actionError}</div> : null}
      {actionMessage ? <div className="identitySuccess identityFeedback" role="status">{actionMessage}</div> : null}
      {loading ? <LoadingState label="Memuat direktori pengguna…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void loadUsers()} /> : null}
      {!loading && !error && !users.length ? <EmptyState title="Pengguna tidak ditemukan" description="Ubah filter pencarian atau tambahkan akun internal baru." /> : null}

      {!loading && !error && users.length ? (
        <div className="identityLayout">
          <section className="identityList" aria-label="Direktori pengguna">
            <div className="identityListSummary"><strong>{total} pengguna</strong><span>Dalam organisasi aktif</span></div>
            {users.map((user) => (
              <button aria-pressed={selectedId === user.user_id} className={selectedId === user.user_id ? "identityUser selected" : "identityUser"} key={user.user_id} onClick={() => { setSelectedId(user.user_id); clearFeedback(); setGovernanceReason(""); }} type="button">
                <span className="identityAvatar">{user.display_name.slice(0, 1).toUpperCase()}</span>
                <span className="identityUserCopy"><strong>{user.display_name}</strong><small>{user.email}</small><span>{user.roles.map((assignment) => roleLabels[assignment.role]).join(", ") || "Tanpa role"}</span></span>
                <span className={`accountStatus ${user.status.toLowerCase()}`}>{statusLabels[user.status]}</span>
              </button>
            ))}
          </section>

          {selected ? (
            <section className="identityDetail" aria-label="Detail pengguna">
              <div className="identityDetailHeader">
                <div><p className="eyebrow">Profil pengguna</p><h2>{selected.display_name}</h2><p>{selected.email}</p></div>
                <span className={`accountStatus large ${selected.status.toLowerCase()}`}>{statusLabels[selected.status]}</span>
              </div>
              <dl className="detailGrid identityMeta">
                <div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                <div><dt>Diperbarui</dt><dd>{formatDateTime(selected.updated_at)}</dd></div>
                <div><dt>Jumlah role</dt><dd>{selected.roles.length}</dd></div>
                <div><dt>Akses proyek</dt><dd>{selected.projects.length}</dd></div>
              </dl>

              {canManage ? (
                <section className="identityGovernance">
                  <label>Alasan perubahan atau pencabutan<input maxLength={500} onChange={(event) => setGovernanceReason(event.target.value)} placeholder="Minimal 8 karakter untuk audit" value={governanceReason} /></label>
                  <button className="button secondary" disabled={Boolean(busy) || isSelf || selected.status === "INVITED"} onClick={() => void changeStatus()} type="button">{selected.status === "ACTIVE" ? "Tangguhkan akun" : "Aktifkan akun"}</button>
                  {isSelf ? <small>Administrator tidak dapat mengubah atau mencabut akses akunnya sendiri.</small> : null}
                </section>
              ) : <div className="readOnlyNotice"><Icon name="document" /><p><strong>Akses baca saja</strong><span>Peran Anda dapat memantau akses tanpa mengubah akun atau penugasan.</span></p></div>}

              <section className="identitySection">
                <div className="identitySectionHeader"><div><p className="eyebrow">Role & divisi</p><h3>Penugasan aktif</h3></div></div>
                <div className="assignmentList">
                  {selected.roles.map((assignment) => <article key={assignment.assignment_id}><div><strong>{roleLabels[assignment.role]}</strong><span>{assignment.division_code ? divisionLabels[assignment.division_code as DivisionCode] : "Lintas divisi"}</span><small>Berlaku sampai {formatDateTime(assignment.valid_until)}</small></div>{canManage ? <button className="textButton danger" disabled={Boolean(busy) || isSelf} onClick={() => void revokeRole(assignment.assignment_id)} type="button">Cabut</button> : null}</article>)}
                  {!selected.roles.length ? <p className="muted identityEmptyLine">Belum ada role aktif.</p> : null}
                </div>
                {canManage ? <form className="assignmentForm" onSubmit={(event) => void submitRole(event)}><label>Role<select onChange={(event) => setAssignmentRole(event.target.value as Role)} value={assignmentRole}>{allRoles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label><label>Divisi<select disabled={roleHasFixedDivision(assignmentRole)} onChange={(event) => setAssignmentDivision(event.target.value as DivisionCode)} value={divisionForRole(assignmentRole, assignmentDivision) || ""}>{divisionForRole(assignmentRole, assignmentDivision) === null ? <option value="">Lintas divisi</option> : divisions.map((division) => <option key={division} value={division}>{divisionLabels[division]}</option>)}</select></label><label>Berlaku sampai <span className="optional">(opsional)</span><input onChange={(event) => setRoleExpiry(event.target.value)} type="datetime-local" value={roleExpiry} /></label><label className="assignmentReason">Alasan<input maxLength={500} onChange={(event) => setRoleReason(event.target.value)} placeholder="Minimal 8 karakter" value={roleReason} /></label><button className="button secondary" disabled={Boolean(busy)} type="submit">Tambah role</button></form> : null}
              </section>

              <section className="identitySection">
                <div className="identitySectionHeader"><div><p className="eyebrow">Cakupan data</p><h3>Akses proyek aktif</h3></div></div>
                <div className="assignmentList">
                  {selected.projects.map((assignment) => <article key={assignment.assignment_id}><div><strong>{assignment.project_code} · {assignment.project_name}</strong><small>Berlaku sampai {formatDateTime(assignment.valid_until)}</small></div>{canManage ? <button className="textButton danger" disabled={Boolean(busy) || isSelf} onClick={() => void revokeProject(assignment.assignment_id)} type="button">Cabut</button> : null}</article>)}
                  {!selected.projects.length ? <p className="muted identityEmptyLine">Belum ada akses proyek khusus.</p> : null}
                </div>
                {canManage ? <form className="assignmentForm projectAssignmentForm" onSubmit={(event) => void submitProject(event)}><label>Proyek<select disabled={!availableProjects.length} onChange={(event) => setProjectId(event.target.value)} value={selectedProjectId}>{availableProjects.length ? availableProjects.map((project) => <option key={project.project_id} value={project.project_id}>{project.code} · {project.name}</option>) : <option value="">Semua proyek sudah ditugaskan</option>}</select></label><label>Berlaku sampai <span className="optional">(opsional)</span><input onChange={(event) => setProjectExpiry(event.target.value)} type="datetime-local" value={projectExpiry} /></label><label className="assignmentReason">Alasan<input maxLength={500} onChange={(event) => setProjectReason(event.target.value)} placeholder="Minimal 8 karakter" value={projectReason} /></label><button className="button secondary" disabled={Boolean(busy) || !selectedProjectId} type="submit">Tambah proyek</button></form> : null}
              </section>
            </section>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

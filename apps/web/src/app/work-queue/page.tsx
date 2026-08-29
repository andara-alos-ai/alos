"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/icons";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  claimWorkItem,
  delegateWorkItem,
  getWorkQueue,
  releaseWorkItem,
  updateWorkItemDeadline,
} from "@/lib/api";
import { formatDateTime, humanizeCode, relativeDeadline, shortId } from "@/lib/format";
import type { Role, WorkItem, WorkQueueScope } from "@/lib/types";

const scopes: Array<{ id: WorkQueueScope; label: string }> = [
  { id: "mine", label: "Pekerjaan saya" },
  { id: "unassigned", label: "Belum ditugaskan" },
  { id: "division", label: "Divisi" },
  { id: "overdue", label: "Terlambat" },
];

const operationalRoles: Role[] = [
  "DIRECTOR",
  "DIVISION_HEAD",
  "SALES",
  "FINANCE",
  "PROPERTY",
  "HR",
  "LEGAL",
  "IT_ADMIN",
];
const deadlineRoles: Role[] = ["DIRECTOR", "DIVISION_HEAD", "IT_ADMIN"];
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Perubahan work item belum dapat diproses.";
}

function toLocalDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function WorkQueuePage() {
  const { activeProjectId, principal, status, token } = useSession();
  const [scope, setScope] = useState<WorkQueueScope>("mine");
  const [items, setItems] = useState<WorkItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [targetUserId, setTargetUserId] = useState("");
  const [dueAt, setDueAt] = useState("");

  const selected = useMemo(
    () => items.find((item) => item.work_item_id === selectedId) || null,
    [items, selectedId],
  );
  const canOperate = principal?.roles.some((role) => operationalRoles.includes(role)) ?? false;
  const canChangeDeadline = principal?.roles.some((role) => deadlineRoles.includes(role)) ?? false;

  const loadQueue = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const nextItems = await getWorkQueue(token, scope, activeProjectId);
      setItems(nextItems);
      const firstItem = nextItems[0] || null;
      setSelectedId(firstItem?.work_item_id || null);
      setReason("");
      setTargetUserId("");
      setDueAt(toLocalDateTime(firstItem?.due_at || null));
      setActionError(null);
    } catch (queueError) {
      setError(errorMessage(queueError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, scope, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadQueue(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadQueue, status]);

  function selectItem(item: WorkItem) {
    setSelectedId(item.work_item_id);
    setReason("");
    setTargetUserId("");
    setDueAt(toLocalDateTime(item.due_at));
    setActionError(null);
  }

  async function runAction(action: "claim" | "release" | "delegate" | "deadline") {
    if (!selected || !token) return;
    setActionError(null);
    if (reason.trim().length < 8) {
      setActionError("Alasan wajib diisi minimal 8 karakter untuk kebutuhan audit.");
      return;
    }
    if (action === "delegate" && !uuidPattern.test(targetUserId)) {
      setActionError("Target User ID wajib menggunakan format UUID yang valid.");
      return;
    }
    if (action === "deadline" && !dueAt) {
      setActionError("Deadline baru wajib dipilih.");
      return;
    }
    setBusyAction(action);
    try {
      if (action === "claim") await claimWorkItem(token, selected.work_item_id, reason.trim());
      if (action === "release") await releaseWorkItem(token, selected.work_item_id, reason.trim());
      if (action === "delegate") {
        await delegateWorkItem(token, selected.work_item_id, targetUserId, reason.trim());
      }
      if (action === "deadline") {
        const parsedDeadline = new Date(dueAt);
        if (Number.isNaN(parsedDeadline.getTime())) throw new Error("Deadline tidak valid");
        await updateWorkItemDeadline(
          token,
          selected.work_item_id,
          parsedDeadline.toISOString(),
          reason.trim(),
        );
      }
      await loadQueue();
    } catch (actionFailure) {
      setActionError(errorMessage(actionFailure));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div><p className="eyebrow">Operasional</p><h1>Antrean Kerja</h1><p>Ambil, delegasikan, dan kelola pekerjaan dengan jejak audit yang jelas.</p></div>
        <button className="button secondary" disabled={loading} onClick={() => void loadQueue()} type="button">Perbarui antrean</button>
      </header>

      <div className="queueToolbar">
        <div className="scopeTabs" role="tablist" aria-label="Cakupan antrean">
          {scopes.map((item) => (
            <button
              aria-selected={scope === item.id}
              className={scope === item.id ? "active" : ""}
              key={item.id}
              onClick={() => setScope(item.id)}
              role="tab"
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
        <span className="resultCount">{items.length} work item</span>
      </div>

      {loading ? <LoadingState label="Memuat antrean kerja…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void loadQueue()} /> : null}
      {!loading && !error && !items.length ? (
        <EmptyState title="Tidak ada pekerjaan pada antrean ini" description="Pilih cakupan lain atau ubah konteks proyek untuk melihat work item yang tersedia." />
      ) : null}

      {!loading && !error && items.length ? (
        <div className="queueLayout">
          <section className="queueList" aria-label="Daftar work item">
            {items.map((item) => (
              <button
                aria-pressed={selectedId === item.work_item_id}
                className={selectedId === item.work_item_id ? "queueItem selected" : "queueItem"}
                key={item.work_item_id}
                onClick={() => selectItem(item)}
                type="button"
              >
                <span className="queueItemTop"><span className={`priorityBadge ${item.priority.toLowerCase()}`}>{humanizeCode(item.priority)}</span><small>{shortId(item.work_item_id)}</small></span>
                <strong>{item.title}</strong>
                <span className="queueMeta"><span>{humanizeCode(item.division_code)}</span><span>{humanizeCode(item.work_type)}</span></span>
                <span className="queueItemBottom"><span className="statusBadge">{humanizeCode(item.status)}</span><span className={item.overdue ? "deadline overdue" : "deadline"}><Icon name="clock" /> {relativeDeadline(item.due_at)}</span></span>
              </button>
            ))}
          </section>

          {selected ? (
            <aside className="workDetail" aria-label="Detail work item">
              <div className="detailHeader">
                <div><span className={`priorityBadge ${selected.priority.toLowerCase()}`}>{humanizeCode(selected.priority)}</span><h2>{selected.title}</h2><p>{humanizeCode(selected.work_type)} · {humanizeCode(selected.division_code)}</p></div>
                <span className="statusBadge large">{humanizeCode(selected.status)}</span>
              </div>
              <dl className="detailGrid">
                <div><dt>Work Item ID</dt><dd title={selected.work_item_id}>{shortId(selected.work_item_id)}</dd></div>
                <div><dt>Pemilik</dt><dd title={selected.owner_user_id || ""}>{selected.owner_user_id ? shortId(selected.owner_user_id) : "Belum ditugaskan"}</dd></div>
                <div><dt>Deadline</dt><dd>{formatDateTime(selected.due_at)}</dd></div>
                <div><dt>Eskalasi</dt><dd>Level {selected.escalation_level}</dd></div>
                <div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                <div><dt>Correlation ID</dt><dd title={selected.correlation_id}>{shortId(selected.correlation_id)}</dd></div>
              </dl>

              {canOperate ? (
                <section className="actionPanel">
                  <div><p className="eyebrow">Tindakan terkendali</p><h3>Kelola penugasan</h3><p>Setiap perubahan divalidasi backend dan dicatat sebagai audit event.</p></div>
                  <label>Alasan perubahan<textarea maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="Minimal 8 karakter" rows={3} value={reason} /></label>
                  {actionError ? <div className="formError" role="alert">{actionError}</div> : null}
                  <div className="actionButtons">
                    {!selected.owner_user_id ? <button className="button primary" disabled={Boolean(busyAction)} onClick={() => void runAction("claim")} type="button">{busyAction === "claim" ? "Memproses…" : "Ambil pekerjaan"}</button> : null}
                    {selected.owner_user_id === principal?.user_id ? <button className="button secondary" disabled={Boolean(busyAction)} onClick={() => void runAction("release")} type="button">{busyAction === "release" ? "Memproses…" : "Lepaskan"}</button> : null}
                  </div>
                  <div className="inlineAction">
                    <label>Delegasikan ke User ID<input onChange={(event) => setTargetUserId(event.target.value)} placeholder="UUID pengguna tujuan" value={targetUserId} /></label>
                    <button className="button secondary" disabled={Boolean(busyAction)} onClick={() => void runAction("delegate")} type="button">Delegasikan</button>
                  </div>
                  {canChangeDeadline ? (
                    <div className="inlineAction">
                      <label>Deadline baru<input onChange={(event) => setDueAt(event.target.value)} type="datetime-local" value={dueAt} /></label>
                      <button className="button secondary" disabled={Boolean(busyAction)} onClick={() => void runAction("deadline")} type="button">Ubah deadline</button>
                    </div>
                  ) : null}
                </section>
              ) : (
                <div className="readOnlyNotice"><Icon name="document" /><p><strong>Akses baca saja</strong><span>Peran Anda dapat memantau work item tanpa mengubah penugasan atau deadline.</span></p></div>
              )}
            </aside>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

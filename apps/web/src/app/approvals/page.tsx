"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, getApprovals } from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type { ApprovalRecord } from "@/lib/types";

export default function ApprovalsPage() {
  const { activeProjectId, status, token } = useSession();
  const [items, setItems] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getApprovals(token, activeProjectId);
      setItems(result.items);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Daftar persetujuan belum dapat dimuat.");
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(refresh);
  }, [load, status]);

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Governance</p><h1>Persetujuan</h1><p>Keputusan material harus eksplisit, berwenang, dan tercatat pada audit trail.</p></div><button className="button secondary" onClick={() => void load()} type="button">Perbarui data</button></header>
      {loading ? <LoadingState label="Memuat permintaan persetujuan…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {!loading && !error && !items.length ? <EmptyState title="Belum ada permintaan persetujuan" description="Permintaan akan muncul setelah workflow membuat approval berdasarkan kebijakan yang berlaku." /> : null}
      {!loading && !error && items.length ? (
        <div className="tablePanel"><table><thead><tr><th>Referensi</th><th>Kebijakan</th><th>Divisi</th><th>Status</th><th>Dibuat</th><th>Diputuskan</th></tr></thead><tbody>
          {items.map((item) => <tr key={item.approval_request_id}><td><strong>{shortId(item.approval_request_id)}</strong></td><td>{item.policy_code}<br /><small>v{item.policy_version}</small></td><td>{humanizeCode(item.division_code)}</td><td><span className="status">{humanizeCode(item.status)}</span></td><td>{formatDateTime(item.created_at)}</td><td>{formatDateTime(item.decided_at)}</td></tr>)}
        </tbody></table></div>
      ) : null}
    </>
  );
}

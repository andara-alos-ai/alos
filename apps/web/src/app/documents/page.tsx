"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, getDocuments } from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type { DocumentRecord } from "@/lib/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const { activeProjectId, status, token } = useSession();
  const [items, setItems] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getDocuments(token, activeProjectId);
      setItems(result.items);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Daftar dokumen belum dapat dimuat.");
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
      <header className="pageHeader"><div><p className="eyebrow">Dokumen & Evidence</p><h1>Dokumen Terverifikasi</h1><p>Metadata, versi, klasifikasi, pemindaian, dan status verifikasi dokumen perusahaan.</p></div><button className="button secondary" onClick={() => void load()} type="button">Perbarui data</button></header>
      {loading ? <LoadingState label="Memuat dokumen…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {!loading && !error && !items.length ? <EmptyState title="Belum ada dokumen" description="Dokumen akan tampil setelah diunggah melalui jalur storage dan lolos validasi keamanan." /> : null}
      {!loading && !error && items.length ? (
        <div className="tablePanel"><table><thead><tr><th>Dokumen</th><th>Divisi</th><th>Klasifikasi</th><th>Versi</th><th>Ukuran</th><th>Verifikasi</th><th>Diperbarui</th></tr></thead><tbody>
          {items.map((item) => <tr key={item.document_version_id}><td><strong>{item.logical_name}</strong><br /><small>{item.original_filename || shortId(item.document_id)}</small></td><td>{item.division_code ? humanizeCode(item.division_code) : "Lintas divisi"}</td><td>{humanizeCode(item.classification)}</td><td>v{item.version_number}</td><td>{formatSize(item.size_bytes)}</td><td><span className="status">{humanizeCode(item.verification_status)}</span><br /><small>Scan: {humanizeCode(item.scan_status)}</small></td><td>{formatDateTime(item.updated_at)}</td></tr>)}
        </tbody></table></div>
      ) : null}
    </>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, getOperationsHealth } from "@/lib/api";
import { formatDateTime, humanizeCode } from "@/lib/format";
import type { OperationsHealth } from "@/lib/types";

export default function SystemHealthPage() {
  const { status, token } = useSession();
  const [health, setHealth] = useState<OperationsHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try { setHealth(await getOperationsHealth(token)); }
    catch (requestError) { setError(requestError instanceof ApiError ? requestError.message : "Status sistem belum dapat dimuat."); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(refresh);
  }, [load, status]);

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Observability</p><h1>Kesehatan Sistem</h1><p>Pantau worker, antrean event integrasi, retry, dan dead letter tanpa membuka data bisnis divisi.</p></div><button className="button secondary" onClick={() => void load()} type="button">Perbarui status</button></header>
      {loading ? <LoadingState label="Memeriksa layanan operasional…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {!loading && !error && !health ? <EmptyState title="Status belum tersedia" description="Worker belum mencatat siklus operasional pada organisasi ini." /> : null}
      {!loading && !error && health ? <><section className="metricGrid"><article className="metricCard"><div><small>Pending event</small><strong>{health.pending_events}</strong><p>Menunggu pengiriman</p></div></article><article className="metricCard"><div><small>Retry</small><strong>{health.retry_events}</strong><p>Menunggu percobaan ulang</p></div></article><article className="metricCard"><div><small>Processing</small><strong>{health.processing_events}</strong><p>Sedang diproses</p></div></article><article className="metricCard"><div><small>Dead letter</small><strong>{health.dead_letter_events}</strong><p>Memerlukan pemeriksaan</p></div></article></section><section className="panel healthDetail"><div className="panelHeader"><div><p className="eyebrow">Worker terakhir</p><h2>{health.last_worker_status ? humanizeCode(health.last_worker_status) : "Belum berjalan"}</h2></div></div><dl className="detailGrid"><div><dt>Mulai</dt><dd>{formatDateTime(health.last_worker_started_at)}</dd></div><div><dt>Selesai</dt><dd>{formatDateTime(health.last_worker_completed_at)}</dd></div><div><dt>Event tertua</dt><dd>{formatDateTime(health.oldest_pending_at)}</dd></div></dl></section></> : null}
    </>
  );
}

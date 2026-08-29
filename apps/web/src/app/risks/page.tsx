"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { ApiError, getCapas, getExceptions } from "@/lib/api";
import { formatDateTime, humanizeCode, relativeDeadline, shortId } from "@/lib/format";
import type { CapaRecord, ExceptionRecord } from "@/lib/types";

export default function RisksPage() {
  const { activeProjectId, status, token } = useSession();
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([]);
  const [capas, setCapas] = useState<CapaRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [exceptionPage, capaPage] = await Promise.all([
        getExceptions(token, activeProjectId),
        getCapas(token, activeProjectId),
      ]);
      setExceptions(exceptionPage.items);
      setCapas(capaPage.items);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Data exception dan CAPA belum dapat dimuat.");
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
      <header className="pageHeader"><div><p className="eyebrow">Exception & Risk Control</p><h1>Exception dan CAPA</h1><p>Temuan operasional, akar masalah, tindakan korektif, dan verifikasi penutupan.</p></div><button className="button secondary" onClick={() => void load()} type="button">Perbarui data</button></header>
      {loading ? <LoadingState label="Memuat exception dan CAPA…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {!loading && !error && !exceptions.length && !capas.length ? <EmptyState title="Tidak ada exception aktif" description="Temuan dan CAPA akan muncul dari workflow ketika sistem atau manusia mendeteksi penyimpangan." /> : null}
      {!loading && !error && (exceptions.length || capas.length) ? (
        <div className="riskColumns">
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Temuan</p><h2>Exception ({exceptions.length})</h2></div></div><div className="recordList">{exceptions.map((item) => <article key={item.exception_id}><div><span className={`priorityBadge ${item.severity.toLowerCase()}`}>{humanizeCode(item.severity)}</span><h3>{humanizeCode(item.category)}</h3><p>{item.division_code ? humanizeCode(item.division_code) : "Lintas divisi"} · {shortId(item.exception_id)}</p></div><div className="recordStatus"><span className="statusBadge">{humanizeCode(item.status)}</span><small>{relativeDeadline(item.due_at)}</small></div></article>)}</div></section>
          <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Corrective action</p><h2>CAPA ({capas.length})</h2></div></div><div className="recordList">{capas.map((item) => <article key={item.capa_id}><div><span className="priorityBadge">CAPA</span><h3>{item.corrective_action || "Tindakan korektif belum dirinci"}</h3><p>Exception {shortId(item.exception_id)} · Dibuat {formatDateTime(item.created_at)}</p></div><div className="recordStatus"><span className="statusBadge">{humanizeCode(item.status)}</span><small>{relativeDeadline(item.due_at)}</small></div></article>)}</div></section>
        </div>
      ) : null}
    </>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  getOperationsHealth,
  getPilotReadiness,
  getSystemReadiness,
} from "@/lib/api";
import { formatDateTime, humanizeCode } from "@/lib/format";
import type {
  OperationsHealth,
  PilotReadinessReport,
  SystemReadinessReport,
} from "@/lib/types";

export default function SystemHealthPage() {
  const { activeProjectId, status, token } = useSession();
  const [health, setHealth] = useState<OperationsHealth | null>(null);
  const [readiness, setReadiness] = useState<PilotReadinessReport | null>(null);
  const [systemReadiness, setSystemReadiness] = useState<SystemReadinessReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [operations, pilot, system] = await Promise.all([
        getOperationsHealth(token),
        activeProjectId ? getPilotReadiness(token, activeProjectId) : Promise.resolve(null),
        getSystemReadiness(token).catch(() => null),
      ]);
      setHealth(operations);
      setReadiness(pilot);
      setSystemReadiness(system);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Status sistem belum dapat dimuat.",
      );
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
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Observability & Deployment Readiness</p>
          <h1>Kesehatan Sistem & Kesiapan Platform</h1>
          <p>
            Pantau status komponen inti (Database, 40 Migrasi, 18 Core Agent, Audit Ledger, LLM Gateway),
            antrean event integrasi, dan kesiapan operasional internal.
          </p>
        </div>
        <button className="button secondary" onClick={() => void load()} type="button">
          Perbarui status
        </button>
      </header>

      {loading ? <LoadingState label="Memeriksa status dan kesiapan sistem…" /> : null}
      {!loading && error ? <ErrorState message={error} retry={() => void load()} /> : null}

      {!loading && !error && (
        <>
          {/* Platform Component Readiness Grid */}
          {systemReadiness && (
            <section className="panel">
              <div className="panelHeader">
                <div>
                  <p className="eyebrow">Pre-Flight Platform Verification</p>
                  <h2>Komponen Inti ALOS</h2>
                  <p>
                    Status: <strong>{systemReadiness.status}</strong> • Lingkungan:{" "}
                    <strong>{systemReadiness.environment.toUpperCase()}</strong> • Waktu Cek:{" "}
                    {formatDateTime(systemReadiness.timestamp)}
                  </p>
                </div>
                <span
                  className={`statusBadge large readiness-${systemReadiness.status.toLowerCase()}`}
                >
                  {systemReadiness.status}
                </span>
              </div>

              <div className="readinessList">
                {systemReadiness.checks.map((check) => (
                  <article key={check.component}>
                    <span
                      className={`readinessMark ${
                        check.status === "HEALTHY"
                          ? "pass"
                          : check.status === "DEGRADED"
                          ? "warning"
                          : "blocked"
                      }`}
                    >
                      {check.status === "HEALTHY" ? "✓" : check.status === "DEGRADED" ? "!" : "×"}
                    </span>
                    <div>
                      <strong>{humanizeCode(check.component)}</strong>
                      <p>{check.message}</p>
                      {check.latency_ms !== null && (
                        <small>Respon: {check.latency_ms} ms</small>
                      )}
                    </div>
                    <b>{check.status}</b>
                  </article>
                ))}
              </div>
            </section>
          )}

          {/* Operational Metrics */}
          {health && (
            <>
              <section className="metricGrid">
                <article className="metricCard">
                  <div>
                    <small>Pending event</small>
                    <strong>{health.pending_events}</strong>
                    <p>Menunggu pengiriman</p>
                  </div>
                </article>
                <article className="metricCard">
                  <div>
                    <small>Retry</small>
                    <strong>{health.retry_events}</strong>
                    <p>Menunggu percobaan ulang</p>
                  </div>
                </article>
                <article className="metricCard">
                  <div>
                    <small>Processing</small>
                    <strong>{health.processing_events}</strong>
                    <p>Sedang diproses</p>
                  </div>
                </article>
                <article className="metricCard">
                  <div>
                    <small>Dead letter</small>
                    <strong>{health.dead_letter_events}</strong>
                    <p>Memerlukan pemeriksaan</p>
                  </div>
                </article>
              </section>

              <section className="panel healthDetail">
                <div className="panelHeader">
                  <div>
                    <p className="eyebrow">Worker terakhir</p>
                    <h2>
                      {health.last_worker_status
                        ? humanizeCode(health.last_worker_status)
                        : "Belum berjalan"}
                    </h2>
                  </div>
                </div>
                <dl className="detailGrid">
                  <div>
                    <dt>Mulai</dt>
                    <dd>{formatDateTime(health.last_worker_started_at)}</dd>
                  </div>
                  <div>
                    <dt>Selesai</dt>
                    <dd>{formatDateTime(health.last_worker_completed_at)}</dd>
                  </div>
                  <div>
                    <dt>Event tertua</dt>
                    <dd>{formatDateTime(health.oldest_pending_at)}</dd>
                  </div>
                </dl>
              </section>
            </>
          )}

          {/* Controlled Pilot Gate */}
          <section className="panel readinessPanel">
            <div className="panelHeader">
              <div>
                <p className="eyebrow">Controlled pilot gate</p>
                <h2>{readiness ? humanizeCode(readiness.overall_status) : "Pilih proyek"}</h2>
                <p>
                  {readiness
                    ? `${readiness.passed_checks} lulus · ${readiness.warning_checks} perhatian · ${readiness.blocked_checks} blocker`
                    : "Pilih konteks proyek untuk menjalankan pemeriksaan kesiapan pilot."}
                </p>
              </div>
              {readiness ? (
                <span
                  className={`statusBadge large readiness-${readiness.overall_status.toLowerCase()}`}
                >
                  {humanizeCode(readiness.overall_status)}
                </span>
              ) : null}
            </div>
            {readiness ? (
              <div className="readinessList">
                {readiness.checks.map((check) => (
                  <article key={check.check_id}>
                    <span className={`readinessMark ${check.status.toLowerCase()}`}>
                      {check.status === "PASS" ? "✓" : check.status === "WARNING" ? "!" : "×"}
                    </span>
                    <div>
                      <strong>{check.title}</strong>
                      <p>{check.detail}</p>
                      {check.remediation ? <small>{check.remediation}</small> : null}
                    </div>
                    <b>{humanizeCode(check.category)}</b>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        </>
      )}
    </>
  );
}

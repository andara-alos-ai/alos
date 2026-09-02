"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import { getConfigurationRegisters, getSourcePacks } from "@/lib/api";
import { humanizeCode } from "@/lib/format";
import type { ConfigurationMapping, ConfigurationRegister, SourcePack } from "@/lib/types";

type ViewFilter = "ALL" | "LOCKED" | "BLOCKED" | "EXTEND";

function sourceLabel(code: string): string {
  if (code === "DECISION") return "Struktur terkunci";
  if (code === "MASTER") return "Dokumen utama";
  if (/^[A-Z]$/.test(code)) return `Lampiran ${code}`;
  return humanizeCode(code);
}

function mappingVisible(mapping: ConfigurationMapping, filter: ViewFilter): boolean {
  if (filter === "LOCKED") return mapping.status === "APPROVED";
  if (filter === "BLOCKED") return mapping.activation_mode === "BLOCKED";
  if (filter === "EXTEND") return mapping.disposition === "EXTEND";
  return true;
}

export default function GovernancePage() {
  const { status, token } = useSession();
  const [sourcePacks, setSourcePacks] = useState<SourcePack[]>([]);
  const [registers, setRegisters] = useState<ConfigurationRegister[]>([]);
  const [filter, setFilter] = useState<ViewFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [packs, configurationRegisters] = await Promise.all([
        getSourcePacks(token),
        getConfigurationRegisters(token),
      ]);
      setSourcePacks(packs);
      setRegisters(configurationRegisters);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Blueprint belum dapat dimuat.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(refresh);
  }, [load, status]);

  const mappings = useMemo(() => (
    registers
      .flatMap((register) => register.mappings)
      .sort((left, right) => left.source_code.localeCompare(right.source_code))
  ), [registers]);
  const visibleMappings = mappings.filter((mapping) => mappingVisible(mapping, filter));
  const sources = sourcePacks.flatMap((pack) => pack.sources);
  const blockers = new Set(mappings.flatMap((mapping) => mapping.blocked_by_decisions));
  const approvedCount = mappings.filter((mapping) => mapping.status === "APPROVED").length;
  const extendCount = mappings.filter((mapping) => mapping.disposition === "EXTEND").length;
  const primaryPack = sourcePacks[0] || null;

  if (loading || status !== "authenticated") {
    return <LoadingState label="Memuat blueprint dan governance register…" />;
  }
  if (error) return <ErrorState message={error} retry={() => void load()} />;

  return (
    <>
      <header className="pageHeader governanceHeader">
        <div>
          <p className="eyebrow">Source governance · Genesis design-time</p>
          <h1>Blueprint & Keputusan</h1>
          <p>Master dan seluruh sumber terdaftar ditampilkan sebagai working baseline. Hanya struktur organisasi yang berstatus disetujui; nilai bisnis lain tetap menunggu ratifikasi manusia.</p>
        </div>
        <button className="button secondary" onClick={() => void load()} type="button">Perbarui registry</button>
      </header>

      <section className="governanceNotice" aria-label="Status baseline">
        <div>
          <span className="governanceNoticeMark">WB</span>
          <p><strong>Working Baseline · Tidak berefek ke production</strong><small>{primaryPack?.decision_basis || "Konfigurasi sumber belum diratifikasi untuk aktivasi produksi."}</small></p>
        </div>
        <span className="statusBadge readiness-attention">{primaryPack?.status || "DRAFT"}</span>
      </section>

      <section className="metricGrid governanceMetrics" aria-label="Ringkasan governance">
        <article className="metricCard"><div><small>Sumber terdaftar</small><strong>{sources.length}</strong><p>Register dinamis, termasuk master, keputusan, lampiran, dan fixture sintetis</p></div></article>
        <article className="metricCard"><div><small>Disetujui</small><strong>{approvedCount}</strong><p>Hanya boundary yang telah dikunci</p></div></article>
        <article className="metricCard"><div><small>Perlu diperluas</small><strong>{extendCount}</strong><p>Implementasi bertahap melalui registry</p></div></article>
        <article className="metricCard"><div><small>Keputusan terbuka</small><strong>{blockers.size}</strong><p>Belum boleh menjadi aturan aktif</p></div></article>
      </section>

      <section className="panel lockedStructurePanel">
        <div className="panelHeader"><div><p className="eyebrow">Locked organization boundary</p><h2>Struktur organisasi ALOS</h2></div><span className="statusBadge">APPROVED</span></div>
        <div className="organizationFlow" aria-label="Struktur organisasi yang dikunci">
          <div><small>01</small><strong>Direktur Utama</strong><span>Pemegang keputusan organisasi</span></div>
          <i>→</i>
          <div><small>02</small><strong>AI Executive Operating Layer</strong><span>Agregasi data, sinyal, dan brief</span></div>
          <i>→</i>
          <div className="divisionNode"><small>03</small><strong>Enam Divisi</strong><span>Keuangan · Sales & Marketing · Property · HR · Legal · IT</span></div>
        </div>
      </section>

      <section className="governanceLayout">
        <div className="governanceMain">
          <div className="sectionHeading">
            <div><p className="eyebrow">Canonical mapping</p><h2>Sumber dan konfigurasi ALOS</h2><p>Setiap kartu berasal dari configuration registry dinamis ALOS.</p></div>
            <div className="filterChips" aria-label="Filter blueprint">
              {(["ALL", "LOCKED", "BLOCKED", "EXTEND"] as ViewFilter[]).map((item) => (
                <button className={filter === item ? "active" : ""} key={item} onClick={() => setFilter(item)} type="button">{item === "ALL" ? "Semua" : humanizeCode(item)}</button>
              ))}
            </div>
          </div>

          {visibleMappings.length ? (
            <div className="mappingGrid">
              {visibleMappings.map((mapping) => (
                <article className="mappingCard" key={mapping.mapping_id}>
                  <div className="mappingCardTop">
                    <span className="documentKey">{mapping.source_code}</span>
                    <div><small>{sourceLabel(mapping.source_code)}</small><h3>{mapping.name}</h3></div>
                    <span className={`mappingStatus ${mapping.status.toLowerCase()}`}>{mapping.status}</span>
                  </div>
                  <dl className="mappingMeta"><div><dt>Owner</dt><dd>{humanizeCode(mapping.business_owner)}</dd></div><div><dt>Keputusan</dt><dd>{mapping.disposition}</dd></div><div><dt>Registry</dt><dd>{humanizeCode(mapping.target_registry)}</dd></div></dl>
                  <ul>{mapping.implementation_scope.map((scope) => <li key={scope}>{scope}</li>)}</ul>
                  <div className="mappingFooter">
                    <span className={`activationBadge ${mapping.activation_mode.toLowerCase()}`}>{humanizeCode(mapping.activation_mode)}</span>
                    {mapping.blocked_by_decisions.length ? <small>Menunggu {mapping.blocked_by_decisions.join(", ")}</small> : <small>Tidak ada blocker keputusan</small>}
                  </div>
                </article>
              ))}
            </div>
          ) : <EmptyState title="Tidak ada mapping" description="Tidak ada mapping yang sesuai dengan filter ini." />}
        </div>

        <aside className="governanceSide">
          <section className="panel genesisGuardrail">
            <div className="panelHeader"><div><p className="eyebrow">Genesis guardrail</p><h2>Penggunaan sumber</h2></div></div>
            <div className="guardrailGroup allowed"><strong>Diizinkan</strong><div>{primaryPack?.allowed_uses.map((use) => <span key={use}>{humanizeCode(use)}</span>)}</div></div>
            <div className="guardrailGroup blocked"><strong>Diblokir</strong><div>{primaryPack?.blocked_uses.map((use) => <span key={use}>{humanizeCode(use)}</span>)}</div></div>
            <p>Genesis dapat menganalisis, menghasilkan proposal, memvalidasi, menguji, dan membandingkan. Aktivasi production tetap membutuhkan review, staging, release, dan otoritas terpisah.</p>
          </section>

          <section className="panel sourceIntegrity">
            <div className="panelHeader"><div><p className="eyebrow">Source integrity</p><h2>Register dokumen</h2></div><span className="resultCount">{sources.length}</span></div>
            <div className="sourceIntegrityList">
              {sources.map((source) => (
                <article key={source.source_id}>
                  <span>{source.source_code}</span>
                  <div><strong>{source.title}</strong><small>{source.authority === "LOCKED_ORGANIZATION" ? "Locked organization" : "Design baseline"}</small></div>
                  <code title={source.sha256 || "System baseline"}>{source.sha256 ? source.sha256.slice(0, 8) : "SYSTEM"}</code>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </>
  );
}

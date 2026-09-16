"use client";

import { useState } from "react";

import {
  capabilityReadiness,
  capabilityReadinessTone,
  capabilityRiskTone,
  formatCapabilityDomainLabel,
  formatCapabilityScopes,
  groupCapabilitiesByDomain,
  type CapabilityRecord,
  type TypedToolRecord,
} from "@/lib/capabilities";

export type CapabilityViewProps = {
  capabilities: CapabilityRecord[];
  tools: TypedToolRecord[];
  loading: boolean;
};

const readinessLabel: Record<ReturnType<typeof capabilityReadiness>, string> = {
  READY: "Siap digunakan",
  NEEDS_CONFIGURATION: "Perlu konfigurasi",
  UNAVAILABLE: "Tidak tersedia",
};

/**
 * Operational, human-readable view of the Capability Registry for IT users.
 * Every field (purpose, status, version, scope, risk, readiness) comes
 * directly from the backend contract; this view never falls back to a mock
 * or locally computed capability list.
 */
export function CapabilityView({ capabilities, tools, loading }: CapabilityViewProps) {
  const [selectedKey, setSelectedKey] = useState<string>(() => capabilities[0]?.capability_key ?? "");

  if (loading) {
    return <p className="alos-loading-inline">Memuat Capability Registry…</p>;
  }

  if (capabilities.length === 0) {
    return (
      <p className="empty-state">
        Belum ada Capability terdaftar untuk organisasi ini. Registry akan tampil setelah
        platform mendaftarkan definisi Capability.
      </p>
    );
  }

  const selected = capabilities.find((capability) => capability.capability_key === selectedKey);
  const groups = groupCapabilitiesByDomain(capabilities);
  const backingTools = selected
    ? tools.filter((tool) => tool.capability_key === selected.capability_key)
    : [];

  return (
    <section aria-label="Capability Registry" className="alos-capability-view">
      <div className="alos-capability-layout">
        <div className="alos-capability-list" role="list">
          {groups.map((group) => (
            <div className="alos-capability-domain-group" key={group.domain}>
              <p className="alos-dash-kicker">{formatCapabilityDomainLabel(group.domain)}</p>
              {group.items.map((capability) => {
                const readiness = capabilityReadiness(capability);
                return (
                  <button
                    aria-current={capability.capability_key === selectedKey ? "true" : undefined}
                    className={`alos-capability-row ${capability.capability_key === selectedKey ? "selected" : ""}`}
                    key={capability.capability_key}
                    onClick={() => setSelectedKey(capability.capability_key)}
                    role="listitem"
                    type="button"
                  >
                    <div>
                      <strong>{capability.name}</strong>
                      <small>{capability.capability_key}</small>
                    </div>
                    <span className={`alos-status-pill ${capabilityReadinessTone(readiness)}`}>
                      {readinessLabel[readiness]}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <article className="alos-capability-detail">
          {!selected ? (
            <p className="empty-state">Pilih Capability untuk melihat purpose, status, dan scope operasional.</p>
          ) : (
            <CapabilityDetail capability={selected} tools={backingTools} />
          )}
        </article>
      </div>
    </section>
  );
}

function CapabilityDetail({
  capability,
  tools,
}: {
  capability: CapabilityRecord;
  tools: TypedToolRecord[];
}) {
  const readiness = capabilityReadiness(capability);
  return (
    <>
      <div className="alos-capability-detail-head">
        <div>
          <p className="alos-dash-kicker">{formatCapabilityDomainLabel(capability.domain)}</p>
          <h3>{capability.name}</h3>
        </div>
        <span className={`alos-status-pill ${capabilityReadinessTone(readiness)}`}>
          {readinessLabel[readiness]}
        </span>
      </div>
      <p className="alos-capability-purpose">{capability.description}</p>
      <dl className="review-list">
        <div><dt>Capability key</dt><dd>{capability.capability_key}</dd></div>
        <div><dt>Version</dt><dd>{capability.version}</dd></div>
        <div><dt>Status</dt><dd>{capability.availability} · {capability.configuration_status}</dd></div>
        <div><dt>Scope</dt><dd>{formatCapabilityScopes(capability)}</dd></div>
        <div>
          <dt>Risk</dt>
          <dd><span className={`alos-status-pill ${capabilityRiskTone(capability.risk_level)}`}>{capability.risk_level}</span></dd>
        </div>
        <div><dt>Access mode</dt><dd>{capability.access_mode}</dd></div>
        <div><dt>Data classification</dt><dd>{capability.allowed_data_classification.join(", ") || "—"}</dd></div>
        <div><dt>Readiness</dt><dd>{readinessLabel[readiness]}</dd></div>
      </dl>
      <h4>Typed tools terhubung</h4>
      {tools.length === 0 ? (
        <p className="empty-state">Belum ada typed tool terdaftar untuk Capability ini.</p>
      ) : (
        <ul className="alos-capability-tool-list">
          {tools.map((tool) => (
            <li key={tool.tool_key}>
              <strong>{tool.tool_key}</strong>
              <span>{tool.lifecycle_status} · risk {tool.risk_level}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="safe-note">
        Capability ini tidak memberi akses otomatis. Permission tetap harus disetujui melalui
        Governance → Permissions sebelum Agent dapat memakainya.
      </p>
    </>
  );
}

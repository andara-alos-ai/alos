"use client";

import Link from "next/link";
import { useState } from "react";

import type { SessionActor } from "@/lib/governance";
import {
  isActionUsable,
  permissionForDomain,
  rndPermissionLabel,
  rndPermissionNextAction,
  rndPermissionTone,
  type RndBacklogPermission,
  type RndDomainPermission,
} from "@/lib/rnd-permissions";

export type RndDomainKey =
  | "TECHNOLOGY"
  | "PROPERTY_BUSINESS_MODEL"
  | "CORPORATE_MANAGEMENT"
  | "PROPERTY_MARKET";

export type RndDomainSummary = {
  key: RndDomainKey;
  label: string;
  description: string;
};

// Baseline taxonomy for the four business R&D domains (M2-H01-AI-06 / M2-H01-FE-05).
// These four domains run on a single Research & Intelligence engine; this is
// navigation/IA baseline only. Finding, Recommendation, Backlog Candidate and
// Production Backlog data will be wired once the backend contract (M2-H01-BE-06)
// and access semantics (M2-H02) are available.
export const rndDomains: RndDomainSummary[] = [
  {
    key: "TECHNOLOGY",
    label: "R&D Teknologi",
    description: "Riset model, framework, tool, dan teknologi baru. Menghasilkan recommendation/change proposal, bukan auto-update ModelGateway.",
  },
  {
    key: "PROPERTY_BUSINESS_MODEL",
    label: "R&D Model Bisnis Properti",
    description: "Riset paket, pricing, unit economics, dan skenario model bisnis properti.",
  },
  {
    key: "CORPORATE_MANAGEMENT",
    label: "R&D Manajemen Perusahaan",
    description: "Riset SOP, KPI, proses, dan governance perusahaan. Menghasilkan gap dan draft recommendation, bukan auto-change policy.",
  },
  {
    key: "PROPERTY_MARKET",
    label: "R&D Properti",
    description: "Riset pasar, wilayah, kompetitor, harga, permintaan, tren konsumen, dan regulasi dari sumber yang disetujui.",
  },
];

export type RndFlowStage = {
  stage: string;
  description: string;
};

export const rndToBacklogFlow: RndFlowStage[] = [
  { stage: "Research", description: "Sumber internal + eksternal sesuai policy." },
  { stage: "R&D Finding", description: "Temuan domain dengan evidence/citation; terpisah dari operational finding." },
  { stage: "Recommendation", description: "Usulan tindakan; belum executable." },
  { stage: "Backlog Candidate", description: "Draft work item; belum masuk production." },
  { stage: "Review", description: "Business/Domain Owner dan IT; Director bila material." },
  { stage: "Production Backlog", description: "Approved work item, dapat diteruskan ke eksekusi terkontrol." },
];

// Explicit, per-concept glossary so a user never has to infer the difference
// between Finding, Recommendation, Backlog Candidate, and Production Backlog
// from the linear flow alone. Each entry states what it IS, who owns the
// authority over it, and what it explicitly is NOT — this is the acceptance
// criterion for M2-H01-FE-05 ("memahami perbedaan ... tanpa raw schema").
export type RndStatusConcept = {
  key: "FINDING" | "RECOMMENDATION" | "BACKLOG_CANDIDATE" | "PRODUCTION_BACKLOG";
  label: string;
  whatItIs: string;
  authority: string;
  whatItIsNot: string;
};

export const rndStatusConcepts: RndStatusConcept[] = [
  {
    key: "FINDING",
    label: "R&D Finding",
    whatItIs: "Temuan riset per domain, didukung evidence dan citation sumber internal/eksternal.",
    authority: "Dicatat oleh peneliti/Agent riset; tidak memerlukan approval untuk dicatat.",
    whatItIsNot: "Bukan operational finding (compliance/audit) dan bukan keputusan atau tindakan.",
  },
  {
    key: "RECOMMENDATION",
    label: "Recommendation",
    whatItIs: "Usulan tindakan yang disusun dari satu atau lebih R&D Finding.",
    authority: "Disusun oleh peneliti/Agent riset; masih berupa usulan tertulis.",
    whatItIsNot: "Belum executable dan tidak mengubah sistem, kebijakan, atau production secara otomatis.",
  },
  {
    key: "BACKLOG_CANDIDATE",
    label: "Backlog Candidate",
    whatItIs: "Draft work item yang diturunkan dari Recommendation yang dipandang layak ditindaklanjuti.",
    authority: "Diajukan oleh Business/Domain Owner; masih berstatus draft.",
    whatItIsNot: "Belum masuk antrian eksekusi production dan belum mengikat sumber daya tim.",
  },
  {
    key: "PRODUCTION_BACKLOG",
    label: "Production Backlog",
    whatItIs: "Work item yang telah melalui Review dan disetujui untuk dieksekusi secara terkontrol.",
    authority: "Disetujui oleh Business/Domain Owner dan IT; Director untuk item material.",
    whatItIsNot: "Bukan hasil otomatis dari Finding atau Recommendation; selalu melalui gate Review manusia.",
  },
];

export type RndViewsProps = {
  actor: SessionActor;
  // M2-H02-FE-05 (R&D Permission UX): backend-supplied allowed/denied/
  // needs-approval decisions for the four R&D domains and for Production
  // Backlog access. Omitted entirely until the backend contract exists —
  // every domain/backlog defaults to NOT_CONNECTED (see
  // lib/rnd-permissions.ts), never to a locally-fabricated ALLOWED state.
  domainPermissions?: RndDomainPermission[];
  backlogPermission?: RndBacklogPermission;
};

export function RndWorkspace({ actor, domainPermissions, backlogPermission }: RndViewsProps) {
  const [selectedDomain, setSelectedDomain] = useState<RndDomainKey>(rndDomains[0].key);
  const activeDomain = rndDomains.find((domain) => domain.key === selectedDomain) ?? rndDomains[0];
  const activeDomainPermissionStatus = permissionForDomain(domainPermissions, activeDomain.key);
  const backlogStatus = backlogPermission?.status ?? "NOT_CONNECTED";

  return (
    <section aria-label="Research & Intelligence" className="alos-content alos-rnd-workspace">
      <p className="alos-inline-notice" role="note">
        Workspace ini baru menampilkan navigasi dan konsep dasar (baseline H1). Finding, source
        viewer, dan Production Backlog akan aktif setelah backend Research &amp; Intelligence
        tersedia pada hari kerja berikutnya.
      </p>

      <article aria-label="Pilih Domain R&D" className="alos-panel alos-rnd-domain-picker">
        <div className="alos-panel-title">
          <p className="alos-dash-kicker">EMPAT DOMAIN R&amp;D</p>
          <h3>Pilih domain untuk melihat konteks risetnya</h3>
        </div>
        <div className="alos-rnd-domain-grid" role="tablist" aria-label="Domain R&D">
          {rndDomains.map((domain) => {
            const status = permissionForDomain(domainPermissions, domain.key);
            return (
              <button
                aria-current={domain.key === selectedDomain ? "true" : undefined}
                aria-label={domain.label}
                className={`alos-panel alos-rnd-domain-card ${domain.key === selectedDomain ? "selected" : ""}`}
                key={domain.key}
                onClick={() => setSelectedDomain(domain.key)}
                role="tab"
                type="button"
              >
                <div className="alos-panel-title">
                  <p className="alos-dash-kicker">{domain.key}</p>
                  <h3>{domain.label}</h3>
                  <span className={`alos-rnd-permission-badge tone-${rndPermissionTone(status)}`}>
                    {rndPermissionLabel(status)}
                  </span>
                </div>
                <p>{domain.description}</p>
              </button>
            );
          })}
        </div>
      </article>

      <article aria-label={`Status riset domain ${activeDomain.label}`} className="alos-panel alos-rnd-domain-status-card">
        <div className="alos-panel-title">
          <p className="alos-dash-kicker">STATUS DOMAIN TERPILIH</p>
          <h3>{activeDomain.label}</h3>
          <span className={`alos-rnd-permission-badge tone-${rndPermissionTone(activeDomainPermissionStatus)}`}>
            {rndPermissionLabel(activeDomainPermissionStatus)}
          </span>
        </div>
        <p>{activeDomain.description}</p>
        {rndPermissionNextAction(activeDomainPermissionStatus) ? (
          <p
            className={`alos-rnd-permission-note tone-${rndPermissionTone(activeDomainPermissionStatus)}`}
            role={activeDomainPermissionStatus === "DENIED" ? "alert" : "note"}
          >
            {rndPermissionNextAction(activeDomainPermissionStatus)}
          </p>
        ) : null}
        <div className="alos-rnd-status-grid">
          {rndStatusConcepts.map((concept) => (
            <div className="alos-rnd-status-cell" key={concept.key}>
              <strong>{concept.label}</strong>
              <span className="alos-rnd-status-count">Belum terhubung</span>
              <small>Menunggu backend Research &amp; Intelligence (M2-H01-BE-06).</small>
            </div>
          ))}
        </div>
        <p className="alos-empty-copy">
          Jumlah dan daftar {activeDomain.label} untuk setiap status akan tampil di sini setelah
          contract ResearchRequest, R&amp;D Finding, Recommendation, dan Backlog (M2-H01-BE-06)
          tersedia. Angka tidak dibuat-buat sebelum sumber data kanonis terhubung.
        </p>
      </article>

      <article aria-label="Perbedaan Finding, Recommendation, Backlog Candidate, dan Production Backlog" className="alos-panel alos-rnd-glossary-card">
        <div className="alos-panel-title">
          <p className="alos-dash-kicker">GLOSARIUM STATUS</p>
          <h3>Finding, Recommendation, Backlog Candidate, dan Production Backlog tidak sama</h3>
        </div>
        <div className="alos-rnd-glossary-grid">
          {rndStatusConcepts.map((concept) => (
            <article aria-label={concept.label} className="alos-rnd-glossary-entry" key={concept.key}>
              <h4>
                {concept.label}
                {concept.key === "PRODUCTION_BACKLOG" ? (
                  <span className={`alos-rnd-permission-badge tone-${rndPermissionTone(backlogStatus)}`}>
                    {rndPermissionLabel(backlogStatus)}
                  </span>
                ) : null}
              </h4>
              <dl>
                <div>
                  <dt>Apa itu</dt>
                  <dd>{concept.whatItIs}</dd>
                </div>
                <div>
                  <dt>Authority</dt>
                  <dd>{concept.authority}</dd>
                </div>
                <div>
                  <dt>Bukan</dt>
                  <dd>{concept.whatItIsNot}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </article>

      <article aria-label="R&D Finding ke Production Backlog" className="alos-panel alos-rnd-flow-card">
        <div className="alos-panel-title">
          <p className="alos-dash-kicker">ALUR</p>
          <h3>R&amp;D Finding menuju Production Backlog</h3>
        </div>
        <ol className="alos-rnd-flow-list">
          {rndToBacklogFlow.map((step) => (
            <li key={step.stage}>
              <strong>{step.stage}</strong>
              <span>{step.description}</span>
            </li>
          ))}
        </ol>
        <p className="alos-rnd-flow-note">
          Recommendation R&amp;D tidak dapat langsung mengubah production. Backlog Candidate
          bersifat draft; Production Backlog hanya terbentuk setelah review/approval sesuai
          materialitas.
        </p>
      </article>

      <article aria-label="Entry Point Riset Internal dan External" className="alos-panel alos-rnd-source-card">
        <div className="alos-panel-title">
          <p className="alos-dash-kicker">MULAI RISET</p>
          <h3>Internal &amp; External Research</h3>
        </div>
        <div className="alos-rnd-source-entry-grid">
          <article aria-label="Riset Internal" className="alos-rnd-source-entry">
            <div className="alos-rnd-source-entry-head">
              <strong>Internal</strong>
              <span className="alos-rnd-source-badge trusted">Authority ALOS</span>
            </div>
            <p>
              Dokumen perusahaan, data internal, laporan, dan evidence historis sesuai
              role/scope/classification Anda. Dapat dijadikan dasar Finding dan Recommendation.
            </p>
            {isActionUsable(activeDomainPermissionStatus) ? (
              <Link
                className="alos-rnd-source-entry-action"
                href="/genesis?mode=INTERNAL"
              >
                Mulai riset internal via GENESIS →
              </Link>
            ) : (
              <span className="alos-rnd-source-entry-action disabled" role="note">
                {rndPermissionNextAction(activeDomainPermissionStatus) ??
                  `Riset domain ${activeDomain.label} ${rndPermissionLabel(activeDomainPermissionStatus).toLowerCase()}.`}
              </span>
            )}
          </article>
          <article aria-label="Riset External" className="alos-rnd-source-entry">
            <div className="alos-rnd-source-entry-head">
              <strong>External</strong>
              <span className="alos-rnd-source-badge untrusted">Untrusted, tanpa authority</span>
            </div>
            <p>
              Sumber resmi dan connector yang disetujui organisasi. Selalu diperlakukan sebagai
              untrusted information: tidak memberi authority baru dan tidak pernah otomatis
              mengubah production tanpa review manusia.
            </p>
            {isActionUsable(activeDomainPermissionStatus) ? (
              <Link
                className="alos-rnd-source-entry-action"
                href="/genesis?mode=INTERNAL_AND_EXTERNAL"
              >
                Mulai riset internal + external via GENESIS →
              </Link>
            ) : (
              <span className="alos-rnd-source-entry-action disabled" role="note">
                {rndPermissionNextAction(activeDomainPermissionStatus) ??
                  `Riset domain ${activeDomain.label} ${rndPermissionLabel(activeDomainPermissionStatus).toLowerCase()}.`}
              </span>
            )}
          </article>
        </div>
        <p className="alos-empty-copy">
          Entry point ini membuka percakapan GENESIS dengan mode sumber yang sudah dipilih.
          Source registry, reliability, dan freshness metadata khusus domain R&amp;D akan tampil
          di sini setelah Research Orchestrator (H7) tersedia.
        </p>
      </article>

      <p className="sr-only">Diakses oleh {actor.roles.join(", ") || "pengguna ALOS"}.</p>
    </section>
  );
}

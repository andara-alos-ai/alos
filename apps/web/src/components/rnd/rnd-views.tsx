"use client";

import Link from "next/link";

import type { SessionActor } from "@/lib/governance";

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

export type RndViewsProps = {
  actor: SessionActor;
};

export function RndWorkspace({ actor }: RndViewsProps) {
  return (
    <section aria-label="Research & Intelligence" className="alos-content alos-rnd-workspace">
      <p className="alos-inline-notice" role="note">
        Workspace ini baru menampilkan navigasi dan konsep dasar (baseline H1). Finding, source
        viewer, dan Production Backlog akan aktif setelah backend Research &amp; Intelligence
        tersedia pada hari kerja berikutnya.
      </p>

      <div className="alos-rnd-domain-grid">
        {rndDomains.map((domain) => (
          <article aria-label={domain.label} className="alos-panel alos-rnd-domain-card" key={domain.key}>
            <div className="alos-panel-title">
              <p className="alos-dash-kicker">{domain.key}</p>
              <h3>{domain.label}</h3>
            </div>
            <p>{domain.description}</p>
          </article>
        ))}
      </div>

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
            <Link
              className="alos-rnd-source-entry-action"
              href="/genesis?mode=INTERNAL"
            >
              Mulai riset internal via GENESIS →
            </Link>
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
            <Link
              className="alos-rnd-source-entry-action"
              href="/genesis?mode=INTERNAL_AND_EXTERNAL"
            >
              Mulai riset internal + external via GENESIS →
            </Link>
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

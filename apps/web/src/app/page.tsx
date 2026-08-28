import Link from "next/link";

import { sharedAgents, workflows, workspaces } from "@/lib/catalog";

export default function DashboardPage() {
  return (
    <>
      <header className="pageHeader">
        <div><p className="eyebrow">AI Executive Operating Layer</p><h1>Pusat Operasi Internal</h1><p>Antrean, bukti, persetujuan, risiko, dan kinerja dalam satu sistem.</p></div>
        <button type="button" disabled>Data perusahaan belum diaktifkan</button>
      </header>

      <section className="stats" aria-label="Status fondasi">
        <article><span>Core Agent</span><strong>18</strong><small>shared runtime</small></article>
        <article><span>Workflow awal</span><strong>{workflows.length}</strong><small>konfigurasi STAGED</small></article>
        <article><span>Workspace divisi</span><strong>{workspaces.length}</strong><small>business-owned</small></article>
        <article><span>LLM produksi</span><strong>OFF</strong><small>aman secara bawaan</small></article>
      </section>

      <section>
        <div className="sectionTitle"><div><p className="eyebrow">Workspace</p><h2>Enam divisi operasional</h2></div><Link href="/workflows">Lihat workflow →</Link></div>
        <div className="workspaceGrid">
          {workspaces.map((workspace) => (
            <article className="workspaceCard" key={workspace.id}>
              <div className="cardTop"><span>{workspace.name.slice(0, 2).toUpperCase()}</span><small>{workspace.agents.length || "IT"}</small></div>
              <h3>{workspace.name}</h3><p>{workspace.focus}</p>
              <div className="tags">{workspace.agents.length ? workspace.agents.map((agent) => <span key={agent}>{agent}</span>) : <span>Technical Custodian</span>}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="sharedPanel">
        <div><p className="eyebrow">Shared Enterprise</p><h2>Kontrol lintas divisi</h2><p>Tujuh agent bersama mendukung eksekusi tanpa mengambil alih akuntabilitas bisnis divisi.</p></div>
        <div className="tags large">{sharedAgents.map((agent) => <span key={agent}>{agent}</span>)}</div>
      </section>
    </>
  );
}

import Link from "next/link";
import { notFound } from "next/navigation";

import { workspaces } from "@/lib/catalog";

const workspaceCapabilities: Record<string, string[]> = {
  finance: ["Permintaan pembayaran", "Kontrol anggaran", "Rekonsiliasi", "Invoice & pajak"],
  "sales-marketing": ["Intake lead", "Penugasan sales", "Customer follow-up", "Pipeline & reservasi"],
  property: ["Bukti lapangan", "Validasi progres", "KPI teknis", "Exception & CAPA"],
  hr: ["Permintaan rekrutmen", "Screening", "Keputusan HR", "Checklist personalia"],
  legal: ["Intake izin & kontrak", "Review legal", "Verifikasi sumber", "Evidence keputusan"],
  it: ["Agent Runtime", "Integrasi", "Keamanan", "Observability & Genesis"],
};

const operationalLinks: Record<string, string> = {
  finance: "/finance",
  "sales-marketing": "/sales",
  property: "/property",
  hr: "/hr",
  legal: "/legal",
};

export default async function DivisionWorkspacePage({
  params,
}: {
  params: Promise<{ division: string }>;
}) {
  const { division } = await params;
  const workspace = workspaces.find((item) => item.id === division);
  if (!workspace) notFound();
  const capabilities = workspaceCapabilities[workspace.id] || [];

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Workspace Divisi</p><h1>{workspace.name}</h1><p>{workspace.focus}. Business owner tetap berada pada divisi ini; platform IT bertindak sebagai technical custodian.</p></div><Link className="button secondary" href={operationalLinks[workspace.id] || "/work-queue"}>Buka operasional</Link></header>
      <div className="workspaceOverview">
        <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Cakupan v1</p><h2>Kapabilitas operasional</h2></div></div><div className="capabilityGrid">{capabilities.map((capability, index) => <article key={capability}><span>{String(index + 1).padStart(2, "0")}</span><strong>{capability}</strong><small>Dijalankan melalui workflow dan audit trail ALOS.</small></article>)}</div></section>
        <aside className="panel"><div className="panelHeader"><div><p className="eyebrow">Digital workforce</p><h2>Core Agent</h2></div></div><div className="agentTiles">{workspace.agents.length ? workspace.agents.map((agent) => <div key={agent}><strong>{agent}</strong><span>Logical agent · Shared Runtime</span></div>) : <div><strong>Technical Custodian</strong><span>Runtime, registry, integrasi, security, observability, dan Genesis</span></div>}</div></aside>
      </div>
    </>
  );
}
